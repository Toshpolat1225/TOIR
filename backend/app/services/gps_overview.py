"""The GPS page: Wialon and GTK are two separate trackers; here they are compared, merged and the disagreements named."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.identity import User
from app.repositories import gps as repository
from app.schemas.gps import (
    GpsAssetDetail, GpsAssetRow, GpsDayRow, GpsFeedHealth, GpsFix, GpsOverview, GpsPositionCheck, GpsSummary, GpsTrackPoint,
)
from app.services import gps_compare as cmp

MAX_DAYS = 31
MAX_TRACK_DAYS = 14


def _scope(user: User) -> UUID | None:
    if user.role != "master":
        return None
    if user.section_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Master user must be assigned to a section")
    return user.section_id


def _fix(lat, lon, at, speed, now: datetime) -> GpsFix | None:
    source = cmp.SourceFix(None if lat is None else float(lat), None if lon is None else float(lon), at, None if speed is None else float(speed))
    if not source.valid:
        return None
    age = None
    if at is not None:
        aware = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        age = max(0.0, (now - aware).total_seconds() / 60)
    return GpsFix(lat=source.lat, lon=source.lon, at=at, speed=source.speed, age_min=None if age is None else round(age, 1), fresh=cmp._is_fresh(age))  # type: ignore[arg-type]


def local_days(today: date, days: int) -> list[date]:
    """Newest first."""
    return [today - timedelta(days=i) for i in range(days)]


def day_rows(
    days: list[date],
    wialon: dict[date, tuple[int, int]],
    gtk_stored: dict[date, tuple[int, int]],
    gtk_figures: dict[date, object],
) -> list[GpsDayRow]:
    rows: list[GpsDayRow] = []
    for day in days:
        w_m, w_pts = wialon.get(day, (None, 0))
        _, g_pts = gtk_stored.get(day, (None, 0))
        figure = gtk_figures.get(day)
        g_m = getattr(figure, "distance_m", None)
        check = cmp.distance_check(g_m, g_pts, w_m, w_pts, gtk_collected=figure is not None)
        events = getattr(figure, "events", None) or {}
        rows.append(
            GpsDayRow(
                day=day, wialon_m=w_m, wialon_points=w_pts, gtk_m=g_m, gtk_points=g_pts, gtk_raw_points=getattr(figure, "points", 0) or 0,
                gtk_final=bool(getattr(figure, "is_final", False)), verdict=check.verdict, ratio=check.ratio, diff_m=check.diff_m,
                unified_m=check.unified_m, idle_events=sum(v for k, v in events.items() if "idle" in k) if events else None,
            )
        )
    return rows


def build_row(base: dict, days: list[GpsDayRow], now: datetime) -> GpsAssetRow:
    wialon = _fix(base["w_lat"], base["w_lon"], base["w_at"], base["w_speed"], now)
    gtk = _fix(base["g_lat"], base["g_lon"], base["g_at"], base["g_speed"], now)
    check = cmp.position_check(
        cmp.SourceFix(wialon.lat, wialon.lon, wialon.at, wialon.speed) if wialon else None,
        cmp.SourceFix(gtk.lat, gtk.lon, gtk.at, gtk.speed) if gtk else None,
        now,
    )
    issues = sum(1 for d in days if cmp.DISTANCE_SEVERITY[d.verdict] > 0)
    worst_distance = max((cmp.DISTANCE_SEVERITY[d.verdict] for d in days), default=0)
    # a source that is simply not linked is not a fault of the data, so it does not outrank a real problem on the other one
    severity = max(cmp.POSITION_SEVERITY[check.verdict], worst_distance)
    return GpsAssetRow(
        asset_id=base["asset_id"], inv_number=base["inv_number"], name=base["name"], asset_type=base["asset_type"],
        asset_type_name=base["asset_type_name"], model_name=base["model_name"], section_id=base["section_id"], section_name=base["section_name"],
        wialon_linked=base["wialon_link_id"] is not None, gtk_linked=base["gtk_link_id"] is not None, wialon=wialon, gtk=gtk,
        position=GpsPositionCheck(**{k: getattr(check, k) for k in ("verdict", "diff_m", "lag_s", "tolerance_m", "best")}),
        days=days, week_wialon_m=sum(d.wialon_m or 0 for d in days), week_gtk_m=sum(d.gtk_m or 0 for d in days),
        week_unified_m=sum(d.unified_m or 0 for d in days), distance_issues=issues, severity=severity,
        status="ok" if severity == 0 else ("warn" if severity == 1 else "bad"),
    )


def _bounds(today: date, days: int, offset: int) -> tuple[datetime, datetime]:
    first = today - timedelta(days=days - 1)
    lo = datetime.combine(first, time.min, tzinfo=timezone.utc) - timedelta(hours=offset)
    hi = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc) - timedelta(hours=offset)
    return lo, hi


async def _rows_for(db: AsyncSession, bases: list[dict], days: int, now: datetime) -> list[GpsAssetRow]:
    offset = settings.gtk_utc_offset_hours
    today = (now + timedelta(hours=offset)).date()
    wanted = local_days(today, days)
    lo, hi = _bounds(today, days, offset)
    asset_ids = [b["asset_id"] for b in bases]
    gtk_ids = [b["gtk_id"] for b in bases if b["gtk_id"] is not None]
    wialon = await repository.stored_day_distances(db, asset_ids, "wialon", lo, hi, offset)
    gtk_stored = await repository.stored_day_distances(db, asset_ids, "gtk_gps", lo, hi, offset)
    gtk_figures = await repository.gtk_days(db, gtk_ids, wanted[-1], wanted[0])
    rows: list[GpsAssetRow] = []
    for base in bases:
        asset = base["asset_id"]
        days_for = day_rows(
            wanted,
            {d: v for (a, d), v in wialon.items() if a == asset},
            {d: v for (a, d), v in gtk_stored.items() if a == asset},
            {d: f for (g, d), f in gtk_figures.items() if g == base["gtk_id"]} if base["gtk_id"] is not None else {},
        )
        rows.append(build_row(base, days_for, now))
    return rows


def summarise(rows: list[GpsAssetRow]) -> GpsSummary:
    summary = GpsSummary(assets=len(rows))
    for row in rows:
        summary.both_sources += 1 if (row.wialon and row.gtk) else 0
        summary.position_verdicts[row.position.verdict] = summary.position_verdicts.get(row.position.verdict, 0) + 1
        for d in row.days:
            summary.distance_verdicts[d.verdict] = summary.distance_verdicts.get(d.verdict, 0) + 1
        summary.week_wialon_m += row.week_wialon_m
        summary.week_gtk_m += row.week_gtk_m
        summary.week_unified_m += row.week_unified_m
        setattr(summary, row.status, getattr(summary, row.status) + 1)
    return summary


async def _feed(db: AsyncSession) -> GpsFeedHealth:
    data = await repository.feed_health(db)
    run = data["run"]
    stats = data["by_source"]
    return GpsFeedHealth(
        gtk_enabled=settings.gtk_gps_pull_enabled, gtk_running=data["running"], gtk_last_run_at=run.started_at if run else None, gtk_last_status=run.status if run else None,
        gtk_last_error=run.error_code if run else None, gtk_units=run.units if run else 0, gtk_tracks_failed=run.tracks_failed if run else 0,
        gtk_units_synced_at=data["gtk_units_synced_at"], wialon_units_synced_at=data["wialon_units_synced_at"],
        gtk_track_points=stats.get("gtk_gps", (0, None))[0], wialon_track_points=stats.get("wialon", (0, None))[0],
        gtk_track_from=stats.get("gtk_gps", (0, None))[1], wialon_track_from=stats.get("wialon", (0, None))[1],
        utc_offset_hours=settings.gtk_utc_offset_hours,
    )


async def get_overview(
    db: AsyncSession, user: User, *, days: int = 7, q: str | None = None, section_id: UUID | None = None, verdict: str | None = None,
    only_issues: bool = False, limit: int = 200, offset: int = 0, now: datetime | None = None,
) -> GpsOverview:
    scope = _scope(user)
    if scope is not None:
        section_id = scope  # a master only ever sees their own section, whatever the query says
    now = now or datetime.now(timezone.utc)
    days = max(1, min(days, MAX_DAYS))
    bases = await repository.list_loco_positions(db, section_id=section_id, q=q)
    rows = await _rows_for(db, bases, days, now)
    summary = summarise(rows)  # the summary describes the whole scope, the filters only narrow the list
    shown = [r for r in rows if (verdict is None or r.position.verdict == verdict) and (not only_issues or r.severity > 0)]
    shown.sort(key=lambda r: (-r.severity, r.inv_number))
    offset_hours = settings.gtk_utc_offset_hours
    today = (now + timedelta(hours=offset_hours)).date()
    return GpsOverview(
        items=shown[offset : offset + limit], total=len(shown), limit=limit, offset=offset, summary=summary, feed=await _feed(db), days=days,
        date_from=today - timedelta(days=days - 1), date_to=today,
    )


async def get_asset_detail(
    db: AsyncSession, user: User, asset_id: UUID, *, days: int = 7, track_days: int = 2, now: datetime | None = None,
) -> GpsAssetDetail:
    scope = _scope(user)
    bases = await repository.list_loco_positions(db, section_id=scope, asset_id=asset_id)  # the section check comes first: 404 for a stranger
    if not bases:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locomotive not found")
    now = now or datetime.now(timezone.utc)
    days = max(1, min(days, MAX_DAYS))
    track_days = max(1, min(track_days, MAX_TRACK_DAYS, days))
    row = (await _rows_for(db, bases, days, now))[0]
    offset = settings.gtk_utc_offset_hours
    today = (now + timedelta(hours=offset)).date()
    lo, hi = _bounds(today, track_days, offset)
    wialon_track = await repository.track(db, asset_id, "wialon", lo, hi)
    gtk_track = await repository.track(db, asset_id, "gtk_gps", lo, hi)
    point = lambda t: GpsTrackPoint(at=t[0], lat=t[1], lon=t[2], speed=t[3])  # noqa: E731
    return GpsAssetDetail(
        row=row, wialon_track=[point(t) for t in wialon_track], gtk_track=[point(t) for t in gtk_track], track_from=lo, track_to=hi,
        feed=await _feed(db),
    )
