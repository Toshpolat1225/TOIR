"""The schedule exposes the interval length so the UI can show progress inside the CURRENT interval (needs pg_rehearse)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.maintenance import MaintenanceInterval
from app.services import maintenance

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


async def test_forecast_item_carries_interval_km_and_threshold():
    tag = uuid4().hex[:8]
    asset_id, interval_id = uuid4(), uuid4()
    async with SessionFactory() as db:
        db.add(FixedAsset(id=asset_id, inv_number=f"SCH-{tag}", asset_type="locomotive",
                          status="operational", mileage=Decimal("7300")))
        db.add(MaintenanceInterval(id=interval_id, code=f"T-{tag}", name="Schedule test",
                                   interval_km=Decimal("5000"), warn_percent=Decimal("60"),
                                   asset_types=["locomotive"], is_active=True))
        await db.commit()
    try:
        user = SimpleNamespace(role="admin", section_id=None)
        async with SessionFactory() as db:
            result = await maintenance.get_schedule(db, user, date.today().strftime("%Y-%m"))
        item = next(i for i in result.schedule if i.interval_id == interval_id)
        # next threshold is the next multiple of 5000 above 7300, not an absolute-odometer ratio
        assert item.nextThreshold == Decimal("10000")
        assert item.intervalKm == Decimal("5000")
        assert item.remainingKm == Decimal("2700")
        # progress inside the current interval = 1 - remaining / interval = 46 %
        assert round((1 - item.remainingKm / item.intervalKm) * 100) == 46
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(MaintenanceInterval).where(MaintenanceInterval.id == interval_id))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
            await db.commit()


async def test_schedule_items_carry_joined_names_and_one_consistent_unit_label():
    from app.models.asset_models import AssetModel
    from app.models.organization import Section

    tag = uuid4().hex[:8]
    asset_id, interval_id, model_id, section_id = uuid4(), uuid4(), uuid4(), uuid4()
    inv = f"NM-{tag}"
    async with SessionFactory() as db:
        db.add(Section(id=section_id, name=f"Участок {tag}"))
        db.add(AssetModel(id=model_id, name=f"Модель {tag}", name_normalized=f"модель {tag}",
                          asset_type="locomotive"))
        await db.commit()
        db.add(FixedAsset(id=asset_id, inv_number=inv, serial_number="777", asset_type="locomotive",
                          status="operational", mileage=Decimal("4800"), model_id=model_id,
                          section_id=section_id, wialon_online=True))
        db.add(MaintenanceInterval(id=interval_id, code=f"N-{tag}", name="Names test",
                                   interval_km=Decimal("5000"), warn_percent=Decimal("60"),
                                   asset_types=["locomotive"], is_active=True))
        await db.commit()
    try:
        user = SimpleNamespace(role="admin", section_id=None)
        async with SessionFactory() as db:
            result = await maintenance.get_schedule(db, user, date.today().strftime("%Y-%m"))
        items = [i for i in result.schedule if i.asset_id == asset_id]
        assert items, "the asset must have at least one schedule item"
        item = items[0]
        # names are JOINED (section, model), not left empty / as codes
        assert item.depot == f"Участок {tag}"
        assert item.asset_model == f"Модель {tag}"
        assert item.asset_serial == "777" and item.asset_inv_number == inv
        assert item.asset_type == "locomotive"
        assert item.asset_status == "operational"
        assert item.asset_online is True
        # one label for every item of the asset: translated type (or the code if untranslated) + serial-inv
        assert {i.unit for i in items} == {f"{item.asset_type_name or 'locomotive'} 777-{inv} · {inv}"}
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(MaintenanceInterval).where(MaintenanceInterval.id == interval_id))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
            await db.execute(delete(AssetModel).where(AssetModel.id == model_id))
            await db.execute(delete(Section).where(Section.id == section_id))
            await db.commit()
