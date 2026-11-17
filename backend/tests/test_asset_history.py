"""Position history and the asset history timeline (where was it, behind which traction unit, what was it doing)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.core.database import SessionFactory
from app.integrations.wialon_client import parse_track_messages
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.organization import Section
from app.models.position_history import AssetPositionHistory
from app.models.scales import ScalePost
from app.schemas import scales as scale_schemas
from app.services import asset_history, position_history as ph
from app.services import scales as scales_service

UTC = timezone.utc
T0 = datetime(2026, 11, 17, 8, 0, tzinfo=UTC)


# ── pure rules ─────────────────────────────────────────────────────────────────────────────────────────
def test_distance_and_the_store_rule():
    assert ph.haversine_m(41.0, 69.0, 41.0, 69.0) == 0
    assert 110_000 < ph.haversine_m(41.0, 69.0, 42.0, 69.0) < 112_000  # one degree of latitude
    a = ph.Fix(T0, 41.0, 69.0)
    assert ph.should_store(None, a)
    assert not ph.should_store(a, ph.Fix(T0 + timedelta(minutes=5), 41.0001, 69.0))  # 11 m, 5 min: parked
    assert ph.should_store(a, ph.Fix(T0 + timedelta(minutes=5), 41.002, 69.0))  # 222 m: moved
    assert ph.should_store(a, ph.Fix(T0 + timedelta(minutes=21), 41.0001, 69.0))  # heartbeat
    assert not ph.should_store(a, ph.Fix(T0 - timedelta(minutes=1), 42.0, 69.0))  # older than the stored point


def test_thin_keeps_movement_and_heartbeats_and_drops_bad_fixes():
    fixes = [ph.Fix(T0 + timedelta(seconds=10 * i), 41.0 + 0.0001 * i, 69.0) for i in range(60)]  # ~11 m every 10 s
    kept = ph.thin(fixes + [ph.Fix(T0, 0.0, 0.0), ph.Fix(T0, 95.0, 0.0)])
    assert 4 <= len(kept) <= 8 and kept[0].at == T0  # ~660 m over 10 min: a point per ~100 m
    parked = ph.thin([ph.Fix(T0 + timedelta(minutes=m), 41.0, 69.0) for m in range(0, 61, 5)])
    assert [p.at for p in parked] == [T0 + timedelta(minutes=m) for m in (0, 20, 40, 60)]


def test_wialon_track_messages_are_parsed_and_positionless_ones_skipped():
    payload = {"messages": [{"t": 1_700_000_000, "pos": {"y": 41.3, "x": 69.2, "s": 12}}, {"t": 1_700_000_010}, {"t": "x", "pos": {"y": 1, "x": 1}}, {"t": 1_700_000_020, "pos": {"y": 41.4, "x": 69.3}}]}
    parsed = parse_track_messages(payload)
    assert [(round(p[1], 1), round(p[2], 1), p[3]) for p in parsed] == [(41.3, 69.2, 12.0), (41.4, 69.3, None)]
    assert parse_track_messages(None) == [] and parse_track_messages({"messages": "no"}) == []


# ── database ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.pg
@pytest.mark.asyncio
async def test_live_recording_is_thinned_and_the_history_joins_trains_tracks_and_weighings():
    tag = uuid4().hex[:6]
    base = 600_000 + int(tag[:4], 16) % 90_000
    loco1_gtk, loco2_gtk, train1, train2 = base, base + 1, base, base + 1
    cars = [base + 10, base + 11]
    sec_a, sec_b = uuid4(), uuid4()
    loco1, loco2, wagon, other_wagon = uuid4(), uuid4(), uuid4(), uuid4()
    unit = f"U{tag}"
    now = datetime.now(UTC).replace(microsecond=0)
    t1, t2 = now - timedelta(hours=10), now - timedelta(hours=6)  # train 1 from t1 to t2, then train 2 from t2 (open)
    post = f"H{tag}"
    async with SessionFactory() as db:
        db.add_all([Section(id=sec_a, name=f"HA-{tag}"), Section(id=sec_b, name=f"HB-{tag}")])
        await db.flush()
        db.add_all([
            FixedAsset(id=loco1, inv_number=f"HL1-{tag}", asset_type="locomotive", status="operational", section_id=sec_a),
            FixedAsset(id=loco2, inv_number=f"HL2-{tag}", asset_type="diesel", status="operational", section_id=sec_a),
            FixedAsset(id=wagon, inv_number=f"HW-{tag}", asset_type="wagon", status="operational", section_id=sec_a),
            FixedAsset(id=other_wagon, inv_number=f"HO-{tag}", asset_type="wagon", status="operational", section_id=sec_b),
        ])
        await db.flush()
        db.add_all([GtkLocomotive(gtk_id=loco1_gtk, name=f"TA {tag}1", garage_number=f"{tag}1", is_active=True), GtkLocomotive(gtk_id=loco2_gtk, name=f"TEM {tag}2", garage_number=f"{tag}2", is_active=True)]
                   + [GtkCarriage(gtk_id=c, name=f"HC{c}", is_active=True) for c in cars]
                   + [GtkTrain(gtk_id=train1, number=f"{tag}1", title="поезд 1", begin_time=t1, is_open=False), GtkTrain(gtk_id=train2, number=f"{tag}2", title="поезд 2", begin_time=t2, is_open=True)])
        await db.flush()
        db.add_all([
            GtkTrainMember(train_gtk_id=train1, kind="locomotive", object_gtk_id=loco1_gtk, is_main=True, ord=0, observed_from=t1, observed_to=t2),
            GtkTrainMember(train_gtk_id=train1, kind="carriage", object_gtk_id=cars[0], is_main=False, ord=1, observed_from=t1, observed_to=t2),
            GtkTrainMember(train_gtk_id=train1, kind="carriage", object_gtk_id=cars[1], is_main=False, ord=2, observed_from=t1, observed_to=t2),
            GtkTrainMember(train_gtk_id=train2, kind="locomotive", object_gtk_id=loco2_gtk, is_main=True, ord=0, observed_from=t2),
            GtkTrainMember(train_gtk_id=train2, kind="carriage", object_gtk_id=cars[0], is_main=False, ord=1, observed_from=t2),
            AssetSourceLink(asset_id=loco1, source="gtk", external_id=str(loco1_gtk), status="active"),
            AssetSourceLink(asset_id=loco2, source="gtk", external_id=str(loco2_gtk), status="active"),
            AssetSourceLink(asset_id=wagon, source="gtk", external_id=str(cars[0]), status="active"),
            AssetSourceLink(asset_id=loco1, source="wialon", external_id=unit, status="active"),
        ])
        await db.commit()
    try:
        # live recording: the first fix is stored, a parked repeat is not, a real move is
        fix = lambda minutes, lat: SimpleNamespace(unit_id=unit, lat=Decimal(str(lat)), lon=Decimal("69.2"), position_at=t1 + timedelta(minutes=minutes), last_message_at=None, speed=Decimal("20"))  # noqa: E731
        async with SessionFactory() as db:
            assert await ph.record_wialon(db, [fix(1, 41.3000)], synced_at=now) == 1
            await db.commit()
            assert await ph.record_wialon(db, [fix(3, 41.30005)], synced_at=now) == 0  # 5 m: parked
            assert await ph.record_wialon(db, [fix(5, 41.3050)], synced_at=now) == 1  # ~550 m
            assert await ph.record_wialon(db, [SimpleNamespace(unit_id="unlinked-" + tag, lat=Decimal("41.1"), lon=Decimal("69.1"), position_at=t1, last_message_at=None, speed=None)], synced_at=now) == 0
            await db.commit()
            # more points inside train 1 (moving) and train 2 (standing) of loco 1 / loco 2
            db.add_all([AssetPositionHistory(asset_id=loco1, at=t1 + timedelta(minutes=10 + 5 * i), lat=Decimal(str(41.31 + 0.01 * i)), lon=Decimal("69.2"), speed=Decimal("25"), source="wialon") for i in range(6)])
            db.add_all([AssetPositionHistory(asset_id=loco2, at=t2 + timedelta(minutes=10 * i), lat=Decimal("41.4"), lon=Decimal("69.4"), speed=Decimal("0"), source="wialon") for i in range(4)])
            await db.commit()
            assert (await db.execute(select(func.count()).select_from(AssetPositionHistory).where(AssetPositionHistory.asset_id == loco1))).scalar_one() == 8

        # a weighing of the wagon's train 1 at the scales
        async with SessionFactory() as db:
            await scales_service.ingest(db, scale_schemas.ScalesIngestIn(
                post=post, tare_default_t=49, capacity_norm_t=105,
                trains=[scale_schemas.ScaleTrainIn(src_id=1, loco_number=f"{tag}1", declared_wagons=3, reported_weight_t=400.0, started_at=(t1 + timedelta(minutes=30)).replace(tzinfo=None) + timedelta(hours=5), finished_at=(t1 + timedelta(minutes=38)).replace(tzinfo=None) + timedelta(hours=5))],
                weighings=[scale_schemas.ScaleWeighingIn(src_id=i + 1, train_src_id=1, position=p, gross_t=tare + net, tare_t=tare, net_t=net, capacity_t=105, weighed_at=(t1 + timedelta(minutes=30)).replace(tzinfo=None) + timedelta(hours=5))
                           for i, (p, tare, net) in enumerate([(1, 126, 44), (2, 126, 44), (3, 49, 100), (4, 49, 90)])],
            ))

        admin = SimpleNamespace(role="admin", section_id=None)
        async with SessionFactory() as db:
            wh = await asset_history.asset_history(db, admin, asset_id=wagon, carriage_gtk_id=None, days=3)
            assert wh.kind == "wagon" and wh.asset and wh.asset.inv_number == f"HW-{tag}" and wh.gtk_carriage and wh.gtk_carriage.name == f"HC{cars[0]}"
            assert [(s.train_gtk_id, s.is_open, s.cars, s.loco_inv_number) for s in wh.segments] == [(train2, True, 1, f"HL2-{tag}"), (train1, False, 2, f"HL1-{tag}")]  # newest first
            s2, s1 = wh.segments
            assert (s1.activity, s1.points) == ("moving", 8) and s1.km and s1.km > 4 and s1.max_speed == 25.0  # loco 1 drove ~5.5 km during train 1
            assert (s2.activity, s2.points) == ("standing", 4) and (s2.km or 0) < 0.1
            assert {p.source for p in wh.track} == {"loco"} and len(wh.track) == 12 and wh.track == sorted(wh.track, key=lambda p: p.at)
            assert wh.current and wh.current.in_train and wh.current.loco_label == s2.loco_label and (wh.current.lat, wh.current.lon) == (41.4, 69.4)
            assert [(b.label.split()[0], b.segments) for b in wh.by_loco] == [("TEM", 1), ("TA", 1)] or len(wh.by_loco) == 2
            assert wh.by_loco[0].hours > wh.by_loco[1].hours - 0.1 and wh.stats.segments == 2 and wh.stats.distinct_partners == 2
            assert len(wh.trips) == 1 and wh.trips[0].post_code == post and s1.trips == 1 and s2.trips == 0 and wh.stats.trips == 1
            assert wh.gtk_history_from is not None and wh.track_from is not None

            lh = await asset_history.asset_history(db, admin, asset_id=loco1, carriage_gtk_id=None, days=3)
            assert lh.kind == "locomotive" and lh.gtk_loco and [(s.train_gtk_id, s.cars) for s in lh.segments] == [(train1, 2)]
            assert {w.label for w in lh.segments[0].wagons} == {f"HW-{tag}", f"HC{cars[1]}"}  # the linked wagon by inventory, the other by its GTK name
            assert {p.source for p in lh.track} == {"own"} and len(lh.track) == 8 and lh.segments[0].activity == "moving" and lh.stats.distinct_partners == 2
            assert len(lh.trips) == 1 and lh.trips[0].cars is not None

            unlinked = await asset_history.asset_history(db, admin, asset_id=None, carriage_gtk_id=cars[1], days=3)
            assert unlinked.asset is None and unlinked.kind == "wagon" and [s.train_gtk_id for s in unlinked.segments] == [train1]

            master_b = SimpleNamespace(role="master", section_id=sec_b)
            master_a = SimpleNamespace(role="master", section_id=sec_a)
            for who, kwargs in ((master_b, dict(asset_id=wagon, carriage_gtk_id=None)), (master_a, dict(asset_id=None, carriage_gtk_id=cars[1])), (master_a, dict(asset_id=other_wagon, carriage_gtk_id=None))):
                with pytest.raises(HTTPException) as hidden:
                    await asset_history.asset_history(db, who, days=3, **kwargs)
                assert hidden.value.status_code == 404  # another section / an unlinked wagon is invisible to a master
            assert (await asset_history.asset_history(db, master_a, asset_id=wagon, carriage_gtk_id=None, days=3)).segments
            with pytest.raises(HTTPException) as nothing:
                await asset_history.asset_history(db, admin, asset_id=None, carriage_gtk_id=None, days=3)
            assert nothing.value.status_code == 422
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(ScalePost).where(ScalePost.code == post))
            await db.execute(delete(AssetPositionHistory).where(AssetPositionHistory.asset_id.in_([loco1, loco2, wagon])))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco1, loco2, wagon])))
            await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id.in_([train1, train2])))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id.in_([train1, train2])))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id.in_(cars)))
            await db.execute(delete(GtkLocomotive).where(GtkLocomotive.gtk_id.in_([loco1_gtk, loco2_gtk])))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco1, loco2, wagon, other_wagon])))
            await db.execute(delete(Section).where(Section.id.in_([sec_a, sec_b])))
            await db.commit()
