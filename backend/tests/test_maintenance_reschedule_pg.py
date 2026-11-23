"""Manual rescheduling end to end on PostgreSQL: forecast -> plan, reconcile keeps the date (needs pg_rehearse)."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.maintenance import MaintenanceInterval, MaintenancePlan
from app.schemas.maintenance import MaintenancePlanFromForecast, MaintenancePlanUpdate
from app.services import maintenance
from app.services.maintenance import estimate_date

from pace_factory import seed_pace

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def _fresh_pace_book():
    from app.services import maintenance_obligations as obligations

    obligations.reset_pace_book()
    yield
    obligations.reset_pace_book()

ADMIN = SimpleNamespace(role="admin", section_id=None)
TODAY = date.today()


async def _seed(mileage="4000"):
    tag = uuid4().hex[:8]
    asset_id, interval_id = uuid4(), uuid4()
    async with SessionFactory() as db:
        db.add(FixedAsset(id=asset_id, inv_number=f"RS-{tag}", asset_type="locomotive",
                          status="operational", mileage=Decimal(mileage)))
        db.add(MaintenanceInterval(id=interval_id, code=f"R-{tag}", name="Reschedule test",
                                   interval_km=Decimal("5000"), warn_percent=Decimal("60"),
                                   asset_types=["locomotive"], is_active=True))
        await db.flush()
        await seed_pace(db, asset_id, mileage)
        await db.commit()
    return asset_id, interval_id


async def _cleanup(asset_id, interval_id):
    async with SessionFactory() as db:
        await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))  # plans cascade
        await db.execute(delete(MaintenanceInterval).where(MaintenanceInterval.id == interval_id))
        await db.commit()


async def _schedule_item(asset_id, interval_id, on=None):
    # `on`: the day whose month is shown (a date 9 days ahead may already fall into the next month)
    async with SessionFactory() as db:
        result = await maintenance.get_schedule(db, ADMIN, (on or TODAY).strftime("%Y-%m"))
    return next((i for i in result.schedule if i.asset_id == asset_id and i.interval_id == interval_id), None)


async def test_forecast_becomes_a_manual_plan_and_the_automatic_forecast_keeps_its_hands_off():
    asset_id, interval_id = await _seed("4000")
    try:
        recommended = estimate_date(TODAY, Decimal("1000"), Decimal(settings.daily_km_estimate))
        forecast = await _schedule_item(asset_id, interval_id)
        assert forecast is not None and forecast.entity_type == "forecast"
        assert forecast.startDate == recommended and forecast.dateManual is False

        chosen = TODAY + timedelta(days=9)
        async with SessionFactory() as db:
            plan = await maintenance.create_plan_from_forecast(
                db, ADMIN, MaintenancePlanFromForecast(
                    asset_id=asset_id, interval_id=interval_id, scheduled_date=chosen,
                    reschedule_reason="  нет свободного бокса  "))
        assert plan.scheduled_date == chosen and plan.scheduled_date_manual is True
        assert plan.recommended_date == recommended and plan.reschedule_reason == "нет свободного бокса"
        assert plan.trigger_mileage == Decimal("5000.00")

        # the schedule now shows the plan (not the forecast) on the chosen day
        item = await _schedule_item(asset_id, interval_id, on=chosen)
        assert item.entity_type == "maintenance_plan" and item.startDate == chosen
        assert item.dateManual is True and item.recommendedDate == recommended

        # a mileage update re-runs the forecast: the chosen date must survive, the recommendation refreshes
        async with SessionFactory() as db:
            asset = await db.get(FixedAsset, asset_id)
            await maintenance.reconcile_asset_plans(db, asset, Decimal("4800"))
            await db.commit()
        async with SessionFactory() as db:
            stored = (await db.execute(select(MaintenancePlan).where(MaintenancePlan.asset_id == asset_id))).scalar_one()
        assert stored.scheduled_date == chosen
        assert stored.recommended_date == estimate_date(TODAY, Decimal("200"), Decimal(settings.daily_km_estimate))

        # a second plan for the same threshold is refused (reschedule the existing one instead)
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as raised:
                await maintenance.create_plan_from_forecast(
                    db, ADMIN, MaintenancePlanFromForecast(asset_id=asset_id, interval_id=interval_id, scheduled_date=chosen))
        assert raised.value.status_code == 409
    finally:
        await _cleanup(asset_id, interval_id)


async def test_moving_an_existing_plan_and_returning_to_the_recommendation():
    asset_id, interval_id = await _seed("4000")
    try:
        async with SessionFactory() as db:
            asset = await db.get(FixedAsset, asset_id)
            await maintenance.reconcile_asset_plans(db, asset, Decimal("4000"))
            await db.commit()
        async with SessionFactory() as db:
            plan_id = (await db.execute(select(MaintenancePlan.id).where(MaintenancePlan.asset_id == asset_id))).scalar_one()
        recommended = estimate_date(TODAY, Decimal("1000"), Decimal(settings.daily_km_estimate))

        moved = TODAY + timedelta(days=12)
        async with SessionFactory() as db:
            read = await maintenance.update_plan(db, ADMIN, plan_id, MaintenancePlanUpdate(
                scheduled_date=moved, reschedule_reason="ремонтный бокс занят"))
        assert read.scheduled_date == moved and read.scheduled_date_manual and read.recommended_date == recommended

        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as past:
                await maintenance.update_plan(db, ADMIN, plan_id, MaintenancePlanUpdate(scheduled_date=TODAY - timedelta(days=1)))
        assert past.value.status_code == 422

        async with SessionFactory() as db:
            reset = await maintenance.update_plan(db, ADMIN, plan_id, MaintenancePlanUpdate(reset_schedule=True))
        assert reset.scheduled_date == recommended
        assert (reset.scheduled_date_manual, reset.recommended_date, reset.reschedule_reason) == (False, None, None)

        # a plan that is already running cannot be moved
        async with SessionFactory() as db:
            await maintenance.update_plan(db, ADMIN, plan_id, MaintenancePlanUpdate(status="in_progress"))
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as running:
                await maintenance.update_plan(db, ADMIN, plan_id, MaintenancePlanUpdate(scheduled_date=moved))
        assert running.value.status_code == 409
    finally:
        await _cleanup(asset_id, interval_id)


async def test_database_rejects_a_reason_on_an_automatic_plan():
    asset_id, interval_id = await _seed("4000")
    try:
        async with SessionFactory() as db:
            db.add(MaintenancePlan(asset_id=asset_id, interval_id=interval_id, status="scheduled",
                                   trigger_mileage=Decimal("5000"), scheduled_date=TODAY,
                                   scheduled_date_manual=False, reschedule_reason="orphan"))
            with pytest.raises(IntegrityError):
                await db.commit()
    finally:
        await _cleanup(asset_id, interval_id)
