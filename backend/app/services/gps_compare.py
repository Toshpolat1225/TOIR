"""Wialon GPS vs GTK GPS: two independent trackers on the same locomotives, compared and merged.

Pure functions (no database): position verdict, daily-distance verdict and the unified value. Thresholds were measured on live
data (2026-11-17): moving units differ by 200-700 m because the two fixes are taken at different seconds (~2 min apart), parked
units by 2-80 m; a GTK tracker that stopped reporting shows an age of hours/days with a Wialon fix still fresh; the daily GTK
`distance` is 0.92-1.00 of the Wialon track length when both trackers work.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

FRESH = timedelta(minutes=30)  # a fix older than this is "stale" (the unit is parked/offline or the tracker stopped)
BASE_TOLERANCE_M = 200.0  # GPS noise + different fix seconds even when parked
EXTRA_SECONDS = 30.0  # slack added to the lag between the two fixes when estimating how far a moving unit travelled
SAME_SPOT_M = 150.0  # two stale fixes this close are the same parking spot

IDLE_M = 1000  # a day below this is "did not drive"
MATCH_LOW, MATCH_HIGH = 0.85, 1.15
MINOR_LOW, MINOR_HIGH = 0.60, 1.60

PositionVerdict = Literal[
    "confirmed",  # both fresh and at the same place (within the tolerance for their time lag and speed)
    "diverged",  # both fresh but apart: one of them is wrong
    "gtk_stale",  # GTK stopped reporting while Wialon is fresh
    "wialon_stale",  # Wialon stopped reporting while GTK is fresh
    "both_stale_agree",  # both silent, same parking spot
    "both_stale_apart",  # both silent and at different places
    "wialon_only",  # no GTK GPS for this asset (unit not linked / no fix)
    "gtk_only",
    "no_position",
]
DistanceVerdict = Literal["match", "minor_diff", "gtk_gap", "wialon_gap", "idle", "no_data", "not_collected"]


@dataclass(frozen=True)
class SourceFix:
    lat: float | None
    lon: float | None
    at: datetime | None = None
    speed: float | None = None  # km/h

    @property
    def valid(self) -> bool:
        return (
            self.lat is not None
            and self.lon is not None
            and abs(self.lat) <= 90
            and abs(self.lon) <= 180
            and not (self.lat == 0 and self.lon == 0)
        )


@dataclass(frozen=True)
class PositionCheck:
    verdict: PositionVerdict
    diff_m: float | None = None
    lag_s: float | None = None  # |GTK time - Wialon time|
    tolerance_m: float | None = None
    wialon_age_min: float | None = None
    gtk_age_min: float | None = None
    best: Literal["wialon", "gtk"] | None = None  # the source to draw: the newer valid fix


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _age_min(fix: SourceFix, now: datetime) -> float | None:
    at = _aware(fix.at)
    return None if at is None else max(0.0, (now - at).total_seconds() / 60)


def _is_fresh(age: float | None) -> bool:
    return age is not None and age <= FRESH.total_seconds() / 60


def position_check(wialon: SourceFix | None, gtk: SourceFix | None, now: datetime) -> PositionCheck:
    """Compare the two live positions of one asset. A missing time counts as stale (it cannot be shown to be fresh)."""
    w = wialon if wialon is not None and wialon.valid else None
    g = gtk if gtk is not None and gtk.valid else None
    w_age = _age_min(w, now) if w else None
    g_age = _age_min(g, now) if g else None
    if w is None and g is None:
        return PositionCheck("no_position")
    if g is None:
        return PositionCheck("wialon_only", wialon_age_min=w_age, best="wialon")
    if w is None:
        return PositionCheck("gtk_only", gtk_age_min=g_age, best="gtk")

    diff = haversine_m(w.lat, w.lon, g.lat, g.lon)  # type: ignore[arg-type]
    w_at, g_at = _aware(w.at), _aware(g.at)
    lag = abs((g_at - w_at).total_seconds()) if (w_at and g_at) else None
    speeds = [s for s in (w.speed, g.speed) if s is not None]
    vmax = (max(speeds) / 3.6) if speeds else 0.0
    tolerance = BASE_TOLERANCE_M + vmax * ((lag or 0.0) + EXTRA_SECONDS)
    # draw the newer fix (ties: Wialon, the longer-established source)
    best = "gtk" if (g_at and w_at and g_at > w_at) or (g_at and not w_at) else "wialon"
    common = dict(diff_m=diff, lag_s=lag, tolerance_m=tolerance, wialon_age_min=w_age, gtk_age_min=g_age, best=best)
    w_fresh, g_fresh = _is_fresh(w_age), _is_fresh(g_age)
    if w_fresh and g_fresh:
        return PositionCheck("confirmed" if diff <= tolerance else "diverged", **common)  # type: ignore[arg-type]
    if w_fresh:
        return PositionCheck("gtk_stale", **{**common, "best": "wialon"})  # type: ignore[arg-type]
    if g_fresh:
        return PositionCheck("wialon_stale", **{**common, "best": "gtk"})  # type: ignore[arg-type]
    return PositionCheck("both_stale_agree" if diff <= SAME_SPOT_M else "both_stale_apart", **common)  # type: ignore[arg-type]


@dataclass(frozen=True)
class DistanceCheck:
    verdict: DistanceVerdict
    ratio: float | None  # GTK / Wialon
    unified_m: int | None  # the one number to trust (see `unify_distance`)
    diff_m: int | None  # GTK - Wialon


def unify_distance(gtk_m: int | None, wialon_m: int | None, verdict: DistanceVerdict) -> int | None:
    """One distance per day: both agree -> their mean; one tracker has a gap -> the fuller one; otherwise the larger (the fuller track)."""
    values = [v for v in (gtk_m, wialon_m) if v is not None]
    if not values:
        return None
    if verdict == "match" and len(values) == 2:
        return round(sum(values) / 2)
    return max(values)


def distance_check(gtk_m: int | None, gtk_points: int, wialon_m: int | None, wialon_points: int, *, gtk_collected: bool = True) -> DistanceCheck:
    """Compare the distance one day gave in GTK (`distance`, server-computed) and in Wialon (length of the stored track).

    `gtk_collected=False`: we never fetched that GTK day (before the integration started): that is not a GTK gap.
    """
    if not gtk_collected:
        return DistanceCheck("not_collected", None, wialon_m, None)
    g = gtk_m if gtk_m is not None else 0
    w = wialon_m if wialon_m is not None else 0
    if gtk_points == 0 and wialon_points == 0 and g == 0 and w == 0:
        return DistanceCheck("no_data", None, None, None)
    diff = g - w
    if g < IDLE_M and w < IDLE_M:
        return DistanceCheck("idle", None, unify_distance(gtk_m, wialon_m, "idle"), diff)
    if g < IDLE_M <= w:
        verdict: DistanceVerdict = "gtk_gap"
        return DistanceCheck(verdict, 0.0 if w else None, unify_distance(gtk_m, wialon_m, verdict), diff)
    if w < IDLE_M <= g:
        verdict = "wialon_gap"
        return DistanceCheck(verdict, None, unify_distance(gtk_m, wialon_m, verdict), diff)
    ratio = g / w
    if MATCH_LOW <= ratio <= MATCH_HIGH:
        verdict = "match"
    elif MINOR_LOW <= ratio < MATCH_LOW or MATCH_HIGH < ratio <= MINOR_HIGH:
        verdict = "minor_diff"
    elif ratio < MINOR_LOW:
        verdict = "gtk_gap"
    else:
        verdict = "wialon_gap"
    return DistanceCheck(verdict, round(ratio, 3), unify_distance(gtk_m, wialon_m, verdict), diff)


# Severity of a verdict, to rank an asset by its worst problem (higher = worse). Used by the overview and the map.
POSITION_SEVERITY: dict[str, int] = {
    "confirmed": 0, "both_stale_agree": 0, "wialon_only": 1, "gtk_only": 1, "no_position": 1,
    "wialon_stale": 2, "gtk_stale": 2, "both_stale_apart": 2, "diverged": 3,
}
DISTANCE_SEVERITY: dict[str, int] = {"match": 0, "idle": 0, "no_data": 0, "not_collected": 0, "minor_diff": 1, "gtk_gap": 2, "wialon_gap": 2}
