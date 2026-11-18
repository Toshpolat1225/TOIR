"""The GPS page: Wialon and GTK are two separate trackers; here they are compared, merged and the disagreements explained.

Rows are built from the live fixes of both trackers and the per-day assessments (`gps_assessment`); filters, facets, sorting and the
export all work on the same rows, so every number on the page, in a facet and in a file is the same number.
"""
from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from xml.sax.saxutils import escape

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.identity import User
from app.repositories import gps as repository
from app.schemas.gps import (
    GpsAssetDetail, GpsAssetRow, GpsDayRow, GpsFeedHealth, GpsFix, GpsHealth, GpsHealthPage, GpsHealthRow, GpsOverview, GpsPositionCheck,
    GpsSummary, GpsTrackPoint,
)
from app.services import gps_analytics as ga
from app.services import gps_assessment as assessment
from app.services import gps_compare as cmp

MAX_DAYS = 31
MAX_TRACK_DAYS = 14
HEALTH_WINDOW_DAYS = 14  # the tracker-health class never looks at fewer days than this
SORT_FIELDS = {"severity", "inv_number", "diff_m", "gtk_age", "wialon_age", "week_wialon_m", "week_gtk_m", "week_fused_m", "ratio", "cause", "confidence"}
HEALTH_SORT = {"worst", "inv_number", "ok_share", "km_lost"}
MOVING_KMH = 3.0
_HEALTH_ORDER = {"dead": 0, "frozen": 1, "intermittent": 2, "ok": 3, "no_gtk": 4}
GTK_LOSS_CAUSES = ("gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse")


@dataclass
class Filters:
    days: int = 7
    date_from: date | None = None
    date_to: date | None = None
    q: str | None = None
    section_id: UUID | None = None
    asset_type: list[str] = field(default_factory=list)
    model_id: UUID | None = None
    verdict: list[str] = field(default_factory=list)
    distance_verdict: list[str] = field(default_factory=list)
    cause: list[str] = field(default_factory=list)
    severity: list[str] = field(default_factory=list)
    link: str | None = None
    health: list[str] = field(default_factory=list)
    min_diff_m: float | None = None
    min_silence_h: float | None = None
    moving: bool | None = None
    min_km: float | None = None
    max_km: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    only_issues: bool = False
    sort_by: str = "severity"
    sort_dir: str = "desc"


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    try:
        a, b, c, d = (float(x) for x in value.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bbox must be minLat,minLon,maxLat,maxLon") from exc
    return (min(a, c), min(b, d), max(a, c), max(b, d))


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


def window_days(f: Filters, today: date) -> list[date]:
    """The local days of the window, newest first."""
    if f.date_from is not None and f.date_to is not None:
        end = min(f.date_to, today)
        start = max(f.date_from, end - timedelta(days=MAX_DAYS - 1))
        if start > end:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date_from must not be after date_to")
        return [end - timedelta(days=i) for i in range((end - start).days + 1)]
    days = max(1, min(f.days, MAX_DAYS))
    return [today - timedelta(days=i) for i in range(days)]


def day_row(a: assessment.DayAssessment) -> GpsDayRow:
    return GpsDayRow(
        day=a.day, wialon_m=a.wialon_m if (a.wialon_points or a.wialon_m) else None, wialon_points=a.wialon_points, gtk_m=a.gtk_m,
        gtk_points=a.gtk_points, gtk_raw_points=a.gtk_raw_points, gtk_final=a.gtk_final, verdict=a.verdict, ratio=a.ratio, diff_m=a.diff_m,
        unified_m=a.fused_m, idle_events=a.idle_events, cause=a.cause, fused_m=a.fused_m, unknown_gap_m=a.unknown_gap_m,
        wialon_cov_h=a.wialon_cov_h, gtk_cov_h=a.gtk_cov_h, confidence=a.confidence, odo_m=a.odo_m, odo_agrees=a.odo_agrees, explanation=a.explanation or None,
    )


def _placeholder(asset: UUID, day: date) -> assessment.DayAssessment:
    return assessment.DayAssessment(
        asset_id=asset, day=day, wialon_m=0, wialon_points=0, gtk_m=None, gtk_points=0, gtk_raw_points=0, gtk_final=False, gtk_collected=False,
        verdict="no_data", ratio=None, diff_m=None, fused_m=None, unknown_gap_m=None, wialon_cov_h=0.0, gtk_cov_h=0.0, wialon_gap_h=0.0,
        gtk_gap_h=0.0, cause="no_data", confidence=None, idle_events=None, is_final=False,
    )


def build_row(base: dict, window: list[assessment.DayAssessment], history: list[assessment.DayAssessment], now: datetime) -> GpsAssetRow:
    wialon = _fix(base["w_lat"], base["w_lon"], base["w_at"], base["w_speed"], now)
    gtk = _fix(base["g_lat"], base["g_lon"], base["g_at"], base["g_speed"], now)
    check = cmp.position_check(
        cmp.SourceFix(wialon.lat, wialon.lon, wialon.at, wialon.speed) if wialon else None,
        cmp.SourceFix(gtk.lat, gtk.lon, gtk.at, gtk.speed) if gtk else None,
        now,
    )
    days = [day_row(a) for a in window]
    issues = sum(1 for d in days if cmp.DISTANCE_SEVERITY.get(d.verdict, 0) > 0)
    worst_distance = max((cmp.DISTANCE_SEVERITY.get(d.verdict, 0) for d in days), default=0)
    # a source that is simply not linked is not a fault of the data, so it does not outrank a real problem on the other one
    severity = max(cmp.POSITION_SEVERITY[check.verdict], worst_distance)
    facts = [ga.DayFact(a.wialon_m, a.gtk_m, a.gtk_points, a.cause, a.verdict) for a in history]
    last_age_h = None if gtk is None or gtk.age_min is None else round(gtk.age_min / 60, 1)
    health = ga.health_of(facts, gtk_linked=base["gtk_link_id"] is not None, last_gtk_fix_age_h=last_age_h)
    causes = Counter(a.cause for a in window if a.cause not in ("ok", "idle", "no_data", "day_open", "not_collected"))
    fused_total = sum(a.fused_m or 0 for a in window)
    conf_num = sum((a.confidence or 0) * (a.fused_m or 0) for a in window)
    best = gtk if (check.best == "gtk" and gtk) else wialon
    moving = bool(best and best.fresh and (best.speed or 0) > MOVING_KMH)
    return GpsAssetRow(
        asset_id=base["asset_id"], inv_number=base["inv_number"], name=base["name"], asset_type=base["asset_type"],
        asset_type_name=base["asset_type_name"], model_name=base["model_name"], model_id=base.get("model_id"), section_id=base["section_id"],
        section_name=base["section_name"], wialon_linked=base["wialon_link_id"] is not None, gtk_linked=base["gtk_link_id"] is not None,
        wialon=wialon, gtk=gtk, position=GpsPositionCheck(**{k: getattr(check, k) for k in ("verdict", "diff_m", "lag_s", "tolerance_m", "best")}),
        days=days, week_wialon_m=sum(d.wialon_m or 0 for d in days), week_gtk_m=sum(d.gtk_m or 0 for d in days), week_unified_m=fused_total,
        week_fused_m=fused_total, distance_issues=issues, severity=severity, status="ok" if severity == 0 else ("warn" if severity == 1 else "bad"),
        health=GpsHealth(
            health_class=health.health_class, window_days=health.window_days, active_days=health.active_days, ok_days=health.ok_days,
            partial_days=health.partial_days, none_days=health.none_days, last_gtk_fix_age_h=health.last_gtk_fix_age_h, km_lost_m=health.km_lost_m, ok_share=health.ok_share,
        ),
        top_cause=causes.most_common(1)[0][0] if causes else None, week_confidence=round(conf_num / fused_total, 2) if fused_total else None,
        moving=moving, explanation=ga.POSITION_TEXT.get(check.verdict),
    )


async def load_rows(db: AsyncSession, scope: UUID | None, f: Filters, now: datetime) -> tuple[list[GpsAssetRow], list[date]]:
    offset = settings.gtk_utc_offset_hours
    today = assessment.local_today(now, offset)
    window = window_days(f, today)
    bases = await repository.list_loco_positions(db, section_id=scope)
    targets = {b["asset_id"]: b["gtk_id"] for b in bases}
    history_days = sorted({*window, *(today - timedelta(days=i) for i in range(HEALTH_WINDOW_DAYS))})
    got = await assessment.ensure_days(db, targets, history_days, now)
    rows = []
    for base in bases:
        asset = base["asset_id"]
        win = [got.get((asset, d)) or _placeholder(asset, d) for d in window]
        hist = [got[(asset, d)] for d in history_days if (asset, d) in got]
        rows.append(build_row(base, win, hist, now))
    return rows, window


# ---- filters, facets, sorting ------------------------------------------------------------------------------
def _link(row: GpsAssetRow) -> str:
    return "both" if (row.wialon_linked and row.gtk_linked) else "wialon_only" if row.wialon_linked else "gtk_only" if row.gtk_linked else "none"


def _best_fix(row: GpsAssetRow) -> GpsFix | None:
    return row.gtk if (row.position.best == "gtk" and row.gtk) else (row.wialon or row.gtk)


def _silence_h(row: GpsAssetRow) -> float | None:
    ages = [x.age_min for x in (row.wialon, row.gtk) if x is not None and x.age_min is not None]
    return None if not ages else max(ages) / 60


def _in_bbox(fix: GpsFix | None, box: tuple[float, float, float, float]) -> bool:
    return fix is not None and box[0] <= fix.lat <= box[2] and box[1] <= fix.lon <= box[3]


def matches(row: GpsAssetRow, f: Filters, skip: str | None = None) -> bool:
    def want(name: str, ok: bool) -> bool:
        return skip == name or ok

    if f.q:
        needle = f.q.strip().lower()
        hay = " ".join(str(x or "") for x in (row.inv_number, row.name, row.model_name, row.section_name)).lower()
        if needle not in hay:
            return False
    return (
        want("section", f.section_id is None or row.section_id == f.section_id)
        and want("asset_type", not f.asset_type or row.asset_type in f.asset_type)
        and want("model", f.model_id is None or row.model_id == f.model_id)
        and want("position_verdict", not f.verdict or row.position.verdict in f.verdict)
        and want("distance_verdict", not f.distance_verdict or any(d.verdict in f.distance_verdict for d in row.days))
        and want("cause", not f.cause or any(d.cause in f.cause for d in row.days))
        and want("severity", not f.severity or row.status in f.severity)
        and want("link", f.link is None or _link(row) == f.link)
        and want("health", not f.health or (row.health is not None and row.health.health_class in f.health))
        and want("min_diff_m", f.min_diff_m is None or (row.position.diff_m or 0) >= f.min_diff_m)
        and want("min_silence_h", f.min_silence_h is None or (_silence_h(row) or 0) >= f.min_silence_h)
        and want("moving", f.moving is None or row.moving == f.moving)
        and want("min_km", f.min_km is None or row.week_fused_m / 1000 >= f.min_km)
        and want("max_km", f.max_km is None or row.week_fused_m / 1000 <= f.max_km)
        and want("bbox", f.bbox is None or _in_bbox(_best_fix(row), f.bbox))
        and want("only_issues", not f.only_issues or row.severity > 0)
    )


def facets_of(rows: list[GpsAssetRow], f: Filters) -> dict[str, dict[str, int]]:
    """For each filter: how many locomotives each of its values would show under all the OTHER active filters."""
    def count(name: str, values) -> dict[str, int]:
        c: Counter = Counter()
        for row in rows:
            if matches(row, f, skip=name):
                for v in values(row):
                    c[v] += 1
        return dict(c)

    return {
        "severity": count("severity", lambda r: [r.status]),
        "position_verdict": count("position_verdict", lambda r: [r.position.verdict]),
        "distance_verdict": count("distance_verdict", lambda r: {d.verdict for d in r.days}),
        "cause": count("cause", lambda r: {d.cause for d in r.days}),
        "health": count("health", lambda r: [r.health.health_class] if r.health else []),
        "link": count("link", lambda r: [_link(r)]),
        "asset_type": count("asset_type", lambda r: [r.asset_type]),
        "section": count("section", lambda r: [str(r.section_id)] if r.section_id else []),
    }


def _ratio(row: GpsAssetRow) -> float:
    return row.week_gtk_m / row.week_wialon_m if row.week_wialon_m else -1.0


def sort_rows(rows: list[GpsAssetRow], sort_by: str, sort_dir: str) -> list[GpsAssetRow]:
    if sort_by not in SORT_FIELDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sort_by must be one of: " + ", ".join(sorted(SORT_FIELDS)))
    keys = {
        "severity": lambda r: (r.severity, r.distance_issues),
        "inv_number": lambda r: r.inv_number,
        "diff_m": lambda r: r.position.diff_m if r.position.diff_m is not None else -1.0,
        "gtk_age": lambda r: r.gtk.age_min if r.gtk and r.gtk.age_min is not None else -1.0,
        "wialon_age": lambda r: r.wialon.age_min if r.wialon and r.wialon.age_min is not None else -1.0,
        "week_wialon_m": lambda r: r.week_wialon_m,
        "week_gtk_m": lambda r: r.week_gtk_m,
        "week_fused_m": lambda r: r.week_fused_m,
        "ratio": _ratio,
        "cause": lambda r: r.top_cause or "",
        "confidence": lambda r: r.week_confidence if r.week_confidence is not None else -1.0,
    }
    ordered = sorted(rows, key=lambda r: r.inv_number)  # a stable secondary order
    return sorted(ordered, key=keys[sort_by], reverse=(sort_dir == "desc"))


def summarise(rows: list[GpsAssetRow]) -> GpsSummary:
    summary = GpsSummary(assets=len(rows))
    for row in rows:
        summary.both_sources += 1 if (row.wialon and row.gtk) else 0
        summary.position_verdicts[row.position.verdict] = summary.position_verdicts.get(row.position.verdict, 0) + 1
        for d in row.days:
            summary.distance_verdicts[d.verdict] = summary.distance_verdicts.get(d.verdict, 0) + 1
            summary.cause_counts[d.cause] = summary.cause_counts.get(d.cause, 0) + 1
        if row.health:
            summary.health_counts[row.health.health_class] = summary.health_counts.get(row.health.health_class, 0) + 1
        summary.km_lost_m += sum(max(0, (d.wialon_m or 0) - (d.gtk_m or 0)) for d in row.days if d.cause in GTK_LOSS_CAUSES)
        summary.week_wialon_m += row.week_wialon_m
        summary.week_gtk_m += row.week_gtk_m
        summary.week_unified_m += row.week_unified_m
        summary.week_fused_m += row.week_fused_m
        setattr(summary, row.status, getattr(summary, row.status) + 1)
    return summary


async def _feed(db: AsyncSession) -> GpsFeedHealth:
    data = await repository.feed_health(db)
    run = data["run"]
    stats = data["by_source"]
    return GpsFeedHealth(
        gtk_enabled=settings.gtk_gps_pull_enabled, gtk_running=data["running"], gtk_last_run_at=run.started_at if run else None,
        gtk_last_status=run.status if run else None, gtk_last_error=run.error_code if run else None, gtk_units=run.units if run else 0,
        gtk_tracks_failed=run.tracks_failed if run else 0, gtk_units_synced_at=data["gtk_units_synced_at"], wialon_units_synced_at=data["wialon_units_synced_at"],
        gtk_track_points=stats.get("gtk_gps", (0, None))[0], wialon_track_points=stats.get("wialon", (0, None))[0],
        gtk_track_from=stats.get("gtk_gps", (0, None))[1], wialon_track_from=stats.get("wialon", (0, None))[1], utc_offset_hours=settings.gtk_utc_offset_hours,
    )


async def filtered_rows(db: AsyncSession, user: User, f: Filters, now: datetime | None = None) -> tuple[list[GpsAssetRow], list[GpsAssetRow], list[date]]:
    """(all rows of the scope, the rows after the filters sorted, the window)."""
    scope = _scope(user)
    now = now or datetime.now(timezone.utc)
    if scope is not None:
        f.section_id = scope  # a master only ever sees their own section, whatever the query says
    rows, window = await load_rows(db, scope, f, now)
    shown = sort_rows([r for r in rows if matches(r, f)], f.sort_by, f.sort_dir)
    return rows, shown, window


async def get_overview(
    db: AsyncSession, user: User, f: Filters | None = None, *, with_facets: bool = False, limit: int = 200, offset: int = 0, now: datetime | None = None,
    **legacy,
) -> GpsOverview:
    """`legacy` keeps the pre-filter call style (days=, q=, section_id=, verdict=<str>, only_issues=)."""
    if f is None:
        known = {k: v for k, v in legacy.items() if k in Filters.__dataclass_fields__ and k != "verdict"}
        f = Filters(**known)
        if legacy.get("verdict"):
            f.verdict = [legacy["verdict"]] if isinstance(legacy["verdict"], str) else list(legacy["verdict"])
    now = now or datetime.now(timezone.utc)
    rows, shown, window = await filtered_rows(db, user, f, now)
    return GpsOverview(
        items=shown[offset : offset + limit], total=len(shown), limit=limit, offset=offset, summary=summarise(rows),
        facets=facets_of(rows, f) if with_facets else {}, feed=await _feed(db), days=len(window), date_from=window[-1], date_to=window[0],
    )


# ---- tracker health ----------------------------------------------------------------------------------------
async def get_health(
    db: AsyncSession, user: User, *, q: str | None = None, section_id: UUID | None = None, health: list[str] | None = None, days: int = 30,
    sort_by: str = "worst", sort_dir: str = "asc", limit: int = 200, offset: int = 0, now: datetime | None = None,
) -> GpsHealthPage:
    if sort_by not in HEALTH_SORT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sort_by must be one of: " + ", ".join(sorted(HEALTH_SORT)))
    scope = _scope(user)
    now = now or datetime.now(timezone.utc)
    days = max(7, min(days, 60))
    today = assessment.local_today(now, settings.gtk_utc_offset_hours)
    bases = await repository.list_loco_positions(db, section_id=scope if scope is not None else section_id, q=q)
    targets = {b["asset_id"]: b["gtk_id"] for b in bases}
    wanted = [today - timedelta(days=i) for i in range(days)]
    got = await assessment.ensure_days(db, targets, wanted, now, max_live_past=0)  # stored rows + today; the CLI/job keeps the rest stored
    items: list[GpsHealthRow] = []
    counts: Counter = Counter()
    for b in bases:
        hist = [got[(b["asset_id"], d)] for d in wanted if (b["asset_id"], d) in got]
        gtk = _fix(b["g_lat"], b["g_lon"], b["g_at"], b["g_speed"], now)
        wialon = _fix(b["w_lat"], b["w_lon"], b["w_at"], b["w_speed"], now)
        age_h = None if gtk is None or gtk.age_min is None else round(gtk.age_min / 60, 1)
        h = ga.health_of([ga.DayFact(a.wialon_m, a.gtk_m, a.gtk_points, a.cause, a.verdict) for a in hist], gtk_linked=b["gtk_link_id"] is not None, last_gtk_fix_age_h=age_h)
        counts[h.health_class] += 1
        if health and h.health_class not in health:
            continue
        anomaly = "frozen" if h.health_class == "frozen" else ("silent" if (age_h or 0) > 24 and wialon is not None and wialon.fresh else None)
        items.append(
            GpsHealthRow(
                asset_id=b["asset_id"], inv_number=b["inv_number"], name=b["name"], asset_type_name=b["asset_type_name"], model_name=b["model_name"],
                section_id=b["section_id"], section_name=b["section_name"], gtk_linked=b["gtk_link_id"] is not None, gtk_id=b["gtk_id"],
                health=GpsHealth(
                    health_class=h.health_class, window_days=h.window_days, active_days=h.active_days, ok_days=h.ok_days, partial_days=h.partial_days,
                    none_days=h.none_days, last_gtk_fix_age_h=h.last_gtk_fix_age_h, km_lost_m=h.km_lost_m, ok_share=h.ok_share,
                ),
                last_gtk_fix_at=gtk.at if gtk else None, anomaly=anomaly, explanation=ga.HEALTH_TEXT.get(h.health_class),
            )
        )
    keys = {
        "worst": lambda r: (_HEALTH_ORDER.get(r.health.health_class, 9), -r.health.km_lost_m, r.inv_number),
        "inv_number": lambda r: r.inv_number,
        "ok_share": lambda r: r.health.ok_share if r.health.ok_share is not None else 2.0,
        "km_lost": lambda r: -r.health.km_lost_m,
    }
    items.sort(key=keys[sort_by], reverse=(sort_dir == "desc"))
    return GpsHealthPage(items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset, counts=dict(counts))


# ---- one locomotive ----------------------------------------------------------------------------------------
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
    offset = settings.gtk_utc_offset_hours
    today = assessment.local_today(now, offset)
    window = window_days(Filters(days=days), today)
    history_days = sorted({*window, *(today - timedelta(days=i) for i in range(HEALTH_WINDOW_DAYS))})
    got = await assessment.ensure_days(db, {asset_id: bases[0]["gtk_id"]}, history_days, now)
    win = [got.get((asset_id, d)) or _placeholder(asset_id, d) for d in window]
    hist = [got[(asset_id, d)] for d in history_days if (asset_id, d) in got]
    row = build_row(bases[0], win, hist, now)
    lo = assessment.local_day_bounds(today - timedelta(days=track_days - 1), offset)[0]
    hi = assessment.local_day_bounds(today, offset)[1]
    wialon_track = await repository.track(db, asset_id, "wialon", lo, hi)
    gtk_track = await repository.track(db, asset_id, "gtk_gps", lo, hi)
    point = lambda t: GpsTrackPoint(at=t[0], lat=t[1], lon=t[2], speed=t[3])  # noqa: E731
    return GpsAssetDetail(row=row, wialon_track=[point(t) for t in wialon_track], gtk_track=[point(t) for t in gtk_track], track_from=lo, track_to=hi, feed=await _feed(db))


# ---- export ------------------------------------------------------------------------------------------------
EXPORT_HEADER = [
    "Инв. номер", "Название", "Модель", "Участок", "Вердикт положения", "Расстояние между точками, м", "Wialon: возраст, мин", "GTK: возраст, мин",
    "Wialon, км", "GTK, км", "Единый, км", "Уверенность", "Состояние GTK-трекера", "Главная причина расхождений", "Проблемных дней",
]


def export_matrix(rows: list[GpsAssetRow]) -> list[list]:
    out = []
    for r in rows:
        out.append(
            [
                r.inv_number, r.name, r.model_name or "", r.section_name or "", r.position.verdict, round(r.position.diff_m) if r.position.diff_m is not None else "",
                r.wialon.age_min if r.wialon else "", r.gtk.age_min if r.gtk else "", round(r.week_wialon_m / 1000, 1), round(r.week_gtk_m / 1000, 1),
                round(r.week_fused_m / 1000, 1), r.week_confidence if r.week_confidence is not None else "", r.health.health_class if r.health else "",
                r.top_cause or "", r.distance_issues,
            ]
        )
    return out


def to_csv(rows: list[GpsAssetRow]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(EXPORT_HEADER)
    writer.writerows(export_matrix(rows))
    return ("﻿" + buf.getvalue()).encode("utf-8")  # a BOM so Excel opens the Russian text correctly


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def to_xlsx(rows: list[GpsAssetRow]) -> bytes:
    """A minimal .xlsx (inline strings, no dependency)."""
    matrix = [EXPORT_HEADER, *export_matrix(rows)]
    sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for r, line in enumerate(matrix, start=1):
        sheet.append(f'<row r="{r}">')
        for c, value in enumerate(line):
            ref = f"{_col(c)}{r}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sheet.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                sheet.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        sheet.append("</row>")
    sheet.append("</sheetData></worksheet>")
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="GPS" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": "".join(sheet),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return out.getvalue()
