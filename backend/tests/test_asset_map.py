"""The asset map: Wialon position parsing and storage, the choice between Wialon and GTK, master scope."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.integrations.wialon_client import parse_units
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage
from app.models.organization import Section
from app.models.wialon_units import WialonUnitRecord
from app.repositories import wialon_units as unit_repository
from app.services import asset_map
from app.services.asset_map import build_points


def _payload(**item):
    return {"items": [{"id": 1, "nm": "Unit", **item}]}


# ── Wialon position parsing ──────────────────────────────────────────────────────────────────────────────
def test_position_is_read_from_the_last_message():
    unit = parse_units(_payload(lmsg={"t": 1_700_000_000, "pos": {"y": 41.3111, "x": 69.2797, "t": 1_700_000_100, "s": 12}}))[0]
    assert (unit.lat, unit.lon) == (Decimal("41.3111"), Decimal("69.2797"))
    assert unit.position_at == datetime.fromtimestamp(1_700_000_100, tz=timezone.utc)


def test_position_falls_back_to_the_item_pos_and_message_time():
    unit = parse_units(_payload(lmsg={"t": 1_700_000_000}, pos={"y": 40.0, "x": 65.5}))[0]
    assert (unit.lat, unit.lon) == (Decimal("40.0"), Decimal("65.5"))
    assert unit.position_at == datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)


@pytest.mark.parametrize(
    "pos",
    [{}, {"y": 0, "x": 0}, {"y": 91, "x": 10}, {"y": 10, "x": 181}, {"y": "abc", "x": 1}, {"y": 41}, {"y": float("nan"), "x": 1}],
)
def test_a_missing_or_impossible_fix_is_no_position(pos):
    unit = parse_units(_payload(lmsg={"t": 1, "pos": pos}))[0]
    assert unit.lat is None and unit.lon is None and unit.position_at is None


def test_a_unit_without_any_position_still_parses():
    unit = parse_units(_payload())[0]
    assert unit.lat is None and unit.name == "Unit"


# ── choosing the point ───────────────────────────────────────────────────────────────────────────────────
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def _row(**over):
    base = dict(
        asset_id=uuid4(), inv_number="1", name="N", asset_type="locomotive", asset_type_name="Локомотив", status="operational",
        status_name="В эксплуатации", section_id=None, section_name=None, model_name=None, wialon_link_id=None, wialon_lat=None,
        wialon_lon=None, wialon_position_at=None, wialon_last_message_at=None, wialon_speed=None, gtk_link_id=None, gtk_lat=None,
        gtk_lon=None, gtk_synced_at=None,
    )
    base.update(over)
    return base


def test_wialon_is_preferred_and_online_is_judged_by_the_last_message():
    row = _row(
        wialon_link_id=uuid4(), wialon_lat=Decimal("41.3"), wialon_lon=Decimal("69.2"), wialon_last_message_at=NOW - timedelta(minutes=3),
        wialon_position_at=NOW - timedelta(minutes=3), wialon_speed=Decimal("40"), gtk_link_id=uuid4(), gtk_lat=Decimal("10"), gtk_lon=Decimal("10"),
    )
    old = _row(wialon_link_id=uuid4(), wialon_lat=Decimal("41.3"), wialon_lon=Decimal("69.2"), wialon_last_message_at=NOW - timedelta(hours=5))
    result = build_points([row, old], NOW - timedelta(minutes=15))
    assert [p.source for p in result.points] == ["wialon", "wialon"]
    assert result.points[0].lat == 41.3 and result.points[0].online is True and result.points[1].online is False


def test_gtk_is_used_when_wialon_has_no_position_and_gaps_are_counted_with_a_reason():
    gtk = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_lat=Decimal("40.5"), gtk_lon=Decimal("64.1"), gtk_synced_at=NOW)
    linked_no_position = _row(wialon_link_id=uuid4())
    unlinked = _row()
    zero = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_lat=Decimal("0"), gtk_lon=Decimal("0"))
    result = build_points([gtk, linked_no_position, unlinked, zero], NOW)
    assert [p.source for p in result.points] == ["gtk"]
    s = result.summary
    assert (s.total_assets, s.placed, s.unplaced) == (4, 1, 3)
    assert s.by_source == {"gtk": 1} and s.unplaced_reasons == {"no_position": 2, "no_link": 1}


def test_the_source_filter_hides_points_but_not_the_counts():
    a = _row(wialon_link_id=uuid4(), wialon_lat=Decimal("41"), wialon_lon=Decimal("69"))
    b = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_lat=Decimal("40"), gtk_lon=Decimal("64"))
    result = build_points([a, b], NOW, source="gtk")
    assert [p.source for p in result.points] == ["gtk"]
    assert result.summary.placed == 2 and result.summary.by_source == {"wialon": 1, "gtk": 1}


def test_a_master_without_a_section_is_refused_and_a_master_is_pinned_to_their_section():
    with pytest.raises(HTTPException) as caught:
        asset_map._master_section_scope(SimpleNamespace(role="master", section_id=None))
    assert caught.value.status_code == 403
    section = uuid4()
    assert asset_map._master_section_scope(SimpleNamespace(role="master", section_id=section)) == section
    assert asset_map._master_section_scope(SimpleNamespace(role="admin", section_id=None)) is None


# ── database ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.pg
@pytest.mark.asyncio
async def test_position_is_stored_and_the_last_known_one_survives_a_pull_without_it():
    unit_id = f"map-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    with_position = parse_units({"items": [{"id": unit_id, "nm": "MapUnit", "lmsg": {"t": 1_700_000_000, "pos": {"y": 41.25, "x": 69.5, "t": 1_700_000_000}}}]})
    without = parse_units({"items": [{"id": unit_id, "nm": "MapUnit", "lmsg": {"t": 1_700_000_500}}]})
    try:
        async with SessionFactory() as db:
            await unit_repository.upsert_units(db, with_position, synced_at=now)
            await db.commit()
        async with SessionFactory() as db:
            await unit_repository.upsert_units(db, without, synced_at=now)
            await db.commit()
        async with SessionFactory() as db:
            row = (await db.execute(select(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit_id))).scalar_one()
        assert (row.lat, row.lon) == (Decimal("41.2500000"), Decimal("69.5000000"))
        assert row.position_at == datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
        assert row.last_message_at == datetime.fromtimestamp(1_700_000_500, tz=timezone.utc)
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit_id))
            await db.commit()


@pytest.mark.pg
@pytest.mark.asyncio
async def test_the_map_query_joins_wialon_for_locomotives_and_gtk_for_wagons_and_scopes_a_master():
    tag = uuid4().hex[:6]
    section_a, section_b = uuid4(), uuid4()
    loco, wagon, other = uuid4(), uuid4(), uuid4()
    unit_id, gtk_id = f"mp-{tag}", 900_000 + int(tag[:4], 16) % 90_000
    now = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        db.add_all([Section(id=section_a, name=f"MAP-A-{tag}"), Section(id=section_b, name=f"MAP-B-{tag}")])
        await db.flush()
        db.add_all([
            FixedAsset(id=loco, inv_number=f"MAP-L-{tag}", asset_type="locomotive", status="operational", section_id=section_a),
            FixedAsset(id=wagon, inv_number=f"MAP-W-{tag}", asset_type="wagon", status="operational", section_id=section_a),
            FixedAsset(id=other, inv_number=f"MAP-O-{tag}", asset_type="wagon", status="operational", section_id=section_b),
        ])
        await db.flush()
        db.add(WialonUnitRecord(unit_id=unit_id, name="U", lat=Decimal("41.3"), lon=Decimal("69.2"), position_at=now, last_message_at=now))
        db.add(GtkCarriage(gtk_id=gtk_id, name="C", is_active=True, lat=Decimal("40.1"), lon=Decimal("65.2")))
        db.add_all([
            AssetSourceLink(asset_id=loco, source="wialon", external_id=unit_id, status="active"),
            AssetSourceLink(asset_id=wagon, source="gtk", external_id=str(gtk_id), status="active"),
        ])
        await db.commit()
    try:
        async with SessionFactory() as db:
            admin = SimpleNamespace(role="admin", section_id=None)
            everything = await asset_map.get_asset_map(db, admin, q=f"MAP-")
            by_inv = {p.inv_number: p for p in everything.points}
            assert by_inv[f"MAP-L-{tag}"].source == "wialon" and by_inv[f"MAP-L-{tag}"].lat == 41.3 and by_inv[f"MAP-L-{tag}"].online is True
            assert by_inv[f"MAP-W-{tag}"].source == "gtk" and by_inv[f"MAP-W-{tag}"].lon == 65.2
            assert f"MAP-O-{tag}" not in by_inv and everything.summary.unplaced_reasons.get("no_link", 0) >= 1
            only_gtk = await asset_map.get_asset_map(db, admin, q="MAP-", source="gtk")
            assert [p.inv_number for p in only_gtk.points if p.inv_number.endswith(tag)] == [f"MAP-W-{tag}"]
            master = SimpleNamespace(role="master", section_id=section_b)
            scoped = await asset_map.get_asset_map(db, master, q="MAP-", section_id=section_a)  # the query asks for A
            assert {p.inv_number for p in scoped.points} <= {f"MAP-O-{tag}"} and scoped.summary.total_assets == 1
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco, wagon, other])))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco, wagon, other])))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit_id))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id == gtk_id))
            await db.execute(delete(Section).where(Section.id.in_([section_a, section_b])))
            await db.commit()
