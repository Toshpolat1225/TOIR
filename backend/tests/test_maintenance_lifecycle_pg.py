"""Lifecycle of the living plan on PostgreSQL: cascade, order sync, approvals, blocks, baselines, health (needs pg_rehearse)."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.maintenance import (
    AssetMaintenanceBaseline,
    MaintenanceDecision,
    MaintenanceInterval,
    MaintenancePlan,
)
from app.models.organization import Section
from app.models.wialon_units import WialonUnitRecord
from app.models.work_orders import WorkOrder
from app.schemas.maintenance import (
    MaintenanceBaselineUpsert,
    MaintenanceDisruptionCreate,
    MaintenancePlanBlock,
    MaintenancePlanUpdate,
    MaintenancePlanWaive,
)
from app.schemas.work_orders import WorkOrderUpdate
from app.services import maintenance, maintenance_lifecycle as lifecycle, maintenance_obligations as obligations
from app.services import work_orders

from pace_factory import seed_pace

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]

ADMIN = SimpleNamespace(role="admin", section_id=None)
OPERATOR = SimpleNamespace(role="operator", section_id=None)
TODAY = date.today()


@pytest.fixture(autouse=True)
def _fresh_pace_book():
    obligations.reset_pace_book()
    yield
    obligations.reset_pace_book()


class World:
    def __init__(self):
        tag = uuid4().hex[:8]
        self.tag = tag
        self.asset_id = uuid4()
        self.section_id = uuid4()
        self.low_id, self.high_id = uuid4(), uuid4()
        self.unit_id = f"wu-{tag}"

    async def seed(self, mileage="4900", with_high=False):
        async with SessionFactory() as db:
            db.add(Section(id=self.section_id, name=f"S-{self.tag}"))
            await db.flush()
            db.add(FixedAsset(id=self.asset_id, inv_number=f"LC-{self.tag}", asset_type="locomotive",
                              status="operational", mileage=Decimal(mileage), section_id=self.section_id))
            await db.flush()
            await seed_pace(db, self.asset_id, mileage)
            db.add(MaintenanceInterval(id=self.low_id, code=f"L1-{self.tag}", name="low", interval_km=Decimal("5000"),
                                       rank=1, warn_percent=Decimal("10"), asset_types=["locomotive"], is_active=True))
            if with_high:
                db.add(MaintenanceInterval(id=self.high_id, code=f"L2-{self.tag}", name="high", interval_km=Decimal("15000"),
                                           rank=2, warn_percent=Decimal("10"), asset_types=["locomotive"], is_active=True))
            await db.commit()
        return self

    async def reconcile(self, mileage=None):
        async with SessionFactory() as db:
            asset = await db.get(FixedAsset, self.asset_id)
            created = await maintenance.reconcile_asset_plans(db, asset, Decimal(mileage) if mileage else asset.mileage)
            await db.commit()
        return created

    async def plan(self, interval_id=None):
        async with SessionFactory() as db:
            return (await db.execute(select(MaintenancePlan).where(
                MaintenancePlan.asset_id == self.asset_id, MaintenancePlan.interval_id == (interval_id or self.low_id)
            ))).scalar_one()

    async def cleanup(self):
        async with SessionFactory() as db:
            await db.execute(delete(WorkOrder).where(WorkOrder.fixed_asset_id == self.asset_id))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == self.asset_id))
            await db.execute(delete(MaintenanceInterval).where(MaintenanceInterval.id.in_([self.low_id, self.high_id])))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id == self.unit_id))
            await db.execute(delete(Section).where(Section.id == self.section_id))
            await db.commit()


@pytest_asyncio.fixture
async def world():
    w = World()
    yield w
    await w.cleanup()


async def _make_order(w: World, plan_id, status="in_progress"):
    order_id = uuid4()
    async with SessionFactory() as db:
        db.add(WorkOrder(id=order_id, number=f"WO-{uuid4().hex[:10]}", fixed_asset_id=w.asset_id, section_id=w.section_id,
                         order_kind="planned", status=status, description="plan test"))
        await db.flush()
        plan = await db.get(MaintenancePlan, plan_id)
        plan.work_order_id = order_id
        plan.status = "in_progress"
        await db.commit()
    return order_id


async def test_completing_a_higher_rank_covers_every_lower_rank_and_restarts_their_baselines(world):
    await world.seed("14800", with_high=True)
    # both are due: the 5 000 cycle (grid) and the 15 000 cycle
    await world.reconcile()
    low, high = await world.plan(world.low_id), await world.plan(world.high_id)
    async with SessionFactory() as db:
        covered = await lifecycle.finalize_completion(
            db, await db.get(MaintenancePlan, high.id), completed_on=TODAY, user=ADMIN)
        await db.commit()
    assert [p.id for p in covered] == [low.id]
    async with SessionFactory() as db:
        high_row, low_row = await db.get(MaintenancePlan, high.id), await db.get(MaintenancePlan, low.id)
        assert (high_row.status, high_row.completed_km) == ("completed", Decimal("14800.00"))
        assert (low_row.status, low_row.covered_by_plan_id) == ("covered", high.id)
        baselines = {b.interval_id: b for b in (await db.execute(select(AssetMaintenanceBaseline).where(
            AssetMaintenanceBaseline.asset_id == world.asset_id))).scalars()}
        assert {b.source for b in baselines.values()} == {"completed"}
        assert baselines[world.low_id].km == baselines[world.high_id].km == Decimal("14800.00")
        kinds = (await db.execute(select(MaintenanceDecision.kind).where(MaintenanceDecision.plan_id == low.id))).scalars().all()
        assert kinds == ["cover"]
    # the next cycle now counts from 14 800, not from the grid: nothing is due
    async with SessionFactory() as db:
        _, obs = await obligations.evaluate_for_asset(db, await db.get(FixedAsset, world.asset_id))
    assert {ob.interval.id: ob.baseline_km for ob in obs} == {world.low_id: Decimal("14800.00"), world.high_id: Decimal("14800.00")}
    assert all(ob.markers.state == "forecast" for ob in obs)


async def test_completing_an_unranked_interval_does_not_touch_others(world):
    await world.seed("4900")
    async with SessionFactory() as db:
        interval = await db.get(MaintenanceInterval, world.low_id)
        interval.rank = None
        await db.commit()
    await world.reconcile()
    plan = await world.plan()
    async with SessionFactory() as db:
        covered = await lifecycle.finalize_completion(db, await db.get(MaintenancePlan, plan.id), completed_on=TODAY)
        await db.commit()
    assert covered == []


async def test_work_order_completion_closes_the_plan_cancel_and_delete_release_it(world):
    await world.seed("4900")
    await world.reconcile()
    plan = await world.plan()

    order_id = await _make_order(world, plan.id)
    async with SessionFactory() as db:
        await work_orders.update_order(db, ADMIN, order_id, WorkOrderUpdate(status="cancelled"))
    async with SessionFactory() as db:
        row = await db.get(MaintenancePlan, plan.id)
        assert (row.status, row.work_order_id) == ("scheduled", None)  # the obligation is back, not lost

    second = await _make_order(world, plan.id)
    async with SessionFactory() as db:
        await work_orders.delete_order(db, second)
    async with SessionFactory() as db:
        row = await db.get(MaintenancePlan, plan.id)
        assert (row.status, row.work_order_id) == ("scheduled", None)

    third = await _make_order(world, plan.id)
    async with SessionFactory() as db:
        await work_orders.update_order(db, ADMIN, third, WorkOrderUpdate(status="completed"))
    async with SessionFactory() as db:
        row = await db.get(MaintenancePlan, plan.id)
        assert row.status == "completed" and row.completed_km == Decimal("4900.00")
        baseline = await db.get(AssetMaintenanceBaseline, (world.asset_id, world.low_id))
        assert baseline.source == "completed" and baseline.work_order_id == third
        decisions = (await db.execute(select(MaintenanceDecision.kind).where(MaintenanceDecision.plan_id == plan.id))).scalars().all()
        assert decisions.count("release") == 2


async def test_operators_need_an_administrator_beyond_the_tolerance_and_after_two_deferrals(world):
    await world.seed("4900")
    await world.reconcile()
    plan = await world.plan()

    async def move(user, days):
        async with SessionFactory() as db:
            return await maintenance.update_plan(db, user, plan.id, MaintenancePlanUpdate(
                scheduled_date=TODAY + timedelta(days=days), reschedule_reason="сдвиг"))

    with pytest.raises(HTTPException) as far:
        await move(OPERATOR, 40)  # 40 days at ~200 km/day is far beyond the 10 % tolerance
    assert far.value.status_code == 403
    assert (await move(OPERATOR, 2)).deferral_count == 1
    assert (await move(OPERATOR, 3)).deferral_count == 2
    with pytest.raises(HTTPException) as third:
        await move(OPERATOR, 4)  # already deferred twice
    assert third.value.status_code == 403
    assert (await move(ADMIN, 4)).deferral_count == 3  # an administrator may approve it
    async with SessionFactory() as db:
        decisions = await lifecycle.list_decisions(db, plan.id)
    assert [d.kind for d in decisions] == ["reschedule"] * 3
    assert decisions[0].to_date == TODAY + timedelta(days=4) and decisions[0].from_date == TODAY + timedelta(days=3)


async def test_blocking_keeps_the_obligation_and_only_an_administrator_waives(world):
    await world.seed("4900")
    await world.reconcile()
    plan = await world.plan()
    async with SessionFactory() as db:
        blocked = await maintenance.block_plan(db, OPERATOR, plan.id, MaintenancePlanBlock(
            reason_code="parts", until=TODAY + timedelta(days=5), note="жду фильтры"))
    assert blocked.status == "blocked" and blocked.blocked_reason == "parts"

    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as moving:
            await maintenance.update_plan(db, ADMIN, plan.id, MaintenancePlanUpdate(scheduled_date=TODAY + timedelta(days=3)))
    assert moving.value.status_code == 409  # unblock first
    # the forecast still sees the obligation while it is blocked: it is not dropped, and the plan is left alone
    await world.reconcile()
    assert (await world.plan()).status == "blocked"

    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as denied:
            await maintenance.waive_plan(db, OPERATOR, plan.id, MaintenancePlanWaive(reason="не нужно"))
    assert denied.value.status_code == 403
    async with SessionFactory() as db:
        waived = await maintenance.waive_plan(db, ADMIN, plan.id, MaintenancePlanWaive(reason="заменено старшим ТО"))
    assert waived.status == "waived"
    async with SessionFactory() as db:
        baseline = await db.get(AssetMaintenanceBaseline, (world.asset_id, world.low_id))
    assert baseline.source == "waived" and baseline.km == Decimal("5000.00")  # the next cycle counts from the waived threshold
    assert await world.reconcile() == 0  # the waived cycle is not planned again


async def test_a_disruption_blocks_plans_in_its_window_and_closing_it_releases_them(world):
    await world.seed("4900")
    await world.reconcile()
    plan = await world.plan()
    async with SessionFactory() as db:
        created = await lifecycle.create_disruption(db, MaintenanceDisruptionCreate(
            kind="no_bay", scope="asset", asset_id=world.asset_id, ends_on=TODAY + timedelta(days=10)), ADMIN)
    assert created.affected_plans == 1
    assert (await world.plan()).status == "blocked"
    async with SessionFactory() as db:
        closed = await lifecycle.close_disruption(db, created.id, ADMIN)
    assert closed.status == "closed" and closed.affected_plans == 1
    row = await world.plan()
    assert row.status == "scheduled" and row.blocked_reason is None

    async with SessionFactory() as db:  # a faulty sensor does not stop the work
        sensor = await lifecycle.create_disruption(db, MaintenanceDisruptionCreate(
            kind="sensor_failure", scope="asset", asset_id=world.asset_id), ADMIN)
    assert sensor.affected_plans == 0 and (await world.plan()).status == "scheduled"
    async with SessionFactory() as db:
        ctx, obs = await obligations.evaluate_for_asset(db, await db.get(FixedAsset, world.asset_id))
    assert obs[0].confidence == "stale"
    async with SessionFactory() as db:
        await lifecycle.close_disruption(db, sensor.id, ADMIN)


async def test_baseline_from_the_real_odometer_is_converted_to_the_toir_scale(world):
    await world.seed("3000")
    async with SessionFactory() as db:
        db.add(WialonUnitRecord(unit_id=world.unit_id, name=f"unit {world.tag}", cnm=Decimal("123000")))
        db.add(AssetSourceLink(asset_id=world.asset_id, source="wialon", external_id=world.unit_id, status="active"))
        await db.commit()
    async with SessionFactory() as db:
        read = await lifecycle.set_baseline(db, MaintenanceBaselineUpsert(
            asset_id=world.asset_id, interval_id=world.low_id, done_at=TODAY - timedelta(days=20),
            odometer_km=Decimal("121500")), ADMIN)
    # Wialon says 123 000 while TOIR says 3 000: the odometer is 120 000 ahead, so 121 500 is TOIR 1 500
    assert read.km == Decimal("1500.00") and read.source == "manual"
    async with SessionFactory() as db:
        _, obs = await obligations.evaluate_for_asset(db, await db.get(FixedAsset, world.asset_id))
    assert obs[0].baseline_source == "manual" and obs[0].markers.used == Decimal("1500.00")

    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as both:
            await lifecycle.set_baseline(db, MaintenanceBaselineUpsert(
                asset_id=world.asset_id, interval_id=world.low_id, done_at=TODAY, km=Decimal("1"), odometer_km=Decimal("2")), ADMIN)
        assert both.value.status_code == 422
        with pytest.raises(HTTPException) as future:
            await lifecycle.set_baseline(db, MaintenanceBaselineUpsert(
                asset_id=world.asset_id, interval_id=world.low_id, done_at=TODAY + timedelta(days=1), km=Decimal("1")), ADMIN)
        assert future.value.status_code == 422


async def test_baseline_without_a_wialon_odometer_needs_the_km_in_toir_scale(world):
    await world.seed("3000")
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as raised:
            await lifecycle.set_baseline(db, MaintenanceBaselineUpsert(
                asset_id=world.asset_id, interval_id=world.low_id, done_at=TODAY, odometer_km=Decimal("1000")), ADMIN)
    assert raised.value.status_code == 422


async def test_health_check_reports_and_repairs_a_running_plan_without_an_order(world):
    await world.seed("4900")
    await world.reconcile()
    plan = await world.plan()
    async with SessionFactory() as db:
        row = await db.get(MaintenancePlan, plan.id)
        row.status = "in_progress"  # a zombie: running, but no order behind it
        await db.commit()
    async with SessionFactory() as db:
        report = await lifecycle.run_health(db, fix=False)
    issue = next(i for i in report.issues if i.code == "running_plan_without_live_order")
    assert issue.count >= 1 and issue.fixed == 0 and not report.ok
    async with SessionFactory() as db:
        report = await lifecycle.run_health(db, fix=True)
        await db.commit()
    assert next(i for i in report.issues if i.code == "running_plan_without_live_order").fixed >= 1
    assert (await world.plan()).status == "scheduled"


async def test_schedule_exposes_markers_confidence_priority_and_blocked_state(world):
    await world.seed("4900")
    await world.reconcile()
    plan = await world.plan()
    async with SessionFactory() as db:
        result = await maintenance.get_schedule(db, ADMIN, TODAY.strftime("%Y-%m"))
    item = next(i for i in result.schedule if i.asset_id == world.asset_id and i.interval_id == world.low_id)
    assert item.entity_type == "maintenance_plan" and item.planStatus == "scheduled"
    assert item.state == "due_soon" and item.limiting == "km"
    assert item.dateEarly <= item.dateTypical <= item.dateLate
    assert item.confidence == "low" and item.baselineSource == "provisional"  # the grid baseline is a guess
    assert item.priority > 0 and item.priorityWhy
    assert item.paceKmPerDay is not None and item.paceSource in {"default", "setting", "group", "blend", "asset"}

    async with SessionFactory() as db:
        await maintenance.block_plan(db, ADMIN, plan.id, MaintenancePlanBlock(reason_code="no_crew"))
        result = await maintenance.get_schedule(db, ADMIN, TODAY.strftime("%Y-%m"))
    blocked = next(i for i in result.schedule if i.plan_id == plan.id)
    assert blocked.status == "blocked" and blocked.blockedReason == "no_crew"


async def test_kpis_count_the_state_of_the_plan(world):
    await world.seed("4900")
    await world.reconcile()
    async with SessionFactory() as db:
        kpi = await lifecycle.compute_kpis(db)
    assert kpi.obligations >= 1 and kpi.due_soon >= 1 and kpi.open_plans >= 1
    assert kpi.provisional_baseline >= 1
    assert kpi.on_time_pct is None or 0 <= kpi.on_time_pct <= 100


async def test_database_rules_for_the_new_states(world):
    await world.seed("4900")
    async with SessionFactory() as db:
        db.add(MaintenancePlan(asset_id=world.asset_id, interval_id=world.low_id, status="blocked",
                               trigger_mileage=Decimal("5000"), scheduled_date=TODAY))
        with pytest.raises(IntegrityError):  # blocked without a reason
            await db.commit()
    async with SessionFactory() as db:
        db.add(MaintenancePlan(asset_id=world.asset_id, interval_id=world.low_id, status="scheduled",
                               trigger_mileage=Decimal("5000"), scheduled_date=TODAY, blocked_reason="parts"))
        with pytest.raises(IntegrityError):  # a reason without being blocked
            await db.commit()
    async with SessionFactory() as db:
        db.add(AssetMaintenanceBaseline(asset_id=world.asset_id, interval_id=world.low_id, km=Decimal("-100"), source="import"))
        await db.commit()  # a negative baseline is legitimate: the service was done before tracking began


async def test_bulk_baseline_import_is_a_dry_run_until_applied(world):
    await world.seed("4000")
    rows = [
        {"inv_number": f"LC-{world.tag}", "interval_code": f"L1-{world.tag}", "done_at": "2026-10-01", "km": "2500"},
        {"inv_number": "NO-SUCH", "interval_code": f"L1-{world.tag}", "done_at": "2026-10-01", "km": "1"},
        {"inv_number": f"LC-{world.tag}", "interval_code": f"L1-{world.tag}", "done_at": "01.10.2026", "km": "1"},
    ]
    async with SessionFactory() as db:
        dry = await lifecycle.import_baselines(db, rows, apply=False)
    assert (dry["ok"], len(dry["errors"])) == (1, 2) and dry["details"][0]["used_since"] == "1500.00"
    async with SessionFactory() as db:
        assert await db.get(AssetMaintenanceBaseline, (world.asset_id, world.low_id)) is None
    async with SessionFactory() as db:
        done = await lifecycle.import_baselines(db, rows, apply=True)
    assert done["ok"] == 1
    async with SessionFactory() as db:
        stored = await db.get(AssetMaintenanceBaseline, (world.asset_id, world.low_id))
    assert stored.source == "import" and stored.km == Decimal("2500.00") and stored.done_at == date(2026, 10, 1)


async def test_the_hourly_cycle_plans_what_is_due_and_a_second_pass_changes_nothing(world):
    await world.seed("4900")
    async with SessionFactory() as db:
        first = await lifecycle.run_cycle(db)
    assert first["plans_created"] >= 1
    async with SessionFactory() as db:
        second = await lifecycle.run_cycle(db)
    assert second["plans_created"] == 0  # idempotent
    assert (await world.plan()).status == "scheduled"
