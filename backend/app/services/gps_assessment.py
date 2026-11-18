"""Per-day assessment of both trackers for every locomotive: distances, cause of a difference, fused distance, confidence.

`assess_days` computes (from the stored, movement-thinned tracks and GTK's own daily figure); `persist` upserts into
`gps_day_assessment`; `ensure_days` serves the page: stored rows for finished days, a live computation for today and for any day
that is missing (so the page never waits for the job). The periodic GTK GPS sync refreshes today / yesterday after every cycle.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.gtk_gps import GpsDayAssessment, GtkGpsDay
from app.models.position_history import AssetPositionHistory
from app.services import gps_analytics as ga
from app.services import gps_compare as cmp
from app.services import gtk_gps

logger = logging.getLogger(__name__)

IDLE_KINDS = "idle"


@dataclass
class DayAssessment:
    asset_id: UUID
    day: date
    wialon_m: int
    wialon_points: int
    gtk_m: int | None
    gtk_points: int
    gtk_raw_points: int
    gtk_final: bool
    gtk_collected: bool
    verdict: str
    ratio: float | None
    diff_m: int | None
    fused_m: int | None
    unknown_gap_m: int | None
    wialon_cov_h: float
    gtk_cov_h: float
    wialon_gap_h: float
    gtk_gap_h: float
    cause: str
    confidence: float | None
    idle_events: int | None
    is_final: bool
    odo_m: int | None = None
    odo_agrees: bool | None = None
    algorithm_version: str = ga.ALGORITHM_VERSION
    is_open: bool = False
    persisted: bool = False
    _inputs: dict = field(default_factory=dict, repr=False)

    @property
    def explanation(self) -> str:
        text_ = ga.explain_day(self.cause, w_gap_h=self.wialon_gap_h, g_gap_h=self.gtk_gap_h)
        if self.odo_agrees is True and self.cause in ("gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse", "both_gaps"):
            text_ += " Одометр Wialon подтверждает пробег по треку Wialon."
        elif self.odo_agrees is False and self.odo_m and self.wialon_m >= ga.ACTIVE_M:
            text_ += f" Внимание: одометр Wialon ({self.odo_m / 1000:.1f} км) расходится с треком Wialon ({self.wialon_m / 1000:.1f} км)."
        return text_.strip()


def local_day_bounds(day: date, offset_hours: int) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc) - timedelta(hours=offset_hours)
    return start, start + timedelta(days=1)


def local_today(now: datetime, offset_hours: int) -> date:
    return (now.astimezone(timezone.utc) + timedelta(hours=offset_hours)).date()


async def _load_odometer(db: AsyncSession, asset_ids: Sequence[UUID], lo: datetime, hi: datetime) -> dict[UUID, list[tuple[datetime, float]]]:
    out: dict[UUID, list[tuple[datetime, float]]] = defaultdict(list)
    if not asset_ids:
        return out
    stmt = text(
        "SELECT asset_id, reading_at, odometer_km::float8 FROM wialon_odometer_readings "
        "WHERE accepted AND odometer_km IS NOT NULL AND reading_at >= :lo AND reading_at <= :hi AND asset_id IN :ids ORDER BY asset_id, reading_at"
    ).bindparams(bindparam("ids", expanding=True))
    for asset, at, km in (await db.execute(stmt, {"ids": list(asset_ids), "lo": lo, "hi": hi})).all():
        out[asset].append((at, km))
    return out


async def _load_points(db: AsyncSession, asset_ids: Sequence[UUID], source: str, lo: datetime, hi: datetime) -> dict[UUID, list[ga.P]]:
    out: dict[UUID, list[ga.P]] = defaultdict(list)
    if not asset_ids:
        return out
    rows = await db.execute(
        select(AssetPositionHistory.asset_id, AssetPositionHistory.at, AssetPositionHistory.lat, AssetPositionHistory.lon)
        .where(AssetPositionHistory.asset_id.in_(list(asset_ids)), AssetPositionHistory.source == source, AssetPositionHistory.at >= lo, AssetPositionHistory.at < hi)
        .order_by(AssetPositionHistory.asset_id, AssetPositionHistory.at)
    )
    for asset, at, lat, lon in rows.all():
        out[asset].append(ga.P(at, float(lat), float(lon)))
    return out


def _classify(a: DayAssessment, dead: bool) -> str:
    return ga.classify_cause(
        verdict=a.verdict, gtk_collected=a.gtk_collected, is_open=a.is_open, gtk_points=a.gtk_points, gtk_raw_points=a.gtk_raw_points,
        wialon_points=a.wialon_points, w_gap_h=a.wialon_gap_h, g_gap_h=a.gtk_gap_h, dead=dead,
    )


def is_dead(days: Sequence[DayAssessment]) -> bool:
    active = [d for d in days if max(d.wialon_m, d.gtk_m or 0) >= ga.ACTIVE_M and d.gtk_collected and not d.is_open]
    none = sum(1 for d in active if d.gtk_points == 0 and d.gtk_raw_points == 0)
    return len(active) >= 3 and none / len(active) >= ga.DEAD_SHARE


async def assess_days(
    db: AsyncSession, targets: dict[UUID, int | None], days: Sequence[date], now: datetime | None = None, history: Sequence[DayAssessment] = (),
) -> list[DayAssessment]:
    """Compute (not store) the assessments of `days` for every asset in `targets` (asset -> GTK unit id or None).

    `history`: earlier days of the same assets (already stored), used only to recognise a «dead» GTK tracker.
    """
    now = now or datetime.now(timezone.utc)
    offset = settings.gtk_utc_offset_hours
    today = local_today(now, offset)
    results: list[DayAssessment] = []
    gtk_ids = [g for g in targets.values() if g is not None]
    for day in sorted(days):
        start, end = local_day_bounds(day, offset)
        is_open = day >= today
        window_end = min(end, now) if is_open else end
        window_s = max(1.0, (window_end - start).total_seconds())
        w_all = await _load_points(db, list(targets), "wialon", start, window_end)
        odo_all = await _load_odometer(db, list(targets), start - timedelta(hours=5), window_end + timedelta(hours=5))
        g_all = await _load_points(db, [a for a, g in targets.items() if g is not None], "gtk_gps", start, window_end)
        figures: dict[int, GtkGpsDay] = {}
        if gtk_ids:
            rows = await db.execute(select(GtkGpsDay).where(GtkGpsDay.gtk_id.in_(gtk_ids), GtkGpsDay.day == day))
            figures = {r.gtk_id: r for r in rows.scalars()}
        for asset, gid in targets.items():
            w, g = w_all.get(asset, []), g_all.get(asset, [])
            figure = figures.get(gid) if gid is not None else None
            wm = ga.measure(w)
            w_m = round(wm.length_m + wm.bridge_m)
            g_m = figure.distance_m if figure is not None else None
            check = cmp.distance_check(g_m, len(g), w_m, len(w), gtk_collected=figure is not None)
            w_cov, w_gap_total, _ = ga.coverage_and_gaps(w, start, window_end)
            g_cov, g_gap_total, _ = ga.coverage_and_gaps(g, start, window_end) if figure is not None else (0.0, 0.0, 0.0)
            fused = ga.fuse(w, g, start, window_end)
            # a unit with no Wialon track at all: GTK's own (filtered) figure is better than the haversine of its thinned, jittery points
            fused_total = (g_m + fused.bridge_m) if (not w and g_m) else fused.total_m
            delta = ga.odometer_delta(odo_all.get(asset, []), start, window_end)
            odo_m = round(delta * 1000) if delta is not None and delta > 0 else None
            odo_agrees = ga.odometer_corroborates(w_m, odo_m)
            confidence = ga.day_confidence(fused.covered_h * 3600 / window_s, check.verdict, len(w), len(g), odo_agrees) if (w or g) else None
            events = figure.events if figure is not None and figure.events else {}
            a = DayAssessment(
                asset_id=asset, day=day, wialon_m=w_m, wialon_points=len(w), gtk_m=g_m, gtk_points=len(g),
                gtk_raw_points=figure.points if figure is not None else 0, gtk_final=bool(figure.is_final) if figure is not None else False,
                gtk_collected=figure is not None, verdict=check.verdict, ratio=check.ratio, diff_m=check.diff_m,
                fused_m=round(fused_total) if (w or g) else None, unknown_gap_m=round(fused.bridge_m) if (w or g) else None,
                wialon_cov_h=round(w_cov, 2), gtk_cov_h=round(g_cov, 2), wialon_gap_h=round(w_gap_total, 2), gtk_gap_h=round(g_gap_total, 2),
                cause="ok", confidence=confidence, idle_events=sum(v for k, v in events.items() if IDLE_KINDS in k) if events else None,
                is_final=(not is_open) and figure is not None and bool(figure.is_final), is_open=is_open, odo_m=odo_m, odo_agrees=odo_agrees,
            )
            a.cause = _classify(a, dead=False)
            results.append(a)
    # an asset whose GTK tracker was silent on (almost) all its active days: «dead», not a string of separate bad days
    by_asset: dict[UUID, list[DayAssessment]] = defaultdict(list)
    for a in results:
        by_asset[a.asset_id].append(a)
    earlier: dict[UUID, list[DayAssessment]] = defaultdict(list)
    for a in history:
        earlier[a.asset_id].append(a)
    for asset, items in by_asset.items():
        if is_dead([*items, *(h for h in earlier.get(asset, []) if h.day not in {i.day for i in items})]):
            for a in items:
                a.cause = _classify(a, dead=True)
    return results


_COLUMNS = (
    "wialon_m", "wialon_points", "gtk_m", "gtk_points", "gtk_raw_points", "gtk_final", "gtk_collected", "verdict", "ratio", "diff_m", "fused_m",
    "unknown_gap_m", "wialon_cov_h", "gtk_cov_h", "wialon_gap_h", "gtk_gap_h", "cause", "confidence", "idle_events", "odo_m", "odo_agrees", "is_final", "algorithm_version",
)


async def persist(db: AsyncSession, items: Sequence[DayAssessment], now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    rows = []
    for a in items:
        row = {"asset_id": a.asset_id, "day": a.day, "computed_at": now}
        for c in _COLUMNS:
            v = getattr(a, c)
            row[c] = Decimal(str(v)) if isinstance(v, float) else v
        rows.append(row)
    for i in range(0, len(rows), 500):
        stmt = insert(GpsDayAssessment).values(rows[i : i + 500])
        await db.execute(stmt.on_conflict_do_update(index_elements=["asset_id", "day"], set_={c: getattr(stmt.excluded, c) for c in (*_COLUMNS, "computed_at")}))
    return len(rows)


def _from_row(r: GpsDayAssessment) -> DayAssessment:
    f = lambda v: None if v is None else float(v)  # noqa: E731
    return DayAssessment(
        asset_id=r.asset_id, day=r.day, wialon_m=r.wialon_m, wialon_points=r.wialon_points, gtk_m=r.gtk_m, gtk_points=r.gtk_points,
        gtk_raw_points=r.gtk_raw_points, gtk_final=r.gtk_final, gtk_collected=r.gtk_collected, verdict=r.verdict, ratio=f(r.ratio), diff_m=r.diff_m,
        fused_m=r.fused_m, unknown_gap_m=r.unknown_gap_m, wialon_cov_h=f(r.wialon_cov_h) or 0.0, gtk_cov_h=f(r.gtk_cov_h) or 0.0,
        wialon_gap_h=f(r.wialon_gap_h) or 0.0, gtk_gap_h=f(r.gtk_gap_h) or 0.0, cause=r.cause, confidence=f(r.confidence), idle_events=r.idle_events,
        is_final=r.is_final, odo_m=r.odo_m, odo_agrees=r.odo_agrees, algorithm_version=r.algorithm_version, persisted=True,
    )


async def load_stored(db: AsyncSession, asset_ids: Sequence[UUID], day_from: date, day_to: date) -> dict[tuple[UUID, date], DayAssessment]:
    if not asset_ids:
        return {}
    rows = await db.execute(select(GpsDayAssessment).where(GpsDayAssessment.asset_id.in_(list(asset_ids)), GpsDayAssessment.day >= day_from, GpsDayAssessment.day <= day_to))
    return {(r.asset_id, r.day): _from_row(r) for r in rows.scalars()}


async def ensure_days(
    db: AsyncSession, targets: dict[UUID, int | None], days: Sequence[date], now: datetime | None = None, *, max_live_past: int = 3,
) -> dict[tuple[UUID, date], DayAssessment]:
    """What the page shows: stored rows for finished days, live computation for today and for anything not stored yet."""
    now = now or datetime.now(timezone.utc)
    today = local_today(now, settings.gtk_utc_offset_hours)
    stored = await load_stored(db, list(targets), min(days), max(days))
    out: dict[tuple[UUID, date], DayAssessment] = {}
    missing: dict[date, dict[UUID, int | None]] = defaultdict(dict)
    for asset, gid in targets.items():
        for day in days:
            row = stored.get((asset, day))
            if row is not None and day < today:
                out[(asset, day)] = row
            else:
                missing[day][asset] = gid
    # today is always live; of the past days that are not stored yet only the newest few are computed on the spot (the CLI/job fills the rest)
    past = sorted((d for d in missing if d < today), reverse=True)[:max_live_past]
    for day in [d for d in missing if d >= today] + past:
        for a in await assess_days(db, missing[day], [day], now):
            out[(a.asset_id, a.day)] = a
    return out


async def assess_recent(db: AsyncSession, now: datetime | None = None, *, back_days: int = 3) -> int:
    """After every GTK GPS cycle: today, yesterday and any not-yet-final day of the last `back_days` days for the linked locomotives."""
    now = now or datetime.now(timezone.utc)
    targets: dict[UUID, int | None] = {asset: gid for gid, asset in (await gtk_gps.linked_targets(db)).items()}
    if not targets:
        return 0
    today = local_today(now, settings.gtk_utc_offset_hours)
    window = [today - timedelta(days=i) for i in range(back_days + 1)]
    stored = await load_stored(db, list(targets), window[-1], window[0])
    todo = [d for d in window if d == today or any(not (stored.get((a, d)) and stored[(a, d)].is_final) for a in targets)]
    prior = await load_stored(db, list(targets), today - timedelta(days=back_days + 14), today - timedelta(days=back_days + 1))
    items = await assess_days(db, targets, todo, now, history=list(prior.values()))
    n = await persist(db, items, now)
    await db.commit()
    return n


async def assess_range(db: AsyncSession, days: int, now: datetime | None = None) -> int:
    """CLI backfill: recompute the last `days` local days (the page needs them stored for speed and for the tracker-health window)."""
    now = now or datetime.now(timezone.utc)
    targets: dict[UUID, int | None] = {asset: gid for gid, asset in (await gtk_gps.linked_targets(db)).items()}
    today = local_today(now, settings.gtk_utc_offset_hours)
    items = await assess_days(db, targets, [today - timedelta(days=back) for back in range(days, -1, -1)], now)
    total = await persist(db, items, now)
    await db.commit()
    return total
