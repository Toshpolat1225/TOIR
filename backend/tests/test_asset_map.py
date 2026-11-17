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
from app.models.gtk import GtkCarriage, GtkTrain, GtkTrainMember
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


# -- wagons ride with their locomotive (GTK train) ---------------------------------------------------------
def _train(**over):
    base = dict(
        train_number="T-1", locomotive_asset_id=uuid4(), locomotive_inv_number="L-1", locomotive_name="Loco 1",
        locomotive_section_id=None, lat=Decimal("41.0"), lon=Decimal("69.0"), position_at=NOW - timedelta(minutes=2),
        last_message_at=NOW - timedelta(minutes=2), speed=Decimal("35"),
    )
    base.update(over)
    return base


def test_a_wagon_in_an_open_train_is_drawn_at_its_locomotive_even_when_it_has_its_own_gtk_coordinate():
    wagon = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_external_id="77", gtk_lat=Decimal("10"), gtk_lon=Decimal("10"))
    result = build_points([wagon], NOW - timedelta(minutes=15), trains={"77": _train()})
    point = result.points[0]
    assert point.source == "train" and (point.lat, point.lon) == (41.0, 69.0)
    assert point.train_number == "T-1" and point.locomotive_inv_number == "L-1" and point.online is True
    assert result.summary.by_source == {"train": 1}


def test_a_wagon_not_in_a_train_keeps_its_own_gtk_coordinate_and_an_invalid_train_fix_is_ignored():
    alone = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_external_id="78", gtk_lat=Decimal("40"), gtk_lon=Decimal("64"))
    zero_fix = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_external_id="79", gtk_lat=Decimal("40"), gtk_lon=Decimal("64"))
    result = build_points([alone, zero_fix], NOW, trains={"79": _train(lat=Decimal("0"), lon=Decimal("0"))})
    assert [p.source for p in result.points] == ["gtk", "gtk"]


def test_a_locomotive_is_never_placed_by_a_train_lookup_and_wialon_still_wins():
    loco_same_id = _row(asset_type="locomotive", gtk_link_id=uuid4(), gtk_external_id="77")
    own_gps = _row(
        asset_type="wagon", wialon_link_id=uuid4(), wialon_lat=Decimal("42"), wialon_lon=Decimal("70"), gtk_link_id=uuid4(), gtk_external_id="77",
    )
    result = build_points([loco_same_id, own_gps], NOW, trains={"77": _train()})
    assert [p.source for p in result.points] == ["wialon"] and result.summary.unplaced == 1


def test_a_master_does_not_learn_the_name_of_a_locomotive_of_another_section():
    mine, other = uuid4(), uuid4()
    wagon = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_external_id="77")
    hidden = build_points([wagon], NOW, trains={"77": _train(locomotive_section_id=other)}, scope_section_id=mine).points[0]
    assert hidden.source == "train" and hidden.train_number == "T-1"
    assert hidden.locomotive_inv_number is None and hidden.locomotive_name is None and hidden.locomotive_asset_id is None
    shown = build_points([wagon], NOW, trains={"77": _train(locomotive_section_id=mine)}, scope_section_id=mine).points[0]
    assert shown.locomotive_inv_number == "L-1"


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


@pytest.mark.pg
@pytest.mark.asyncio
async def test_a_wagon_in_an_open_gtk_train_is_placed_at_the_main_locomotive_and_a_closed_membership_is_ignored():
    tag = uuid4().hex[:6]
    base = 800_000 + int(tag[:4], 16) % 90_000
    loco_main, loco_second, loco_gtk_main, loco_gtk_second = uuid4(), uuid4(), base, base + 1
    wagon_in, wagon_out, wagon_gtk_in, wagon_gtk_out = uuid4(), uuid4(), base + 10, base + 11
    train_open, train_closed = base + 20, base + 21
    unit_main, unit_second = f"tm-{tag}", f"ts-{tag}"
    now = datetime.now(timezone.utc)
    assets = [loco_main, loco_second, wagon_in, wagon_out]
    async with SessionFactory() as db:
        db.add_all([
            FixedAsset(id=loco_main, inv_number=f"TR-L1-{tag}", asset_type="locomotive", status="operational"),
            FixedAsset(id=loco_second, inv_number=f"TR-L2-{tag}", asset_type="locomotive", status="operational"),
            FixedAsset(id=wagon_in, inv_number=f"TR-W1-{tag}", asset_type="wagon", status="operational"),
            FixedAsset(id=wagon_out, inv_number=f"TR-W2-{tag}", asset_type="wagon", status="operational"),
        ])
        await db.flush()
        db.add_all([
            WialonUnitRecord(unit_id=unit_main, name="UM", lat=Decimal("41.5"), lon=Decimal("69.5"), position_at=now, last_message_at=now),
            WialonUnitRecord(unit_id=unit_second, name="US", lat=Decimal("30.0"), lon=Decimal("60.0"), position_at=now, last_message_at=now),
            GtkCarriage(gtk_id=wagon_gtk_in, name="CI", is_active=True, lat=Decimal("10"), lon=Decimal("10")),
            GtkCarriage(gtk_id=wagon_gtk_out, name="CO", is_active=True, lat=Decimal("40.2"), lon=Decimal("65.2")),
            GtkTrain(gtk_id=train_open, number=f"N{tag}", is_open=True),
            GtkTrain(gtk_id=train_closed, number=f"C{tag}", is_open=False),
        ])
        await db.flush()
        db.add_all([
            AssetSourceLink(asset_id=loco_main, source="wialon", external_id=unit_main, status="active"),
            AssetSourceLink(asset_id=loco_second, source="wialon", external_id=unit_second, status="active"),
            AssetSourceLink(asset_id=loco_main, source="gtk", external_id=str(loco_gtk_main), status="active"),
            AssetSourceLink(asset_id=loco_second, source="gtk", external_id=str(loco_gtk_second), status="active"),
            AssetSourceLink(asset_id=wagon_in, source="gtk", external_id=str(wagon_gtk_in), status="active"),
            AssetSourceLink(asset_id=wagon_out, source="gtk", external_id=str(wagon_gtk_out), status="active"),
            GtkTrainMember(train_gtk_id=train_open, kind="locomotive", object_gtk_id=loco_gtk_second, is_main=False, ord=2, observed_from=now),
            GtkTrainMember(train_gtk_id=train_open, kind="locomotive", object_gtk_id=loco_gtk_main, is_main=True, ord=1, observed_from=now),
            GtkTrainMember(train_gtk_id=train_open, kind="carriage", object_gtk_id=wagon_gtk_in, is_main=False, ord=3, observed_from=now),
            # the other wagon was in a train once, but its membership is closed -> it keeps its own GTK coordinate
            GtkTrainMember(
                train_gtk_id=train_open, kind="carriage", object_gtk_id=wagon_gtk_out, is_main=False, ord=4,
                observed_from=now - timedelta(days=1), observed_to=now,
            ),
        ])
        await db.commit()
    try:
        async with SessionFactory() as db:
            admin = SimpleNamespace(role="admin", section_id=None)
            result = await asset_map.get_asset_map(db, admin, q="TR-")
            by_inv = {p.inv_number: p for p in result.points}
            rider = by_inv[f"TR-W1-{tag}"]
            assert rider.source == "train" and (rider.lat, rider.lon) == (41.5, 69.5)  # the MAIN locomotive, not the second one
            assert rider.train_number == f"N{tag}" and rider.locomotive_inv_number == f"TR-L1-{tag}" and rider.online is True
            parked = by_inv[f"TR-W2-{tag}"]
            assert parked.source == "gtk" and parked.lon == 65.2
            assert by_inv[f"TR-L1-{tag}"].source == "wialon"
            only_train = await asset_map.get_asset_map(db, admin, q="TR-", source="train")
            assert [p.inv_number for p in only_train.points] == [f"TR-W1-{tag}"]
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id.in_([train_open, train_closed])))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_(assets)))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(assets)))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id.in_([train_open, train_closed])))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id.in_([wagon_gtk_in, wagon_gtk_out])))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id.in_([unit_main, unit_second])))
            await db.commit()
