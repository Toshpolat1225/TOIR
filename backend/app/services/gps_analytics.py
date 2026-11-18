"""Analytics on top of the two trackers: causes of a difference, the «единый трек», tracker health, wagon mileage candidates.

Pure functions (no database). Rules were derived from 30 days of live data (2026-10-18..11-16, 1527 active locomotive-days):
90% of the days where GTK and Wialon disagree are GTK data holes (no points that day, or >= 2 h of silence), not measurement
differences; on days without holes the two agree within ~1-2%. Nothing here «corrects» a distance with a model: it explains,
fills a hole from the other tracker, and says how much of the day is actually covered.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.services.gps_compare import IDLE_M, haversine_m

TELEPORT_KMH = 120.0  # a hop faster than this between two fixes is noise, not movement
BRIDGE_S = 60 * 60  # consecutive fixes further apart than this are a silent stretch (a straight-line bridge only)
FILL_GAP_S = 25 * 60  # fill a Wialon hole from GTK only when it is longer than the 20-minute parked heartbeat (+margin)
GAP_LONG_H = 2.0  # a tracker silent this long on a day has «gaps»
SPARSE_SHARE = 0.4  # GTK stores < 40% of the points Wialon stores although neither has long gaps
DEAD_SHARE = 0.9
ACTIVE_M = 5000  # a day with at least this in either tracker is an «active» day
ALGORITHM_VERSION = "gps-analytics-1"

Cause = str  # ok | method | day_open | gtk_dead | gtk_no_day | gtk_gaps | gtk_sparse | wialon_gaps | both_gaps | not_collected | idle | no_data


@dataclass(frozen=True)
class P:
    at: datetime
    lat: float
    lon: float


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _sorted(points: Sequence[P]) -> list[P]:
    return sorted(points, key=lambda p: _aware(p.at))


# ---- lengths, coverage, gaps -------------------------------------------------------------------------------
@dataclass(frozen=True)
class Length:
    length_m: float  # segments between fixes <= 60 min apart (teleports dropped)
    bridge_m: float  # straight lines over silent stretches (> 60 min)
    covered_s: float  # time covered by fixes no further apart than 60 min
    dropped: int  # teleport hops dropped


def measure(points: Sequence[P]) -> Length:
    pts = _sorted(points)
    length = bridge = covered = 0.0
    dropped = 0
    for a, b in zip(pts, pts[1:]):
        dt = (_aware(b.at) - _aware(a.at)).total_seconds()
        if dt <= 0:
            continue
        d = haversine_m(a.lat, a.lon, b.lat, b.lon)
        if dt <= BRIDGE_S:
            covered += dt
            if d / dt * 3.6 > TELEPORT_KMH:
                dropped += 1
                continue
            length += d
        else:
            bridge += d
    return Length(length, bridge, covered, dropped)


def coverage_and_gaps(points: Sequence[P], start: datetime, end: datetime) -> tuple[float, float, float]:
    """(covered hours, total hours of silence > 60 min, longest silence in hours) inside [start, end]; the window edges count as gaps."""
    start, end = _aware(start), _aware(end)
    total = max(0.0, (end - start).total_seconds())
    pts = [p for p in _sorted(points) if start <= _aware(p.at) <= end]
    if not pts:
        return 0.0, total / 3600, total / 3600
    covered = gap_total = gap_max = 0.0
    edges = [start] + [_aware(p.at) for p in pts] + [end]
    for a, b in zip(edges, edges[1:]):
        dt = (b - a).total_seconds()
        if dt <= BRIDGE_S:
            covered += dt
        else:
            gap_total += dt
            gap_max = max(gap_max, dt)
    return covered / 3600, gap_total / 3600, gap_max / 3600


# ---- the fused track ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fused:
    points: list[P]
    length_m: float
    bridge_m: float
    covered_h: float
    gtk_added: int

    @property
    def total_m(self) -> float:
        return self.length_m + self.bridge_m


def fuse(wialon: Sequence[P], gtk: Sequence[P], start: datetime, end: datetime) -> Fused:
    """Wialon is the timeline (dense and complete); a GTK fix joins only inside a Wialon hole longer than FILL_GAP_S."""
    w = [p for p in _sorted(wialon)]
    g = _sorted(gtk)
    w_times = [_aware(p.at) for p in w]
    added: list[P] = []
    for gp in g:
        t = _aware(gp.at)
        i = bisect_left(w_times, t)
        prev = w_times[i - 1] if i > 0 else None
        nxt = w_times[i] if i < len(w_times) else None
        if (prev is None or (t - prev).total_seconds() > FILL_GAP_S) and (nxt is None or (nxt - t).total_seconds() > FILL_GAP_S):
            added.append(gp)
    merged = _sorted(w + added)
    window = [p for p in merged if _aware(start) <= _aware(p.at) <= _aware(end)]
    m = measure(window)
    covered_h, _, _ = coverage_and_gaps(window, start, end)
    return Fused(window, m.length_m, m.bridge_m, covered_h, len(added))


ODOMETER_TOLERANCE = 0.15  # the odometer counts a little more than a thinned track (measured: median track/odometer 0.973)


def odometer_corroborates(track_m: float, odometer_m: float | None) -> bool | None:
    """Does the Wialon odometer confirm the Wialon track length of the day? None when either is too small to say."""
    if odometer_m is None or odometer_m < IDLE_M or track_m < IDLE_M:
        return None
    return abs(odometer_m - track_m) / max(odometer_m, track_m) <= ODOMETER_TOLERANCE


def day_confidence(coverage_frac: float, verdict: str, wialon_points: int, gtk_points: int, odometer_agrees: bool | None = None) -> float:
    """Coverage of the window by the fused track x how well the sources agree.

    Two trackers that match, or a lone tracker that the odometer corroborates (two of three sources agree), are fully trusted; a lone
    tracker nothing confirms, or two trackers that disagree, are not.
    """
    if verdict in ("match", "idle"):
        agree = 1.0
    elif odometer_agrees:
        agree = 0.97 if (wialon_points and gtk_points) else 1.0
    elif wialon_points and gtk_points:
        agree = 0.85  # both reported but disagree
    else:
        agree = 0.9  # only one tracker has data: nothing to confirm it against
    return round(max(0.0, min(1.0, coverage_frac)) * agree, 2)


# ---- why the two disagree ----------------------------------------------------------------------------------
def classify_cause(
    *, verdict: str, gtk_collected: bool, is_open: bool, gtk_points: int, gtk_raw_points: int, wialon_points: int,
    w_gap_h: float, g_gap_h: float, dead: bool = False,
) -> Cause:
    if not gtk_collected:
        return "not_collected"
    if verdict in ("idle", "no_data"):
        return verdict
    if verdict == "match":
        return "ok"
    if is_open:
        return "day_open"  # today is still being written: a difference is not yet a fault
    if dead:
        return "gtk_dead"
    if gtk_points == 0 and gtk_raw_points == 0 and verdict == "gtk_gap":
        return "gtk_no_day"
    w_gaps, g_gaps = w_gap_h >= GAP_LONG_H, g_gap_h >= GAP_LONG_H
    if w_gaps and g_gaps:
        return "both_gaps"
    if g_gaps:
        return "gtk_gaps"
    if w_gaps:
        return "wialon_gaps"
    if verdict in ("gtk_gap", "minor_diff") and wialon_points and gtk_points < SPARSE_SHARE * wialon_points:
        return "gtk_sparse"
    return "method"


CAUSE_TEXT = {
    "ok": "Пробеги совпали.",
    "method": "Оба трекера писали без провалов; разница — в методе подсчёта (фильтрация/прореживание).",
    "day_open": "День ещё не закончился: цифры будут дополняться.",
    "gtk_dead": "GTK-трекер этого локомотива давно не передаёт данные: единый пробег берётся из Wialon.",
    "gtk_no_day": "GTK не прислал ни одной точки за этот день; единый пробег — из Wialon.",
    "gtk_gaps": "GTK молчал более {g_gap} ч за сутки при непрерывном Wialon; недостающий пробег GTK — потеря данных, не движение.",
    "gtk_sparse": "GTK присылает слишком мало точек при движении; его пробег занижен, единый — из Wialon.",
    "wialon_gaps": "Wialon молчал более {w_gap} ч, GTK писал непрерывно: провал заполнен по GTK.",
    "both_gaps": "У обоих трекеров есть провалы: единый пробег неполный, ориентируйтесь на уверенность.",
    "not_collected": "GTK за этот день ещё не загружен; показан пробег Wialon.",
    "idle": "Локомотив почти не двигался (менее 1 км по обоим трекерам).",
    "no_data": "Нет данных ни в одном трекере.",
}


def explain_day(cause: Cause, *, w_gap_h: float = 0.0, g_gap_h: float = 0.0) -> str:
    return CAUSE_TEXT.get(cause, "").format(g_gap=f"{g_gap_h:.1f}".rstrip("0").rstrip("."), w_gap=f"{w_gap_h:.1f}".rstrip("0").rstrip("."))


POSITION_TEXT = {
    "confirmed": "Оба трекера свежие и показывают одно место.",
    "diverged": "Оба трекера свежие, но точки далеко друг от друга: один из них ошибается.",
    "gtk_stale": "GTK давно не присылает позицию, Wialon свежий: положение берётся из Wialon.",
    "wialon_stale": "Wialon давно не присылает позицию, GTK свежий: положение берётся из GTK.",
    "both_stale_agree": "Оба трекера давно молчат, но последние точки совпадают: техника, вероятно, стоит.",
    "both_stale_apart": "Оба трекера молчат, а последние точки в разных местах.",
    "wialon_only": "Есть только Wialon: подтвердить положение нечем.",
    "gtk_only": "Есть только GTK: подтвердить положение нечем.",
    "no_position": "Ни один трекер не дал координат.",
}


# ---- tracker health ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DayFact:
    wialon_m: int
    gtk_m: int | None
    gtk_points: int
    cause: str
    verdict: str


@dataclass(frozen=True)
class Health:
    health_class: str  # ok | intermittent | dead | frozen | no_gtk
    window_days: int
    active_days: int
    ok_days: int
    partial_days: int
    none_days: int
    km_lost_m: int
    ok_share: float | None
    last_gtk_fix_age_h: float | None = None


def health_of(days: Sequence[DayFact], *, gtk_linked: bool, last_gtk_fix_age_h: float | None = None) -> Health:
    active = [d for d in days if max(d.wialon_m, d.gtk_m or 0) >= ACTIVE_M and d.cause not in ("not_collected", "day_open")]
    ok = sum(1 for d in active if d.cause == "ok")
    none = sum(1 for d in active if d.cause in ("gtk_no_day", "gtk_dead"))
    partial = len(active) - ok - none
    lost = sum(max(0, d.wialon_m - (d.gtk_m or 0)) for d in active if d.cause in ("gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse"))
    share = round(ok / len(active), 2) if active else None
    frozen_days = sum(1 for d in active if d.gtk_points > 0 and (d.gtk_m or 0) < 0.05 * d.wialon_m and d.wialon_m >= ACTIVE_M)
    dead = (len(active) >= 3 and none / len(active) >= DEAD_SHARE) or (last_gtk_fix_age_h is not None and last_gtk_fix_age_h > 168)
    if not gtk_linked:
        cls = "no_gtk"
    elif dead:
        cls = "dead"
    elif frozen_days >= 3:
        cls = "frozen"
    elif not active or (share is not None and share >= 0.8):
        cls = "ok"
    else:
        cls = "intermittent"
    return Health(cls, len(days), len(active), ok, partial, none, int(lost), share, last_gtk_fix_age_h)


HEALTH_TEXT = {
    "ok": "GTK-трекер работает устойчиво.",
    "intermittent": "GTK-трекер работает с перебоями: часть суток пропадает.",
    "dead": "GTK-трекер этого локомотива почти не передаёт данные.",
    "frozen": "GTK присылает свежие метки времени, но пробег почти нулевой: трекер «замёрз» на одном месте.",
    "no_gtk": "Локомотив не связан с GTK-юнитом.",
}


# ---- wagon mileage candidates ------------------------------------------------------------------------------
def odometer_at(readings: Sequence[tuple[datetime, float]], t: datetime, max_gap_s: float = 240 * 60, edge_s: float = 600.0) -> float | None:
    """Odometer (km) at an instant by linear interpolation between the two readings around it; None when the bracket is too wide.

    At the very ends (before the first / after the last reading) a reading within `edge_s` is used as is.
    """
    if not readings:
        return None
    ts = [_aware(r[0]) for r in readings]
    t = _aware(t)
    i = bisect_right(ts, t)
    if i == 0:
        return readings[0][1] if (ts[0] - t).total_seconds() <= edge_s else None
    if i >= len(ts):
        return readings[-1][1] if (t - ts[-1]).total_seconds() <= edge_s else None
    t0, v0, t1, v1 = ts[i - 1], readings[i - 1][1], ts[i], readings[i][1]
    span = (t1 - t0).total_seconds()
    if span <= 0 or span > max_gap_s:
        return None
    return v0 + (v1 - v0) * ((t - t0).total_seconds() / span)


def odometer_delta(readings: Sequence[tuple[datetime, float]], t0: datetime, t1: datetime) -> float | None:
    a, b = odometer_at(readings, t0), odometer_at(readings, t1)
    if a is None or b is None or b < a:
        return None
    return b - a


def _interp(a: P, b: P, t: datetime) -> P:
    span = (_aware(b.at) - _aware(a.at)).total_seconds()
    f = 0.0 if span <= 0 else (_aware(t) - _aware(a.at)).total_seconds() / span
    return P(t, a.lat + (b.lat - a.lat) * f, a.lon + (b.lon - a.lon) * f)


def window_track(points: Sequence[P], t0: datetime, t1: datetime) -> list[P]:
    """The fixes inside [t0, t1] with the two ends interpolated on the polyline (only when the neighbouring fixes are <= 60 min apart)."""
    pts = _sorted(points)
    t0, t1 = _aware(t0), _aware(t1)
    times = [_aware(p.at) for p in pts]
    inside = [p for p in pts if t0 <= _aware(p.at) <= t1]
    out = list(inside)
    i = bisect_left(times, t0)
    if 0 < i < len(pts) and times[i] > t0 and (times[i] - times[i - 1]).total_seconds() <= BRIDGE_S:
        out.insert(0, _interp(pts[i - 1], pts[i], t0))
    j = bisect_right(times, t1)
    if 0 < j < len(pts) and times[j - 1] < t1 and (times[j] - times[j - 1]).total_seconds() <= BRIDGE_S:
        out.append(_interp(pts[j - 1], pts[j], t1))
    return out


@dataclass(frozen=True)
class Candidates:
    a_odometer: float | None
    b_wialon: float | None
    c_gtk: float | None
    d_fused: float | None
    coverage_w: float
    coverage_g: float
    coverage_d: float


def candidates(
    wialon: Sequence[P], gtk: Sequence[P], odometer: Sequence[tuple[datetime, float]], t0: datetime, t1: datetime,
) -> Candidates:
    """A odometer delta, B Wialon track, C GTK track, D fused track for [t0, t1], in km."""
    span = max(1.0, (_aware(t1) - _aware(t0)).total_seconds())
    w, g = window_track(wialon, t0, t1), window_track(gtk, t0, t1)
    mw, mg = measure(w), measure(g)
    fused = fuse(window_track(wialon, t0 - timedelta(hours=1), t1 + timedelta(hours=1)), window_track(gtk, t0 - timedelta(hours=1), t1 + timedelta(hours=1)), t0, t1)
    cov_w, cov_g = (mw.covered_s / span if len(w) > 1 else 0.0), (mg.covered_s / span if len(g) > 1 else 0.0)
    cov_d = fused.covered_h * 3600 / span
    a = odometer_delta(odometer, t0, t1)
    return Candidates(
        None if a is None else round(a, 3),
        round(mw.length_m / 1000, 3) if len(w) > 1 else None,
        round(mg.length_m / 1000, 3) if len(g) > 1 else None,
        round(fused.total_m / 1000, 3) if len(fused.points) > 1 else None,
        round(min(1.0, cov_w), 3), round(min(1.0, cov_g), 3), round(min(1.0, cov_d), 3),
    )


@dataclass(frozen=True)
class Selection:
    selected_km: float | None
    basis: str  # fused_track | track | conflict | single_source | held
    confidence: str  # high | medium | low | none
    flags: list[str] = field(default_factory=list)


def _close(a: float | None, b: float | None, tol: float = 0.10) -> bool:
    if a is None or b is None:
        return False
    top = max(a, b)
    return top <= 0.05 or abs(a - b) / top <= tol


def select_candidate(c: Candidates) -> Selection:
    """The selection rule of docs/ROADMAP_GPS_PROBEG_2026-11-18.md §4.2 (sources are never summed or averaged)."""
    if c.d_fused is not None and c.coverage_d >= 0.9:
        agree = sum(1 for other in (c.a_odometer, c.b_wialon, c.c_gtk) if _close(c.d_fused, other))
        return Selection(c.d_fused, "fused_track", "high" if agree >= 1 else "medium")
    if c.a_odometer is not None and c.b_wialon is not None:
        if _close(c.a_odometer, c.b_wialon):
            return Selection(c.b_wialon, "track", "medium")
        pick_track = c.coverage_w >= 0.5
        return Selection(c.b_wialon if pick_track else c.a_odometer, "conflict", "low", ["odometer_track_conflict"])
    present = [(name, v) for name, v in (("fused", c.d_fused), ("wialon", c.b_wialon), ("odometer", c.a_odometer), ("gtk", c.c_gtk)) if v is not None]
    if present:
        return Selection(present[0][1], "single_source", "low", ["single_source:" + present[0][0]])
    return Selection(None, "held", "none", ["no_data"])
