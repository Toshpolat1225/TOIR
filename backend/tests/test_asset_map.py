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
from app.services.asset_map import build_points, build_unplaced, classify_unplaced, find_gtk_candidate


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


# -- the "without coordinates" page ---------------------------------------------------------------------------
def _carriage(**over):
    base = dict(
        gtk_id=1, name="2ВС-115 00019427", reg_number="00019427", inventory_number="38742", is_active=True, lat=None, lon=None,
        taken_by_inv_number=None,
    )
    base.update(over)
    return base


def _unplaced_rows():
    """One asset for each reason, plus one placed asset that must never appear."""
    link = uuid4
    return [
        _row(inv_number="A-nolink", asset_type="wagon", serial_number="19427", asset_created_at=NOW - timedelta(days=8)),
        _row(inv_number="B-nolink-tank", asset_type="tank_car", serial_number="13"),
        _row(inv_number="C-wialon-missing", wialon_link_id=link(), wialon_unit_id=None),
        _row(inv_number="D-wialon-nofix", wialon_link_id=link(), wialon_unit_id="u1", wialon_unit_name="Unit 1", wialon_last_message_at=NOW),
        _row(inv_number="E-gtk-loco", asset_type="locomotive", gtk_link_id=link(), gtk_external_id="5"),
        _row(inv_number="F-gtk-missing", asset_type="wagon", gtk_link_id=link(), gtk_external_id="6", gtk_carriage_id=None),
        _row(inv_number="G-gtk-nocoords", asset_type="wagon", gtk_link_id=link(), gtk_external_id="7", gtk_carriage_id=7, gtk_is_active=True),
        _row(inv_number="H-in-train", asset_type="wagon", gtk_link_id=link(), gtk_external_id="8", gtk_carriage_id=8),
        _row(inv_number="Z-placed", wialon_link_id=link(), wialon_lat=Decimal("41"), wialon_lon=Decimal("69")),
    ]


def test_every_unplaced_asset_gets_a_detailed_reason_and_a_placed_one_is_left_out():
    open_trains = {"8": {"train_number": "T-9", "has_locomotive": True}}
    page = build_unplaced(_unplaced_rows(), {}, open_trains, [], limit=100)
    reasons = {i.inv_number: (i.group, i.reason) for i in page.items}
    assert reasons == {
        "A-nolink": ("no_link", "no_link"),
        "B-nolink-tank": ("no_link", "no_link"),
        "C-wialon-missing": ("no_position", "wialon_unit_missing"),
        "D-wialon-nofix": ("no_position", "wialon_no_fix"),
        "E-gtk-loco": ("no_position", "gtk_locomotive_only"),
        "F-gtk-missing": ("no_position", "gtk_carriage_missing"),
        "G-gtk-nocoords": ("no_position", "gtk_no_coords"),
        "H-in-train": ("no_position", "train_no_gps"),
    }
    in_train = next(i for i in page.items if i.inv_number == "H-in-train")
    assert in_train.train_number == "T-9" and in_train.train_has_locomotive is True
    assert page.summary.total == 8 and page.summary.by_group == {"no_link": 2, "no_position": 6}


def test_the_unplaced_page_agrees_with_the_map_summary():
    rows = _unplaced_rows()
    trains = {}
    on_map = build_points(rows, NOW, trains=trains).summary
    page = build_unplaced(rows, trains, {}, [])
    assert page.summary.total == on_map.unplaced
    assert page.summary.by_group == on_map.unplaced_reasons


def test_a_wagon_placed_by_its_train_is_not_listed_as_unplaced():
    wagon = _row(asset_type="wagon", gtk_link_id=uuid4(), gtk_external_id="77")
    trains = {"77": _train()}
    assert build_unplaced([wagon], trains, {}, []).summary.total == 0


def test_an_unlinked_wagon_gets_the_gtk_carriage_with_the_same_numbers_and_a_taken_one_is_flagged():
    wagon = _row(inv_number="38742", asset_type="wagon", serial_number="19427")
    both = find_gtk_candidate(wagon, [_carriage()])
    assert both is not None and both.match == "inv_and_reg" and both.taken_by_inv_number is None and both.has_coordinates is False
    only_inv = find_gtk_candidate(wagon, [_carriage(reg_number="999")])
    assert only_inv is not None and only_inv.match == "inv"
    only_reg = find_gtk_candidate(wagon, [_carriage(inventory_number="1")])
    assert only_reg is not None and only_reg.match == "reg"
    taken = find_gtk_candidate(wagon, [_carriage(gtk_id=1, taken_by_inv_number="OTHER"), _carriage(gtk_id=2)])
    assert taken is not None and taken.gtk_id == 2  # a free carriage beats a taken one
    only_taken = find_gtk_candidate(wagon, [_carriage(taken_by_inv_number="OTHER")])
    assert only_taken is not None and only_taken.taken_by_inv_number == "OTHER"
    assert find_gtk_candidate(wagon, [_carriage(inventory_number="1", reg_number="2")]) is None
    assert find_gtk_candidate(_row(inv_number="38742", asset_type="locomotive"), [_carriage()]) is None  # locomotives: no carriage match


def test_empty_numbers_never_match_and_leading_zeros_are_ignored():
    blank = _row(inv_number="", asset_type="wagon", serial_number=None)
    assert find_gtk_candidate(blank, [_carriage(inventory_number="", reg_number=None)]) is None
    padded = _row(inv_number="1", asset_type="wagon", serial_number="0019427")
    assert find_gtk_candidate(padded, [_carriage(inventory_number="x", reg_number="19427")]).match == "reg"


def test_linkable_counts_only_free_exact_candidates_and_the_filters_sort_and_paginate():
    rows = [
        _row(inv_number="38742", asset_type="wagon", serial_number="19427"),
        _row(inv_number="38743", asset_type="wagon", serial_number="19428"),
        _row(inv_number="T1", asset_type="tank_car", serial_number="5"),
    ]
    carriages = [_carriage(), _carriage(gtk_id=2, reg_number="19428", inventory_number="38743", taken_by_inv_number="OTHER")]
    page = build_unplaced(rows, {}, {}, carriages)
    assert page.summary.linkable == 1 and page.summary.total == 3
    assert [(t.value, t.count) for t in page.summary.by_type] == [("wagon", 2), ("tank_car", 1)]
    assert [i.inv_number for i in build_unplaced(rows, {}, {}, carriages, only_linkable=True).items] == ["38742"]
    assert [i.inv_number for i in build_unplaced(rows, {}, {}, carriages, asset_type="tank_car").items] == ["T1"]
    assert [i.inv_number for i in build_unplaced(rows, {}, {}, carriages, reason="no_link").items] == ["T1", "38742", "38743"]  # by reason, then type (tank_car < wagon), then number
    assert [i.inv_number for i in build_unplaced(rows, {}, {}, carriages, sort_by="inv_number", descending=True).items] == ["T1", "38743", "38742"]
    second = build_unplaced(rows, {}, {}, carriages, sort_by="inv_number", limit=1, offset=1)
    assert [i.inv_number for i in second.items] == ["38743"] and second.total == 3 and second.summary.total == 3


@pytest.mark.asyncio
async def test_an_unknown_unplaced_sort_field_is_refused():
    with pytest.raises(HTTPException) as caught:
        await asset_map.get_unplaced(None, SimpleNamespace(role="admin", section_id=None), sort_by="password")
    assert caught.value.status_code == 422


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


@pytest.mark.pg
@pytest.mark.asyncio
async def test_the_unplaced_page_explains_each_reason_from_the_database_and_scopes_a_master():
    tag = uuid4().hex[:6]
    base = 700_000 + int(tag[:4], 16) % 90_000
    section_a, section_b = uuid4(), uuid4()
    unlinked, nocoords, nofix, other_section = uuid4(), uuid4(), uuid4(), uuid4()
    cand_gtk, nocoords_gtk = base, base + 1
    unit_id = f"un-{tag}"
    now = datetime.now(timezone.utc)
    assets = [unlinked, nocoords, nofix, other_section]
    async with SessionFactory() as db:
        db.add_all([Section(id=section_a, name=f"UN-A-{tag}"), Section(id=section_b, name=f"UN-B-{tag}")])
        await db.flush()
        db.add_all([
            FixedAsset(id=unlinked, inv_number=f"UN-1-{tag}", serial_number=f"{base}", asset_type="wagon", status="operational", section_id=section_a),
            FixedAsset(id=nocoords, inv_number=f"UN-2-{tag}", asset_type="wagon", status="operational", section_id=section_a),
            FixedAsset(id=nofix, inv_number=f"UN-3-{tag}", asset_type="locomotive", status="operational", section_id=section_a),
            FixedAsset(id=other_section, inv_number=f"UN-4-{tag}", asset_type="wagon", status="operational", section_id=section_b),
        ])
        await db.flush()
        db.add_all([
            # a free GTK carriage that matches the unlinked wagon by inventory AND registration number
            GtkCarriage(gtk_id=cand_gtk, name="CAND", reg_number=f"{base}", inventory_number=f"UN-1-{tag}", is_active=True),
            GtkCarriage(gtk_id=nocoords_gtk, name="NOCOORDS", is_active=True),
            WialonUnitRecord(unit_id=unit_id, name="NoFixUnit", last_message_at=now),
        ])
        await db.flush()
        db.add_all([
            AssetSourceLink(asset_id=nocoords, source="gtk", external_id=str(nocoords_gtk), status="active"),
            AssetSourceLink(asset_id=nofix, source="wialon", external_id=unit_id, status="active"),
        ])
        await db.commit()
    try:
        async with SessionFactory() as db:
            admin = SimpleNamespace(role="admin", section_id=None)
            page = await asset_map.get_unplaced(db, admin, q="UN-", limit=500)
            by_inv = {i.inv_number: i for i in page.items}
            assert by_inv[f"UN-1-{tag}"].reason == "no_link" and by_inv[f"UN-1-{tag}"].group == "no_link"
            candidate = by_inv[f"UN-1-{tag}"].candidate
            assert candidate is not None and candidate.gtk_id == cand_gtk and candidate.match == "inv_and_reg" and candidate.taken_by_inv_number is None
            assert by_inv[f"UN-2-{tag}"].reason == "gtk_no_coords" and by_inv[f"UN-2-{tag}"].gtk_carriage_id == nocoords_gtk
            assert by_inv[f"UN-2-{tag}"].gtk_first_seen_at is not None and by_inv[f"UN-2-{tag}"].gtk_last_synced_at is not None
            assert by_inv[f"UN-3-{tag}"].reason == "wialon_no_fix" and by_inv[f"UN-3-{tag}"].wialon_unit_name == "NoFixUnit"
            assert by_inv[f"UN-3-{tag}"].wialon_last_message_at is not None
            assert all(i.asset_created_at is not None for i in by_inv.values())
            # the same population as the map: total = unplaced of /map/assets
            on_map = await asset_map.get_asset_map(db, admin)
            everything = await asset_map.get_unplaced(db, admin, limit=500)
            assert everything.summary.total == on_map.summary.unplaced
            master = SimpleNamespace(role="master", section_id=section_b)
            scoped = await asset_map.get_unplaced(db, master, q="UN-", section_id=section_a, limit=500)  # the query asks for A
            assert [i.inv_number for i in scoped.items] == [f"UN-4-{tag}"]
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_(assets)))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(assets)))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id.in_([cand_gtk, nocoords_gtk])))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit_id))
            await db.execute(delete(Section).where(Section.id.in_([section_a, section_b])))
            await db.commit()


# ── Wialon + GTK GPS unified for locomotives ──────────────────────────────────────────────────────────────
def _gps_row(**over):
    base = dict(
        wialon_link_id=uuid4(), wialon_lat=Decimal("40.8500"), wialon_lon=Decimal("69.5700"), wialon_last_message_at=NOW - timedelta(minutes=2),
        wialon_position_at=NOW - timedelta(minutes=2), wialon_speed=Decimal("0"), gtk_link_id=uuid4(), gps_unit_id=1262,
        gps_lat=Decimal("40.85005"), gps_lon=Decimal("69.5700"), gps_at=NOW - timedelta(minutes=0.5), gps_speed=Decimal("0"),
    )
    base.update(over)
    return _row(**base)


def test_a_locomotive_with_both_trackers_is_drawn_at_the_newer_fix_and_confirmed():
    result = build_points([_gps_row()], NOW - timedelta(minutes=15), now=NOW)
    p = result.points[0]
    assert (p.source, p.gps_verdict, p.online) == ("gtk_gps", "confirmed", True)
    assert p.alt_source == "wialon" and p.alt_lat == 40.85 and p.gps_diff_m < 20
    assert result.summary.gps_verdicts == {"confirmed": 1} and result.summary.by_source == {"gtk_gps": 1}


def test_a_silent_gtk_tracker_keeps_the_wialon_point_and_says_so():
    result = build_points([_gps_row(gps_at=NOW - timedelta(hours=9), gps_lat=Decimal("40.90"))], NOW - timedelta(minutes=15), now=NOW)
    p = result.points[0]
    assert (p.source, p.gps_verdict) == ("wialon", "gtk_stale") and p.alt_source == "gtk_gps" and p.gps_diff_m > 5000 and p.gps_gtk_age_min > 500


def test_a_locomotive_only_gtk_gps_knows_is_placed_with_its_fix():
    row = _gps_row(wialon_link_id=None, wialon_lat=None, wialon_lon=None, wialon_position_at=None, wialon_last_message_at=None)
    result = build_points([row], NOW - timedelta(minutes=15), now=NOW)
    p = result.points[0]
    assert (p.source, p.gps_verdict, p.alt_source) == ("gtk_gps", "gtk_only", None) and result.summary.unplaced == 0
    from app.services.asset_map import _is_placed

    assert _is_placed(row, {})


def test_a_locomotive_without_a_gtk_gps_unit_keeps_the_plain_wialon_rules():
    result = build_points([_gps_row(gps_unit_id=None, gps_lat=None, gps_lon=None, gps_at=None)], NOW - timedelta(minutes=15), now=NOW)
    p = result.points[0]
    assert (p.source, p.gps_verdict, p.alt_source) == ("wialon", None, None) and result.summary.gps_verdicts == {}


def test_a_wagon_never_takes_a_gps_fix_of_a_locomotive_row():
    result = build_points([_gps_row(asset_type="wagon")], NOW - timedelta(minutes=15), now=NOW)
    assert result.points[0].source == "wialon" and result.points[0].gps_verdict is None
