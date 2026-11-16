"""Assets page: connection / mileage / odometer / suspect filters and NULLS-LAST sorting (needs pg_rehearse)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.wialon_units import WialonUnitRecord
from app.services import unified_assets

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


async def _seed():
    tag = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    ids = {k: uuid4() for k in ("a", "b", "c")}
    async with SessionFactory() as db:
        for key, mileage in (("a", "10"), ("b", "500"), ("c", "0")):
            db.add(FixedAsset(id=ids[key], inv_number=f"FLT-{key}-{tag}", asset_type="wagon",
                              status="operational", mileage=Decimal(mileage)))
        await db.commit()
        db.add_all([
            # b: reports now, high odometer
            WialonUnitRecord(unit_id=f"u-b-{tag}", name=f"FLT unit b {tag}", cnm=Decimal("7000"),
                             last_message_at=now - timedelta(minutes=1)),
            # a: silent for hours, low odometer, suspicious
            WialonUnitRecord(unit_id=f"u-a-{tag}", name=f"FLT unit a {tag}", cnm=Decimal("100"),
                             last_message_at=now - timedelta(hours=5), suspect_absolute=True),
        ])
        await db.commit()
        db.add_all([
            AssetSourceLink(asset_id=ids["a"], source="wialon", external_id=f"u-a-{tag}"),
            AssetSourceLink(asset_id=ids["b"], source="wialon", external_id=f"u-b-{tag}"),
        ])
        await db.commit()
    return tag, ids


async def _cleanup(tag, ids):
    async with SessionFactory() as db:
        await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_(list(ids.values()))))
        await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(list(ids.values()))))
        await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id.like(f"u-%-{tag}")))
        await db.commit()


async def _list(tag, *, source=None, sort_by="name", sort_order="asc", **filters):
    async with SessionFactory() as db:
        items, total = await unified_assets.list_unified_assets(
            db, source=source, asset_type=None, asset_status=None, section_id=None,
            master_section_id=None, q=f"FLT-", limit=500, offset=0,
            sort_by=sort_by, sort_order=sort_order, **filters,
        )
    return [i.inv_number[4] for i in items if i.inv_number and tag in i.inv_number], total


async def test_connection_mileage_odometer_and_suspect_filters():
    tag, ids = await _seed()
    try:
        assert (await _list(tag, connection="online"))[0] == ["b"]
        assert (await _list(tag, connection="offline"))[0] == ["a"]
        assert (await _list(tag, connection="no_unit"))[0] == ["c"]
        assert (await _list(tag, mileage_min=Decimal("100")))[0] == ["b"]
        assert (await _list(tag, mileage_max=Decimal("100")))[0] == ["a", "c"]
        assert (await _list(tag, mileage_min=Decimal("10"), mileage_max=Decimal("500")))[0] == ["a", "b"]
        assert (await _list(tag, wialon_min=Decimal("1000")))[0] == ["b"]
        assert (await _list(tag, wialon_max=Decimal("1000")))[0] == ["a"]
        assert (await _list(tag, suspect=True))[0] == ["a"]
    finally:
        await _cleanup(tag, ids)


async def test_sort_directions_and_nulls_last():
    tag, ids = await _seed()
    try:
        assert (await _list(tag, sort_by="mileage", sort_order="desc"))[0] == ["b", "a", "c"]
        assert (await _list(tag, sort_by="mileage", sort_order="asc"))[0] == ["c", "a", "b"]
        # c has no Wialon unit (NULL odometer): last in BOTH directions
        assert (await _list(tag, sort_by="wialon_cnm", sort_order="desc"))[0] == ["b", "a", "c"]
        assert (await _list(tag, sort_by="wialon_cnm", sort_order="asc"))[0] == ["a", "b", "c"]
    finally:
        await _cleanup(tag, ids)


async def test_telemetry_filters_leave_gtk_only_rows_empty():
    items, total = await _list("zzzzzzzz", source="gtk", mileage_min=Decimal("1"))
    assert items == [] and total == 0
    items, total = await _list("zzzzzzzz", source="gtk", connection="online")
    assert items == [] and total == 0
