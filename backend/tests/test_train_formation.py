"""Trains drawn to scale: the geometry along the locomotive's track and the assembly from GTK / Wialon / position history."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.organization import Section
from app.models.position_history import AssetPositionHistory
from app.models.wialon_units import WialonUnitRecord
from app.services import position_history as ph
from app.services import train_formation as tf

UTC = timezone.utc


def test_vehicle_kinds_come_from_the_asset_type_and_model():
    assert tf.loco_kind("locomotive", "ПЭ-2у") == "electric" and tf.loco_kind("locomotive", None) == "electric"
    assert tf.loco_kind("diesel", "ТЭМ2") == "diesel" and tf.loco_kind("diesel", "ПЭ-2у") == "diesel"
    assert tf.loco_kind("special_self_propelled", "АС-7М") == "loco" and tf.loco_kind("special_self_propelled", "МПЭ-2у") == "electric"
    assert [tf.wagon_kind(t) for t in ("wagon", "tank_car", "platform", None)] == ["dump", "tank", "platform", "dump"]


def test_the_formation_is_the_locomotive_its_motor_car_then_the_cars_in_gtk_order():
    electric = tf.formation_specs("electric", "ПЭ-2у", ["dump", "dump", "tank"])
    assert [(s.role, s.kind) for s in electric] == [("loco", "electric"), ("motor", "motor"), ("wagon", "dump"), ("wagon", "dump"), ("wagon", "tank")]
    diesel = tf.formation_specs("diesel", "ТЭМ2", ["dump"])
    assert [(s.role, s.kind) for s in diesel] == [("loco", "diesel"), ("wagon", "dump")]
    two_section = tf.formation_specs("diesel", "2ТЭ116", [])
    assert [s.role for s in two_section] == ["loco", "motor"] and two_section[0].length == 18.0
    d = tf.centre_distances(electric)
    assert d[0] == 0 and round(d[1], 2) == round(10.5 + 1.2 + 10.5, 2) and round(d[2] - d[1], 2) == round(10.5 + 1.2 + 7.25, 2)


def test_vehicles_stand_behind_the_head_along_the_travelled_path_and_follow_a_curve():
    north = [(0.0, 0.0), (0.0, -100.0)]  # newest first: the train came from the south
    placed = tf.place_along(north, [0, 22.2, 40, 150], 90)
    assert [round(p[1], 1) for p in placed] == [0.0, -22.2, -40.0, -150.0]  # past the end: extended straight
    assert all(round(p[2]) == 0 for p in placed)  # heading north
    bend = [(0.0, 0.0), (0.0, -30.0), (-30.0, -30.0)]  # came from the west, turned north
    on_corner, after_corner = tf.place_along(bend, [15, 45], 90)
    assert round(on_corner[0]) == 0 and round(on_corner[1]) == -15 and round(on_corner[2]) == 0
    assert round(after_corner[0]) == -15 and round(after_corner[1]) == -30 and round(after_corner[2]) == 90  # the rear cars run east
    single = tf.place_along([(0.0, 0.0)], [0, 30], 90)
    assert [(round(p[0]), round(p[1]), p[2]) for p in single] == [(0, 0, 90), (-30, 0, 90)]  # nothing known: laid west of the head, heading east
    assert tf.place_along([], [0], 90) == []


def test_build_path_drops_jitter_and_the_formation_has_the_right_length_on_the_ground():
    lat, lon = 41.3, 69.2
    trail = [(lat - 0.0005, lon), (lat - 0.0010, lon), (lat - 0.0015, lon)]  # ~55 m steps to the south
    path = tf.build_path([(lat, lon), (lat + 0.00001, lon), *trail], lat, lon)
    assert len(path) == 4  # the 1 m jitter point is dropped
    built, heading, known = tf.build_formation(trail=trail, lat=lat, lon=lon, kind="electric", model="ПЭ-2у", wagon_kinds=["dump"] * 13)
    assert known and round(heading) == 0 and len(built) == 15
    first, last = built[0], built[-1]
    metres = ph.haversine_m(first[1], first[2], last[1], last[2])
    expected = tf.centre_distances([s[0] for s in built])[-1]
    assert abs(metres - expected) < 1.5, (metres, expected)  # drawn at the real size: ~250 m for a train of 13 cars
    unknown_built, _h, unknown = tf.build_formation(trail=[], lat=lat, lon=lon, kind="diesel", model="ТЭМ2", wagon_kinds=["dump"])
    assert not unknown and unknown_built[0][3] == tf.DEFAULT_HEADING


@pytest.mark.pg
@pytest.mark.asyncio
async def test_live_trains_are_assembled_from_gtk_wialon_and_the_track_and_a_master_sees_only_his_section():
    tag = uuid4().hex[:6]
    base = 500_000 + int(tag[:4], 16) % 90_000
    loco_gtk, train_gtk, cars = base, base, [base + 1, base + 2, base + 3]
    sec_a, sec_b = uuid4(), uuid4()
    loco, w1, w2, w3 = uuid4(), uuid4(), uuid4(), uuid4()
    unit = f"TF{tag}"
    now = datetime.now(UTC).replace(microsecond=0)
    lat, lon = 41.31, 69.21
    async with SessionFactory() as db:
        db.add_all([Section(id=sec_a, name=f"TA-{tag}"), Section(id=sec_b, name=f"TB-{tag}")])
        await db.flush()
        db.add_all([
            FixedAsset(id=loco, inv_number=f"TFL-{tag}", asset_type="locomotive", status="operational", section_id=sec_a),
            FixedAsset(id=w1, inv_number=f"TFW1-{tag}", asset_type="wagon", status="operational", section_id=sec_a),
            FixedAsset(id=w2, inv_number=f"TFW2-{tag}", asset_type="tank_car", status="operational", section_id=sec_b),
            FixedAsset(id=w3, inv_number=f"TFW3-{tag}", asset_type="wagon", status="operational", section_id=sec_a),
        ])
        await db.flush()
        db.add_all([GtkLocomotive(gtk_id=loco_gtk, name=f"TA {tag}", garage_number=tag, model_name="Тяговый агрегат ПЭ2М", is_active=True)]
                   + [GtkCarriage(gtk_id=c, name=f"TC{c}", is_active=True) for c in cars]
                   + [GtkTrain(gtk_id=train_gtk, number=tag, title="tf", begin_time=now - timedelta(hours=3), is_open=True),
                      WialonUnitRecord(unit_id=unit, name="U", lat=Decimal(str(lat)), lon=Decimal(str(lon)), speed=Decimal("12"), position_at=now, last_message_at=now)])
        await db.flush()
        db.add_all([
            GtkTrainMember(train_gtk_id=train_gtk, kind="locomotive", object_gtk_id=loco_gtk, is_main=True, ord=0, observed_from=now - timedelta(hours=3)),
            *[GtkTrainMember(train_gtk_id=train_gtk, kind="carriage", object_gtk_id=c, is_main=False, ord=i + 1, observed_from=now - timedelta(hours=3)) for i, c in enumerate(cars)],
            AssetSourceLink(asset_id=loco, source="gtk", external_id=str(loco_gtk), status="active"),
            AssetSourceLink(asset_id=loco, source="wialon", external_id=unit, status="active"),
            AssetSourceLink(asset_id=w1, source="gtk", external_id=str(cars[0]), status="active"),
            AssetSourceLink(asset_id=w2, source="gtk", external_id=str(cars[1]), status="active"),
        ])
        db.add_all([AssetPositionHistory(asset_id=loco, at=now - timedelta(minutes=5 * (i + 1)), lat=Decimal(str(lat - 0.0006 * (i + 1))), lon=Decimal(str(lon)), source="wialon") for i in range(4)])
        await db.commit()
    try:
        async with SessionFactory() as db:
            admin = SimpleNamespace(role="admin", section_id=None)
            mine = next(t for t in (await tf.live_trains(db, admin)).trains if t.gtk_train_id == train_gtk)
            assert (mine.loco_kind, mine.loco_inv_number, mine.wagons_count, mine.heading_known, mine.moving, mine.online) == ("electric", f"TFL-{tag}", 3, True, True, True)
            assert round(mine.heading) == 0  # the locomotive came from the south
            assert [(v.role, v.kind, v.ord) for v in mine.vehicles] == [("loco", "electric", 0), ("motor", "motor", -1), ("wagon", "dump", 1), ("wagon", "tank", 2), ("wagon", "dump", 3)]
            assert [v.label for v in mine.vehicles if v.role == "wagon"] == [f"TFW1-{tag}", f"TFW2-{tag}", f"TC{cars[2]}"]  # linked by inventory number, the unlinked one by its GTK name
            lats = [v.lat for v in mine.vehicles]
            assert lats == sorted(lats, reverse=True) and abs(lats[0] - lat) < 1e-9  # each next vehicle is further south
            assert mine.length_m > 80

            for who, expect_train, expect_hidden in (
                (SimpleNamespace(role="master", section_id=sec_a), True, [False, False, True, True]),
                (SimpleNamespace(role="master", section_id=sec_b), True, [True, True, False, True]),
                (SimpleNamespace(role="master", section_id=uuid4()), False, None),
            ):
                found = [t for t in (await tf.live_trains(db, who)).trains if t.gtk_train_id == train_gtk]
                assert bool(found) is expect_train
                if found:
                    assert [v.hidden for v in found[0].vehicles if v.role != "motor"] == expect_hidden
                    assert all(v.asset_id is None and v.label is None for v in found[0].vehicles if v.hidden)
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(AssetPositionHistory).where(AssetPositionHistory.asset_id == loco))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco, w1, w2])))
            await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id == train_gtk))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == train_gtk))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id.in_(cars)))
            await db.execute(delete(GtkLocomotive).where(GtkLocomotive.gtk_id == loco_gtk))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco, w1, w2, w3])))
            await db.execute(delete(Section).where(Section.id.in_([sec_a, sec_b])))
            await db.commit()
