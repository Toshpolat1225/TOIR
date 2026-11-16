"""PostgreSQL tests for the conflicts page queries (needs pg_rehearse)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.asset_field_changes import AssetFieldChange
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrain, GtkTrainMember
from app.models.mileage import WialonOdometerReading
from app.models.organization import Department, Section
from app.models.wialon_counters import WialonCounterState
from app.repositories import conflict_views

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


async def _seed():
    now = datetime.now(timezone.utc)
    train_id = 900_000_000 + (uuid4().int % 90_000_000)
    loco_gtk = train_id + 1
    ids = dict(
        loco=uuid4(),
        other_loco=uuid4(),
        wagon=uuid4(),
        dept=uuid4(),
        section=uuid4(),
        train=train_id,
        tag=uuid4().hex[:8],
    )
    async with SessionFactory() as db:
        db.add(Department(id=ids["dept"], name=f"d-{ids['tag']}", color="#000000"))
        await db.commit()
        db.add(Section(id=ids["section"], name=f"s-{ids['tag']}", department_id=ids["dept"]))
        await db.commit()
        db.add_all(
            [
                FixedAsset(
                    id=ids["loco"],
                    inv_number=f"BLK-{ids['tag']}",
                    asset_type="locomotive",
                    status="operational",
                    mileage=Decimal("10"),
                    section_id=ids["section"],
                    wialon_id=f"w-{ids['tag']}",
                ),
                FixedAsset(
                    id=ids["other_loco"],
                    inv_number=f"OK-{ids['tag']}",
                    asset_type="locomotive",
                    status="operational",
                    mileage=Decimal("10"),
                ),
                FixedAsset(
                    id=ids["wagon"],
                    inv_number=f"W-{ids['tag']}",
                    asset_type="wagon",
                    status="operational",
                ),
            ]
        )
        await db.commit()
        db.add(GtkTrain(gtk_id=train_id, is_open=True))
        await db.commit()
        db.add_all(
            [
                WialonCounterState(
                    asset_id=ids["loco"],
                    last_status="rejected",
                    last_reason="same_time_different_odometer",
                    last_cnm=Decimal("100"),
                    last_cnm_at=now - timedelta(hours=3),
                    updated_at=now - timedelta(hours=2),
                ),
                WialonCounterState(
                    asset_id=ids["other_loco"],
                    last_status="accepted",
                    last_reason=None,
                ),
                AssetSourceLink(
                    asset_id=ids["loco"],
                    source="gtk",
                    external_id=str(loco_gtk),
                    link_method="manual",
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="locomotive",
                    object_gtk_id=loco_gtk,
                    is_main=True,
                    ord=1,
                    observed_from=now - timedelta(days=1),
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="carriage",
                    object_gtk_id=train_id + 2,
                    is_main=False,
                    ord=2,
                    observed_from=now - timedelta(days=1),
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="carriage",
                    object_gtk_id=train_id + 3,
                    is_main=False,
                    ord=3,
                    observed_from=now - timedelta(days=1),
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="carriage",
                    object_gtk_id=train_id + 4,
                    is_main=False,
                    ord=4,
                    observed_from=now - timedelta(days=1),
                    observed_to=now - timedelta(hours=5),  # closed: not counted
                ),
            ]
            + [
                WialonOdometerReading(
                    asset_id=ids["loco"],
                    source_unit_id=f"u-{ids['tag']}",
                    odometer_km=Decimal(100 + i),
                    reading_at=now - timedelta(minutes=i + 1),
                    observed_at=now - timedelta(minutes=i + 1),
                    received_at=now - timedelta(minutes=i + 1),
                    accepted=True,
                    calculation_eligible=False,
                    classification="HELD",
                    rejection_reason="counter_state_blocked_by_unresolved_conflict",
                    payload_hash=uuid4().hex + uuid4().hex,
                    payload={},
                )
                for i in range(3)
            ]
        )
        db.add_all(
            [
                AssetFieldChange(
                    asset_id=ids["wagon"],
                    field="inv_number",
                    old_value="A",
                    new_value="B",
                    source="gtk",
                    kind="conflict",
                    status="pending",
                ),
                AssetFieldChange(
                    asset_id=ids["wagon"],
                    field="serial_number",
                    old_value="1",
                    new_value="2",
                    source="wialon",
                    kind="conflict",
                    status="pending",
                ),
            ]
        )
        await db.commit()
    return ids


async def _cleanup(ids):
    async with SessionFactory() as db:
        await db.execute(delete(AssetFieldChange).where(AssetFieldChange.asset_id == ids["wagon"]))
        await db.execute(
            delete(WialonOdometerReading).where(WialonOdometerReading.asset_id == ids["loco"])
        )
        await db.execute(
            delete(WialonCounterState).where(
                WialonCounterState.asset_id.in_([ids["loco"], ids["other_loco"]])
            )
        )
        await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id == ids["train"]))
        await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == ids["train"]))
        await db.execute(
            delete(AssetSourceLink).where(AssetSourceLink.asset_id == ids["loco"])
        )
        await db.execute(
            delete(FixedAsset).where(
                FixedAsset.id.in_([ids["loco"], ids["other_loco"], ids["wagon"]])
            )
        )
        await db.execute(delete(Section).where(Section.id == ids["section"]))
        await db.execute(delete(Department).where(Department.id == ids["dept"]))
        await db.commit()


async def test_blocked_counters_list_counts_readings_and_open_wagons():
    ids = await _seed()
    try:
        async with SessionFactory() as db:
            rows, total, summary = await conflict_views.list_blocked_counters(
                db, q=ids["tag"], section_id=None, limit=50, offset=0
            )
        assert total == 1 and len(rows) == 1  # the unblocked locomotive is absent
        row = rows[0]
        assert row["inv_number"] == f"BLK-{ids['tag']}"
        assert row["blocked_readings_24h"] == 3
        assert row["affected_wagons"] == 2  # closed membership not counted
        assert summary == {"blocked_locomotives": 1, "affected_wagons": 2}
    finally:
        await _cleanup(ids)


async def test_blocked_counters_are_scoped_to_a_masters_section():
    ids = await _seed()
    try:
        async with SessionFactory() as db:
            mine, total_mine, _ = await conflict_views.list_blocked_counters(
                db, q=ids["tag"], section_id=ids["section"], limit=50, offset=0
            )
            other, total_other, _ = await conflict_views.list_blocked_counters(
                db, q=ids["tag"], section_id=uuid4(), limit=50, offset=0
            )
        assert total_mine == 1 and len(mine) == 1
        assert total_other == 0 and other == []
    finally:
        await _cleanup(ids)


async def test_field_conflicts_filter_by_source_field_and_asset_search():
    ids = await _seed()
    try:
        async with SessionFactory() as db:
            all_rows, total = await conflict_views.list_field_conflicts(
                db, status="pending", source=None, field=None,
                q=ids["tag"], limit=50, offset=0,
            )
            gtk_rows, gtk_total = await conflict_views.list_field_conflicts(
                db, status="pending", source="gtk", field=None,
                q=ids["tag"], limit=50, offset=0,
            )
            field_rows, _ = await conflict_views.list_field_conflicts(
                db, status="pending", source=None, field="serial_number",
                q=ids["tag"], limit=50, offset=0,
            )
            none_rows, none_total = await conflict_views.list_field_conflicts(
                db, status="pending", source=None, field=None,
                q="no-such-asset-xyz", limit=50, offset=0,
            )
        assert total == 2 and len(all_rows) == 2
        assert gtk_total == 1 and gtk_rows[0][0].field == "inv_number"
        assert len(field_rows) == 1 and field_rows[0][0].source == "wialon"
        assert all_rows[0][1] == f"W-{ids['tag']}" and all_rows[0][3] == "wagon"
        assert none_total == 0 and none_rows == []
    finally:
        await _cleanup(ids)
