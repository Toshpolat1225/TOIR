"""GTK GPS sync + the GPS comparison page on a real PostgreSQL (the GTK side is a stub that serves a track for any asked window)."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.core.database import SessionFactory
from app.integrations.gtk_client import GtkLoginError
from app.integrations.gtk_gps_client import GpsPoint, GtkTrack
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk_gps import GtkGpsDay, GtkGpsRun, GtkGpsUnit
from app.models.organization import Section
from app.models.position_history import AssetPositionHistory
from app.models.wialon_units import WialonUnitRecord
from app.services import gps_compare as cmp
from app.services import gps_overview as overview
from app.services import gtk_gps

UTC = timezone.utc
LON = 69.57


def lat_of(i: int) -> float:
    return 40.80 + 0.001 * i  # ~111 m per step


def seed_points(now: datetime, n: int = 36):
    """n points 10 minutes apart ending 5 minutes ago, moving north ~111 m per step."""
    return [(now - timedelta(minutes=5 + 10 * (n - 1 - i)), lat_of(i)) for i in range(n)]


class FakeGtk:
    """Stands in for GtkGpsClient: `vehicles` and a `track` that returns the points of the asked LOCAL window."""

    def __init__(self, units, points_by_id, login_error=False):
        self.units, self.points_by_id, self.login_error = units, points_by_id, login_error

    def __call__(self, *_a, **_k):
        return self

    async def __aenter__(self):
        if self.login_error:
            raise GtkLoginError("GTK login failed")
        return self

    async def __aexit__(self, *_):
        return None

    async def vehicles(self):
        return self.units

    async def track(self, vehicle_id, local_from, local_to, **_):
        pts = [p for p in self.points_by_id.get(vehicle_id, []) if local_from <= (p.at + timedelta(hours=5)).replace(tzinfo=None) <= local_to]
        metres = sum(cmp.haversine_m(a.lat, a.lon, b.lat, b.lon) for a, b in zip(pts, pts[1:])) * 0.95  # GTK filters a little
        return GtkTrack(pts, round(metres), {"noreasonidle": 3} if pts else {})


def unit(gtk_id, lat, at, speed=0.0, name="X"):
    return {"gtk_id": gtk_id, "name": name, "garage_number": name, "model_name": "ТЭМ2", "vehicle_type_id": 2, "enterprise_id": 1,
            "lat": lat, "lon": LON, "speed": speed, "course": 0.0, "height": 500.0, "position_at": at}


@pytest.mark.pg
@pytest.mark.asyncio
async def test_sync_stores_gtk_gps_and_the_page_compares_it_with_wialon(monkeypatch):
    tag = uuid4().hex[:6]
    base = 700_000 + int(tag[:4], 16) % 90_000
    g_ok, g_stale = base, base + 1
    sec_a, sec_b = uuid4(), uuid4()
    loco_ok, loco_stale, loco_other = uuid4(), uuid4(), uuid4()
    units_w = (f"GW{tag}1", f"GW{tag}2", f"GW{tag}3")
    now = datetime.now(UTC).replace(microsecond=0)
    pts = seed_points(now)
    gtk_points = [GpsPoint(at, lat, LON, 5.0) for at, lat in pts]
    last_at, last_lat = pts[-1]
    run_ids: list[int] = []
    async with SessionFactory() as db:
        db.add_all([Section(id=sec_a, name=f"GA-{tag}"), Section(id=sec_b, name=f"GB-{tag}")])
        await db.flush()
        db.add_all([
            FixedAsset(id=loco_ok, inv_number=f"GL1-{tag}", asset_type="locomotive", status="operational", section_id=sec_a),
            FixedAsset(id=loco_stale, inv_number=f"GL2-{tag}", asset_type="diesel", status="operational", section_id=sec_a),
            FixedAsset(id=loco_other, inv_number=f"GL3-{tag}", asset_type="diesel", status="operational", section_id=sec_b),
        ])
        await db.flush()
        db.add_all([WialonUnitRecord(unit_id=u, name=u, lat=Decimal(str(last_lat)), lon=Decimal(str(LON)), speed=Decimal("0"), position_at=last_at, last_message_at=last_at) for u in units_w])
        await db.flush()
        db.add_all([
            AssetSourceLink(asset_id=loco_ok, source="wialon", external_id=units_w[0], status="active"),
            AssetSourceLink(asset_id=loco_stale, source="wialon", external_id=units_w[1], status="active"),
            AssetSourceLink(asset_id=loco_other, source="wialon", external_id=units_w[2], status="active"),
            AssetSourceLink(asset_id=loco_ok, source="gtk", external_id=str(g_ok), status="active"),
            AssetSourceLink(asset_id=loco_stale, source="gtk", external_id=str(g_stale), status="active"),
        ])
        # Wialon's stored track: the same path the GTK stub serves
        db.add_all([AssetPositionHistory(asset_id=a, at=at, lat=Decimal(str(round(lat, 7))), lon=Decimal(str(LON)), source="wialon") for a in (loco_ok, loco_stale) for at, lat in pts])
        await db.commit()
    stale_at = now - timedelta(hours=3)
    fake = FakeGtk(
        [unit(g_ok, last_lat + 0.00005, last_at + timedelta(minutes=1), name="OK"), unit(g_stale, last_lat + 0.05, stale_at, name="ST"), unit(base + 9, None, None, name="NOPOS")],
        {g_ok: gtk_points, g_stale: gtk_points},
    )
    monkeypatch.setattr(gtk_gps, "GtkGpsClient", fake)
    try:
        async with SessionFactory() as db:
            run = await gtk_gps.sync_gtk_gps(db, now=now)
            run_ids.append(run.id)
            assert run.status == "success" and run.units == 3 and run.tracks_ok >= 2 and run.tracks_failed == 0
            stored = (await db.execute(select(func.count()).select_from(AssetPositionHistory).where(AssetPositionHistory.asset_id.in_([loco_ok, loco_stale]), AssetPositionHistory.source == "gtk_gps"))).scalar_one()
            assert stored > 30  # thinned points of both locomotives (>= 100 m apart: all kept)
            days = (await db.execute(select(GtkGpsDay).where(GtkGpsDay.gtk_id == g_ok))).scalars().all()
            assert sum(d.distance_m or 0 for d in days) > 3000 and all(d.events == {"noreasonidle": 3} or d.events is None for d in days)
            nopos = (await db.execute(select(GtkGpsUnit).where(GtkGpsUnit.gtk_id == base + 9))).scalar_one()
            assert nopos.lat is None  # a unit without a fix has no position

            # idempotent: a second cycle adds no points and no duplicate days
            run2 = await gtk_gps.sync_gtk_gps(db, now=now + timedelta(minutes=10))
            run_ids.append(run2.id)
            assert (await db.execute(select(func.count()).select_from(AssetPositionHistory).where(AssetPositionHistory.asset_id.in_([loco_ok, loco_stale]), AssetPositionHistory.source == "gtk_gps"))).scalar_one() == stored

            admin = SimpleNamespace(role="admin", section_id=None)
            page = await overview.get_overview(db, admin, days=3, q=f"-{tag}", now=now + timedelta(minutes=10))
            by_inv = {r.inv_number: r for r in page.items}
            ok, stale = by_inv[f"GL1-{tag}"], by_inv[f"GL2-{tag}"]
            assert ok.position.verdict == "confirmed" and ok.position.best == "gtk" and ok.wialon and ok.gtk
            assert stale.position.verdict == "gtk_stale" and stale.status == "bad" and stale.position.best == "wialon"
            assert 0.85 <= ok.week_gtk_m / ok.week_wialon_m <= 1.15 and ok.week_unified_m > 3000
            assert page.summary.position_verdicts.get("confirmed", 0) >= 1 and page.feed.gtk_track_points >= stored
            assert page.items[0].severity >= page.items[-1].severity  # the worst problem first
            only_bad = await overview.get_overview(db, admin, days=3, q=f"-{tag}", only_issues=True, now=now)
            assert {r.inv_number for r in only_bad.items} >= {f"GL2-{tag}"} and f"GL1-{tag}" not in {r.inv_number for r in only_bad.items}

            detail = await overview.get_asset_detail(db, admin, loco_ok, days=3, track_days=2, now=now + timedelta(minutes=10))
            assert len(detail.wialon_track) > 30 and len(detail.gtk_track) > 30 and detail.row.asset_id == loco_ok  # two separate tracks

            # a master sees only his own section; a stranger's locomotive is 404 (before anything else)
            master_a = SimpleNamespace(role="master", section_id=sec_a)
            mine = await overview.get_overview(db, master_a, days=3, q=f"-{tag}", section_id=sec_b)  # the query's section is ignored
            assert {r.inv_number for r in mine.items} == {f"GL1-{tag}", f"GL2-{tag}"}
            with pytest.raises(HTTPException) as info:
                await overview.get_asset_detail(db, master_a, loco_other)
            assert info.value.status_code == 404
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(GtkGpsDay).where(GtkGpsDay.gtk_id.in_([g_ok, g_stale])))
            await db.execute(delete(GtkGpsUnit).where(GtkGpsUnit.gtk_id.in_([g_ok, g_stale, base + 9])))
            await db.execute(delete(GtkGpsRun).where(GtkGpsRun.id.in_(run_ids)))
            await db.execute(delete(AssetPositionHistory).where(AssetPositionHistory.asset_id.in_([loco_ok, loco_stale, loco_other])))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco_ok, loco_stale, loco_other])))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id.in_(units_w)))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco_ok, loco_stale, loco_other])))
            await db.execute(delete(Section).where(Section.id.in_([sec_a, sec_b])))
            await db.commit()


@pytest.mark.pg
@pytest.mark.asyncio
async def test_a_gtk_login_failure_is_recorded_and_does_not_raise(monkeypatch):
    monkeypatch.setattr(gtk_gps, "GtkGpsClient", FakeGtk([], {}, login_error=True))
    async with SessionFactory() as db:
        run = await gtk_gps.sync_gtk_gps(db)
        run_id = run.id
        assert run.status == "failed" and run.error_code == "GtkLoginError" and run.units == 0
    async with SessionFactory() as db:
        await db.execute(delete(GtkGpsRun).where(GtkGpsRun.id == run_id))
        await db.commit()


@pytest.mark.pg
@pytest.mark.asyncio
async def test_a_run_whose_process_died_is_closed_and_a_live_one_is_left_alone():
    now = datetime.now(UTC)
    async with SessionFactory() as db:
        dead = GtkGpsRun(status="failed", started_at=now - timedelta(hours=2), heartbeat_at=now - timedelta(hours=1, minutes=50))
        alive = GtkGpsRun(status="failed", started_at=now - timedelta(hours=2), heartbeat_at=now - timedelta(minutes=2))  # a long backfill that still commits batches
        db.add_all([dead, alive])
        await db.flush()
        ids = [dead.id, alive.id]
        closed = await gtk_gps.close_stale_runs(db, now)
        await db.commit()
        assert closed >= 1
        rows = {r.id: r for r in (await db.execute(select(GtkGpsRun).where(GtkGpsRun.id.in_(ids)))).scalars()}
        assert rows[ids[0]].finished_at is not None and rows[ids[0]].error_code == "interrupted"
        assert rows[ids[1]].finished_at is None
    async with SessionFactory() as db:
        await db.execute(delete(GtkGpsRun).where(GtkGpsRun.id.in_(ids)))
        await db.commit()


def test_day_planning_is_local_and_finalises_after_the_grace():
    now = datetime(2026, 11, 17, 19, 30, tzinfo=UTC)  # 2026-11-18 00:30 local (UTC+5)
    assert gtk_gps.local_now(now, 5) == datetime(2026, 11, 18, 0, 30)
    today = date(2026, 11, 18)
    assert gtk_gps.days_to_fetch(today, set()) == [today, date(2026, 11, 17)]
    assert gtk_gps.days_to_fetch(today, {date(2026, 11, 17)}) == [today]
    assert gtk_gps.days_to_fetch(today, {date(2026, 11, 17)}, backfill_days=3) == [today, date(2026, 11, 16), date(2026, 11, 15)]
    assert not gtk_gps.is_final_day(date(2026, 11, 17), now, 5)  # only 30 min after local midnight
    assert gtk_gps.is_final_day(date(2026, 11, 17), now + timedelta(minutes=20), 5)
    window = gtk_gps.day_window(today, now, 5)
    assert window.local_from == datetime(2026, 11, 18) and window.local_to == datetime(2026, 11, 18, 0, 30)  # today ends «now»
    past = gtk_gps.day_window(date(2026, 11, 17), now, 5)
    assert past.local_to == datetime(2026, 11, 17, 23, 59, 59)
