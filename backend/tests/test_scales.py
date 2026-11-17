"""Weighing-scale feed: pure matching rules, token guard, and the database round trip (ingest, re-match, corrections, work)."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.scales import ScaleCorrection, ScalePost, ScaleTrain, ScaleTrainCarriage, ScaleWeighing
from app.routers.scales import require_ingest_token
from app.schemas import scales as schemas
from app.services import scales as service
from app.services import scales_matching as m

UTC = timezone.utc
T0 = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


def member(train, kind, obj, *, main=False, ord=1, start=T0 - timedelta(hours=2), end=None):
    return m.Member(train, kind, obj, main, ord, start, end)


# ── pure rules ─────────────────────────────────────────────────────────────────────────────────────────
def test_loco_number_is_trimmed_and_keys_try_exact_then_without_leading_zeros():
    assert m.normalize_loco_number(" 07 4 ") == "074" and m.normalize_loco_number("   ") is None and m.normalize_loco_number(None) is None
    assert m.loco_keys("074") == ["074", "74"] and m.loco_keys("360") == ["360"] and m.loco_keys("000") == ["000"]


def test_a_unit_with_a_heavy_tare_is_a_traction_unit_and_the_rest_are_dump_cars():
    assert m.unit_kind(m.Unit(Decimal(170), Decimal("126"), Decimal(44)), 100) == "traction"
    assert m.unit_kind(m.Unit(Decimal(150), Decimal("49"), Decimal(101)), 100) == "dump"
    assert m.unit_kind(m.Unit(None, None, None), 100) == "dump"


def _units(*nets, tare=49, traction=2):
    return [m.Unit(Decimal(170), Decimal(126), Decimal(44), None)] * traction + [m.Unit(Decimal(n) + tare, Decimal(tare), Decimal(n), Decimal(105)) for n in nets]


def test_cargo_is_the_dump_cars_net_without_the_traction_units_and_flags_are_raised():
    s = m.summarize_train(_units(100, 110, 120), tare_min=100, tare_default=Decimal(49), declared_wagons=5, reported_weight_t=Decimal(2000), offset_t=None)
    assert (s.dump_count, s.traction_count, s.net_total_t, s.net_source) == (3, 2, Decimal("330.00"), "weighings")
    assert set(s.flags) == {"default_tare", "overload"}  # 110 and 120 t exceed the 105 t capacity


def test_missing_wagon_rows_use_the_learned_offset_and_partial_rows_are_estimated_not_trusted():
    none = m.summarize_train([], tare_min=100, tare_default=None, declared_wagons=15, reported_weight_t=Decimal(1650), offset_t=Decimal(250))
    assert (none.net_total_t, none.net_source) == (Decimal("1400.00"), "estimated") and set(none.flags) == {"no_wagon_rows", "estimated_net"}
    partial = m.summarize_train(_units(100, 100), tare_min=100, tare_default=None, declared_wagons=15, reported_weight_t=Decimal(1650), offset_t=Decimal(250))
    assert partial.net_source == "estimated" and "partial_wagon_rows" in partial.flags
    unknown = m.summarize_train([], tare_min=100, tare_default=None, declared_wagons=15, reported_weight_t=Decimal(1650), offset_t=None)
    assert unknown.net_total_t is None and unknown.net_source is None
    assert m.estimate_offset([Decimal(1)] * 5) is None and m.estimate_offset([Decimal(200)] * 30) == Decimal("200.0")


def test_negative_net_is_flagged():
    s = m.summarize_train(_units(-5, 100), tare_min=100, tare_default=None, declared_wagons=4, reported_weight_t=None, offset_t=None)
    assert "negative_net" in s.flags


def test_a_gtk_traction_hint_keeps_a_real_dump_car_with_a_heavy_tare_that_a_threshold_would_drop():
    units = [
        m.Unit(Decimal(170), Decimal(126), Decimal(44), None, 1), m.Unit(Decimal(170), Decimal(124), Decimal(46), None, 2),
        m.Unit(Decimal(205), Decimal(105), Decimal(100), Decimal(105), 3),  # a dump car whose tare was really weighed
        m.Unit(Decimal(149), Decimal(49), Decimal(100), Decimal(105), 4), m.Unit(Decimal(149), Decimal(49), Decimal(100), Decimal(105), 5),
    ]
    common = dict(tare_min=100, tare_default=None, declared_wagons=5, reported_weight_t=None, offset_t=None)
    by_threshold = m.summarize_train(units, **common)
    assert (by_threshold.traction_count, by_threshold.dump_count, by_threshold.net_total_t) == (3, 2, Decimal("200.00"))
    hinted = m.summarize_train(units, traction_hint=2, **common)
    assert (hinted.traction_count, hinted.dump_count, hinted.net_total_t) == (2, 3, Decimal("300.00"))
    assert hinted.kinds == ("traction", "traction", "dump", "dump", "dump") and "traction_inferred" in hinted.flags
    assert "traction_inferred" not in by_threshold.flags and by_threshold.kinds == ("traction",) * 3 + ("dump",) * 2


def test_the_gtk_train_is_the_one_where_the_locomotive_overlaps_the_window_longest_and_tolerance_helps():
    win = m.window(T0, T0 + timedelta(minutes=10), timedelta(minutes=15))
    members = [
        member(1, "locomotive", 50, main=True, start=T0 - timedelta(hours=5), end=T0 - timedelta(hours=1)),  # ended before
        member(2, "locomotive", 50, main=True, start=T0 - timedelta(hours=1)),  # open now
        member(3, "locomotive", 51, main=True, start=T0 - timedelta(hours=1)),  # another locomotive
        member(4, "locomotive", 50, main=False, start=T0 - timedelta(hours=1)),  # not the main one
    ]
    assert m.find_gtk_train({50}, members, win) == 2 and m.find_gtk_train({99}, members, win) is None
    just_after = [member(5, "locomotive", 50, main=True, start=T0 + timedelta(minutes=20))]
    assert m.find_gtk_train({50}, just_after, win) == 5  # observed within the 15 min tolerance of the window end
    assert m.find_gtk_train({50}, just_after, m.window(T0, T0, timedelta(0))) is None


def test_carriages_are_those_that_stood_in_the_train_during_the_window_once_each():
    win = m.window(T0, T0 + timedelta(minutes=10), timedelta(0))
    members = [
        member(7, "carriage", 1, ord=2), member(7, "carriage", 2, ord=1),
        member(7, "carriage", 3, ord=3, start=T0 - timedelta(days=2), end=T0 - timedelta(days=1)),  # left before
        member(7, "carriage", 2, ord=9, start=T0 - timedelta(days=9), end=T0 - timedelta(hours=1)),  # same car, older row
        member(8, "carriage", 4, ord=1),  # another train
    ]
    assert [c.object_gtk_id for c in m.carriages_in_train(7, members, win)] == [2, 1]
    assert m.carriages_in_train(7, members, None) == []


def test_dump_cars_are_paired_with_gtk_carriages_in_sequence_and_only_when_the_counts_agree():
    units = [m.Unit(Decimal(150), Decimal(49), Decimal(n), None, pos, f"w{pos}") for pos, n in ((5, 90), (3, 100), (4, 110))]  # unsorted on purpose
    cars = [member(7, "carriage", 30, ord=3), member(7, "carriage", 10, ord=1), member(7, "carriage", 20, ord=2)]
    asc = m.assign_units_to_carriages(units, cars)
    assert [(c.object_gtk_id, u.net) for c, u in asc] == [(10, Decimal(100)), (20, Decimal(110)), (30, Decimal(90))]
    desc = m.assign_units_to_carriages(units, cars, order="desc")
    assert [(c.object_gtk_id, u.net) for c, u in desc] == [(30, Decimal(100)), (20, Decimal(110)), (10, Decimal(90))]
    assert m.assign_units_to_carriages(units, cars[:2]) == [] and m.assign_units_to_carriages([], cars) == []


def test_suggestions_rank_the_gtk_locomotives_working_at_that_time():
    win = m.window(T0, T0 + timedelta(minutes=10), timedelta(0))
    members = [
        member(1, "locomotive", 50, main=True, start=T0 - timedelta(hours=1)),
        member(2, "locomotive", 51, main=True, start=T0 + timedelta(minutes=5)),
        member(3, "locomotive", 52, main=True, start=T0 + timedelta(hours=3)),
    ]
    assert [(s[0], s[1]) for s in m.suggest_locos(members, win)] == [(50, 1), (51, 2)]


def _resolve(number, **kw):
    base = dict(aliases={}, garage_index={}, asset_by_loco_gtk={}, loco_gtk_by_asset={})
    base.update(kw)
    return m.resolve_loco(number, **base)


def test_an_operator_alias_wins_over_the_gtk_garage_number_and_zeros_are_forgiven():
    a1, a2 = uuid4(), uuid4()
    gtk = dict(garage_index={"074": [180], "360": [213]}, asset_by_loco_gtk={180: a1, 213: a2}, loco_gtk_by_asset={a1: 180, a2: 213})
    assert _resolve("074", **gtk).asset_id == a1 and _resolve("074", **gtk).method == "gtk_garage"
    assert _resolve("74", **{**gtk, "garage_index": {"74": [180]}}).gtk_ids == {180}
    assert _resolve("0360", **gtk).gtk_ids == {213}  # leading zero typed by the operator
    aliased = _resolve("074", aliases={"074": a2}, **gtk)
    assert (aliased.asset_id, aliased.gtk_ids, aliased.method) == (a2, frozenset({213}), "alias")
    assert _resolve("3202", **gtk) == m.LocoResolution(None, frozenset(), None) and _resolve(None, **gtk).method is None


def _match(**kw):
    base = dict(
        number="360", started_at=T0, finished_at=T0 + timedelta(minutes=10), dump_count=2, excluded=False, forced_gtk_train=None,
        tolerance=timedelta(minutes=15), members=[], aliases={}, garage_index={}, asset_by_loco_gtk={}, loco_gtk_by_asset={},
    )
    base.update(kw)
    return m.match_train(**base)


def test_match_train_statuses():
    loco = uuid4()
    gtk = dict(garage_index={"360": [213]}, asset_by_loco_gtk={213: loco}, loco_gtk_by_asset={loco: 213})
    members = [member(9, "locomotive", 213, main=True), member(9, "carriage", 1, ord=1), member(9, "carriage", 2, ord=2)]
    ok = _match(members=members, **gtk)
    assert (ok.status, ok.method, ok.loco_asset_id, ok.gtk_train_id, len(ok.carriages), ok.flags) == ("ok", "gtk_garage", loco, 9, 2, [])
    assert _match(members=members, dump_count=3, **gtk).flags == ["count_mismatch"]
    assert _match(members=members, excluded=True, **gtk).status == "excluded"
    assert _match(number="3202", members=members, **gtk).status == "no_loco"
    assert _match(members=[], **gtk).status == "no_gtk_train"  # known locomotive, no GTK train at that time (history gap)
    forced = _match(number="3202", members=members, forced_gtk_train=9, **gtk)
    assert (forced.status, forced.method, forced.gtk_train_id) == ("ok", "forced", 9)
    assert _match(number=None, started_at=None, finished_at=None, members=members, **gtk).status == "no_loco"


# ── the ingest guard ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_the_ingest_endpoint_is_closed_without_a_configured_token_and_accepts_only_the_right_one(monkeypatch):
    request = SimpleNamespace(headers={})
    monkeypatch.setattr(settings, "scales_ingest_token", None)
    for header in (None, "Bearer anything"):
        with pytest.raises(HTTPException) as closed:
            await require_ingest_token(request, header, None)
        assert closed.value.status_code == 401
    monkeypatch.setattr(settings, "scales_ingest_token", SecretStr("s3cret-token"))
    with pytest.raises(HTTPException):
        await require_ingest_token(request, "Bearer wrong", None)
    with pytest.raises(HTTPException):
        await require_ingest_token(request, None, None)
    assert await require_ingest_token(request, "Bearer s3cret-token", None) is None
    assert await require_ingest_token(request, None, "s3cret-token") is None
    with pytest.raises(HTTPException) as big:
        await require_ingest_token(SimpleNamespace(headers={"content-length": str(5 * 1024 * 1024)}), "Bearer s3cret-token", None)
    assert big.value.status_code == 413


# ── the database round trip ────────────────────────────────────────────────────────────────────────────
def _train(src, number, start, *, declared=5, weight=1600.0, finished=None):
    return schemas.ScaleTrainIn(
        src_id=src, loco_number=number, declared_wagons=declared, reported_weight_t=weight, started_at=start,
        finished_at=finished or start + timedelta(minutes=8),
    )


def _w(src, train_src, pos, tare, net, when):
    return schemas.ScaleWeighingIn(
        src_id=src, train_src_id=train_src, position=pos, gross_t=tare + net, tare_t=tare, net_t=net, capacity_t=105, weighed_at=when
    )


@pytest.mark.pg
@pytest.mark.asyncio
async def test_ingest_matches_to_gtk_is_idempotent_and_every_correction_is_re_applied_to_the_past():
    tag = uuid4().hex[:6]
    code, garage = f"Z{tag}", f"G{tag}".upper()
    base = 800_000 + int(tag[:4], 16) % 90_000
    loco_gtk, train_gtk = base, base
    car_gtk = [base + 1, base + 2, base + 3]
    loco_asset, w1, w2, w3 = uuid4(), uuid4(), uuid4(), uuid4()
    other_loco = uuid4()
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=3)
    async with SessionFactory() as db:
        db.add_all([
            FixedAsset(id=loco_asset, inv_number=f"SC-L-{tag}", asset_type="locomotive", status="operational"),
            FixedAsset(id=other_loco, inv_number=f"SC-L2-{tag}", asset_type="diesel", status="operational"),
            FixedAsset(id=w1, inv_number=f"SC-W1-{tag}", asset_type="wagon", status="operational"),
            FixedAsset(id=w2, inv_number=f"SC-W2-{tag}", asset_type="wagon", status="operational"),
            FixedAsset(id=w3, inv_number=f"SC-W3-{tag}", asset_type="wagon", status="operational"),
        ])
        await db.flush()
        db.add_all([GtkLocomotive(gtk_id=loco_gtk, name=f"TA {garage}", garage_number=garage, is_active=True)]
                   + [GtkCarriage(gtk_id=c, name=f"C{c}", is_active=True) for c in car_gtk]
                   + [GtkTrain(gtk_id=train_gtk, number=garage, title="test", begin_time=start - timedelta(hours=1), is_open=True)])
        await db.flush()
        db.add_all([
            GtkTrainMember(train_gtk_id=train_gtk, kind="locomotive", object_gtk_id=loco_gtk, is_main=True, ord=0, observed_from=start - timedelta(hours=1)),
            *[GtkTrainMember(train_gtk_id=train_gtk, kind="carriage", object_gtk_id=c, is_main=False, ord=i + 1, observed_from=start - timedelta(hours=1))
              for i, c in enumerate(car_gtk)],
            AssetSourceLink(asset_id=loco_asset, source="gtk", external_id=str(loco_gtk), status="active"),
            AssetSourceLink(asset_id=w1, source="gtk", external_id=str(car_gtk[0]), status="active"),
            AssetSourceLink(asset_id=w2, source="gtk", external_id=str(car_gtk[1]), status="active"),  # the third car stays unlinked
        ])
        await db.commit()
    admin = SimpleNamespace(id=None, role="admin", section_id=None)
    payload = schemas.ScalesIngestIn(
        post=code, tare_default_t=49, capacity_norm_t=105,
        trains=[_train(1, garage, start), _train(2, f"X{tag}".upper(), start + timedelta(minutes=30)), _train(3, garage, start + timedelta(hours=1), declared=15, weight=1650)],
        weighings=[
            _w(11, 1, 1, 126, 44, start), _w(12, 1, 2, 126, 44, start),
            _w(13, 1, 3, 120, 100, start), _w(14, 1, 4, 49, 110, start), _w(15, 1, 5, 49, 90, start),
        ],
    )
    try:
        async with SessionFactory() as db:
            first = await service.ingest(db, payload)
        assert (first.trains_changed, first.weighings_changed, first.weighings_orphaned) == (3, 5, 0)
        async with SessionFactory() as db:
            again = await service.ingest(db, payload)  # nothing changed: nothing is touched
        assert (again.trains_changed, again.weighings_changed) == (0, 0)

        async with SessionFactory() as db:
            by_src = {t.src_id: t for t in (await db.execute(select(ScaleTrain).join(ScalePost).where(ScalePost.code == code))).scalars().all()}
            good = by_src[1]
            assert (good.match_status, good.match_method, good.loco_asset_id, good.gtk_train_id) == ("ok", "gtk_garage", loco_asset, train_gtk)
            assert (good.dump_count, good.traction_count, good.net_total_t, good.net_source) == (3, 2, Decimal("300.00"), "weighings")
            # unit 3 has a 120 t tare (a threshold would call it traction) but GTK says the train has 3 cars: 5 units - 3 = 2 traction
            assert (good.carriages_total, good.carriages_linked) == (3, 2) and "traction_inferred" in good.flags and "overload" in good.flags
            assert by_src[2].match_status == "no_loco"
            assert by_src[3].match_status == "ok" and "no_wagon_rows" in by_src[3].flags and by_src[3].net_total_t is None  # no offset learned yet
            kinds = (await db.execute(select(ScaleWeighing.unit_kind).where(ScaleWeighing.train_id == good.id).order_by(ScaleWeighing.position))).scalars().all()
            assert kinds == ["traction", "traction", "dump", "dump", "dump"]
            linked = {r.asset_id for r in (await db.execute(select(ScaleTrainCarriage).where(ScaleTrainCarriage.train_id == good.id))).scalars().all()}
            assert linked == {w1, w2, None}

            status_view = await service.get_status(db)
            post = next(p for p in status_view.posts if p.code == code)
            assert post.health == "ok" and post.collector == "ok" and post.unmatched == 1 and post.trains_24h == 3
            listing = await service.list_trains(db, post=code, match_status="no_loco", flag=None, q=None, date_from=None, date_to=None,
                                               sort_by="started_at", descending=True, limit=10, offset=0)
            assert [t.src_id for t in listing.items] == [2]
            with pytest.raises(HTTPException):
                await service.list_trains(db, post=code, match_status=None, flag=None, q=None, date_from=None, date_to=None,
                                          sort_by="nope", descending=True, limit=10, offset=0)

            suggestions = await service.list_unmatched(db, limit=50, offset=0)
            mine = next(i for i in suggestions.items if i.src_id == 2 and i.post_code == code)
            # GTK locomotives working at that time are proposed, best overlap first (on a busy database ours may not be in the top 3)
            assert mine.candidates and all(c.overlap_min > 0 for c in mine.candidates)

            work_w = await service.asset_work(db, w1, date.today() - timedelta(days=2), date.today())
            # two trips (the second train lost its wagon rows: the car did travel, its tonnes are unknown); 300 t over 3 dump cars
            assert (work_w.kind, work_w.trips, work_w.tonnes) == ("wagon", 2, Decimal("100.00"))
            assert work_w.exact_share == 0.5  # train 1 paired the car's own weighing, train 3 (no wagon rows) cannot
            # each car got ITS OWN cargo by GTK order: car 1 = position 3 (100 t), car 2 = position 4 (110 t)
            work_w2 = await service.asset_work(db, w2, date.today() - timedelta(days=2), date.today())
            assert work_w2.tonnes == Decimal("110.00")
            own = {c.carriage_gtk_id: (c.unit_position, c.net_t) for c in (await db.execute(select(ScaleTrainCarriage).where(ScaleTrainCarriage.train_id == good.id))).scalars().all()}
            assert own == {car_gtk[0]: (3, Decimal("100.00")), car_gtk[1]: (4, Decimal("110.00")), car_gtk[2]: (5, Decimal("90.00"))}

            # the ledger: WHICH wagon carried HOW MUCH, WHEN, behind WHICH locomotive
            from app.services import scales_trips as trips

            none = dict(q=None, date_from=None, date_to=None, post=None, cargo_code=None, only_linked=False)
            ledger = await trips.wagon_trips(db, asset_id=w2, sort_by="started_at", descending=True, limit=10, offset=0, **none)
            assert [(r.inv_number, r.tonnes, r.basis, r.position, r.loco_inv_number) for r in ledger.items] == [
                (f"SC-W2-{tag}", None, "unknown", None, f"SC-L-{tag}"),  # train 3 lost its wagon rows and no offset is learned yet
                (f"SC-W2-{tag}", Decimal("110.00"), "own", 4, f"SC-L-{tag}"),  # train 1: this car's own weighing
            ]
            assert (ledger.total, ledger.wagons_total, ledger.tonnes_total) == (2, 1, Decimal("110.00"))
            unlinked = await trips.wagon_trips(db, asset_id=None, sort_by="tonnes", descending=True, limit=10, offset=0, **{**none, "q": f"C{car_gtk[2]}"})
            assert [(r.asset_id, r.gtk_name, r.tonnes, r.basis) for r in unlinked.items][0] == (None, f"C{car_gtk[2]}", Decimal("90.00"), "own")  # an unlinked wagon is still visible
            future = await trips.wagon_trips(db, asset_id=w2, sort_by="started_at", descending=True, limit=10, offset=0, **{**none, "date_from": date.today() + timedelta(days=1)})
            assert future.total == 0
            totals = await trips.wagon_totals(db, sort_by="tonnes", descending=True, limit=10, offset=0, **{**none, "q": "SC-W"})
            assert [(r.inv_number, r.trips, r.tonnes, r.own_trips) for r in totals.items][:2] == [
                (f"SC-W2-{tag}", 2, Decimal("110.00"), 1), (f"SC-W1-{tag}", 2, Decimal("100.00"), 1)
            ] and totals.total == 2 and totals.trips_total == 4
            for bad in ("nope",):
                with pytest.raises(HTTPException):
                    await trips.wagon_totals(db, sort_by=bad, descending=True, limit=10, offset=0, **none)
            sheet = await trips.wagon_trips_csv(db, asset_id=w2, **none)
            lines = sheet.lstrip("﻿").splitlines()
            assert sheet.startswith("﻿") and lines[0].startswith("Дата и время;Весы;Вагон") and len(lines) == 3
            assert f"SC-W2-{tag}" in sheet and "110,00" in sheet and "взвешивание вагона" in sheet
            work_l = await service.asset_work(db, loco_asset, date.today() - timedelta(days=2), date.today())
            assert (work_l.kind, work_l.trips, work_l.tonnes) == ("locomotive", 2, Decimal("300.00"))
            with pytest.raises(HTTPException):
                await service.asset_work(db, uuid4(), date.today(), date.today())

        # operator corrections: alias a mistyped number to a locomotive, exclude a train, force a GTK train
        async with SessionFactory() as db:
            wrong = f"X{tag}".upper()
            with pytest.raises(HTTPException):
                await service.create_correction(db, admin, schemas.CorrectionCreate(kind="loco_alias", loco_number=wrong, asset_id=w1))  # not a locomotive
            alias = await service.create_correction(db, admin, schemas.CorrectionCreate(kind="loco_alias", loco_number=wrong, asset_id=loco_asset, note="typo"))
            assert alias.asset_inv_number == f"SC-L-{tag}"
            t2_id = (await db.execute(select(ScaleTrain.id).join(ScalePost).where(ScalePost.code == code, ScaleTrain.src_id == 2))).scalar_one()

            async def fresh(train_id):
                return (await db.execute(select(ScaleTrain).where(ScaleTrain.id == train_id).execution_options(populate_existing=True))).scalar_one()

            t2 = await fresh(t2_id)
            assert (t2.match_status, t2.match_method, t2.loco_asset_id) == ("ok", "alias", loco_asset)  # the past data was corrected at once
            await service.create_correction(db, admin, schemas.CorrectionCreate(kind="loco_alias", loco_number=wrong, asset_id=other_loco))  # replaces
            assert len([c for c in await service.list_corrections(db) if c.loco_number == wrong]) == 1
            t2 = await fresh(t2_id)
            assert t2.match_status == "no_gtk_train" and t2.loco_asset_id == other_loco  # that diesel has no GTK train at the time

            t3_id = (await db.execute(select(ScaleTrain.id).join(ScalePost).where(ScalePost.code == code, ScaleTrain.src_id == 3))).scalar_one()
            await service.create_correction(db, admin, schemas.CorrectionCreate(kind="train_exclude", train_id=t3_id))
            t3 = await fresh(t3_id)
            assert t3.match_status == "excluded" and t3.carriages_total == 0
            exclude = next(c for c in await service.list_corrections(db) if c.kind == "train_exclude")
            await service.end_correction(db, exclude.id)
            t3 = await fresh(t3_id)
            assert t3.match_status == "ok"  # undone: the same raw data is matched again

            await service.create_correction(db, admin, schemas.CorrectionCreate(kind="train_gtk", train_id=t2_id, gtk_train_id=train_gtk))
            t2 = await fresh(t2_id)
            assert (t2.match_status, t2.match_method, t2.carriages_total) == ("ok", "forced", 3)

        # a later GTK link reaches already stored trains with one pass: link the third car, then re-match
        async with SessionFactory() as db:
            db.add(AssetSourceLink(asset_id=w3, source="gtk", external_id=str(car_gtk[2]), status="active"))
            await db.commit()
        async with SessionFactory() as db:
            await service.rematch_all(db)
            good = (await db.execute(select(ScaleTrain).join(ScalePost).where(ScalePost.code == code, ScaleTrain.src_id == 1))).scalar_one()
            assert (good.carriages_total, good.carriages_linked) == (3, 3)

        # an operator edit of one wagon row changes the cargo and re-matches only that train
        edited = payload.model_copy(deep=True)
        edited.weighings[2].net_t = 80.0
        async with SessionFactory() as db:
            result = await service.ingest(db, edited)
            assert (result.trains_changed, result.weighings_changed) == (0, 1)
            good = (await db.execute(select(ScaleTrain).join(ScalePost).where(ScalePost.code == code, ScaleTrain.src_id == 1))).scalar_one()
            assert good.net_total_t == Decimal("280.00")
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(ScaleCorrection).where(ScaleCorrection.created_by.is_(None), ScaleCorrection.note.in_(["typo"])))
            await db.execute(delete(ScaleCorrection).where(ScaleCorrection.asset_id.in_([loco_asset, other_loco])))
            await db.execute(delete(ScaleCorrection).where(ScaleCorrection.train_id.in_(select(ScaleTrain.id).join(ScalePost).where(ScalePost.code == code))))
            await db.execute(delete(ScalePost).where(ScalePost.code == code))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco_asset, w1, w2, w3])))
            await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id == train_gtk))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == train_gtk))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id.in_(car_gtk)))
            await db.execute(delete(GtkLocomotive).where(GtkLocomotive.gtk_id == loco_gtk))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco_asset, other_loco, w1, w2, w3])))
            await db.commit()


@pytest.mark.pg
@pytest.mark.asyncio
async def test_the_cargo_of_trains_without_wagon_rows_is_estimated_from_the_learned_offset():
    tag = uuid4().hex[:6]
    code = f"Y{tag}"
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(days=2)
    trains, weighings = [], []
    for i in range(1, 26):  # 25 complete trains: «Вес» exceeds the real net by 190 t every time
        when = start + timedelta(minutes=10 * i)
        trains.append(_train(i, f"N{i}", when, declared=3, weight=float(190 + 300)))
        weighings += [_w(100 * i + 1, i, 1, 126, 44, when), _w(100 * i + 2, i, 2, 49, 100, when), _w(100 * i + 3, i, 3, 49, 100, when), _w(100 * i + 4, i, 4, 49, 100, when)]
    trains.append(_train(900, "N900", start + timedelta(hours=9), declared=15, weight=1000.0))  # wagon rows lost
    try:
        async with SessionFactory() as db:
            await service.ingest(db, schemas.ScalesIngestIn(post=code, trains=trains, weighings=weighings))
        async with SessionFactory() as db:
            lost = (await db.execute(select(ScaleTrain).join(ScalePost).where(ScalePost.code == code, ScaleTrain.src_id == 900))).scalar_one()
            assert lost.net_source == "estimated" and lost.net_total_t == Decimal("810.00") and "estimated_net" in lost.flags
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(ScalePost).where(ScalePost.code == code))
            await db.commit()
