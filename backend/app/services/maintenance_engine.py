"""Pure planning engine of the "Tirik reja" model: no database, no clock (`today` is passed in).

Everything here is deterministic and unit-tested; the services feed it facts and persist its answers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

ZERO = Decimal("0")
HUNDRED = Decimal("100")
# Normative limits that mean "no runaway planning": nothing is planned further than this from today.
MAX_PLANNING_DAYS = 3650


# ── Pace (how fast a unit uses its meters) ───────────────────────────────────

@dataclass(frozen=True)
class Pace:
    p25: Decimal  # slow  -> the limit is reached late
    p50: Decimal  # typical
    p75: Decimal  # fast  -> the limit is reached early (the cautious planning pace)
    n_days: int  # days of observation behind the estimate
    source: str  # 'asset' | 'blend' | 'group' | 'setting' | 'default'

    @property
    def reliable(self) -> bool:
        return self.source == "asset"


def quantile(values: Sequence[Decimal], q: float) -> Decimal:
    """Linear-interpolated quantile (same definition as PostgreSQL percentile_cont)."""
    if not values:
        raise ValueError("quantile of an empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = Decimal(str(position - low))
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def daily_deltas(
    readings: Iterable[tuple[date, Decimal]], *, first_day: date, last_day: date
) -> list[Decimal]:
    """Per-day growth of a cumulative meter over the calendar days first_day+1 .. last_day.

    A day without a reading keeps the last known value, so idle days count as 0 (a typical day
    of an asset that sits still is part of its real pace). Meter corrections never go negative.
    """
    by_day: dict[date, Decimal] = {}
    for day, value in readings:
        if day not in by_day or value > by_day[day]:
            by_day[day] = value
    if not by_day:
        return []
    known = sorted(by_day.items())
    # End-of-day value for every calendar day (a day without a reading keeps the last known value).
    values: list[Decimal] = []
    index = 0
    last_value: Decimal | None = None
    day = first_day
    while day <= last_day:
        while index < len(known) and known[index][0] <= day:
            last_value = known[index][1]
            index += 1
        if last_value is not None:
            values.append(last_value)
        day += timedelta(days=1)
    return [max(ZERO, values[i] - values[i - 1]) for i in range(1, len(values))]


def _flat_pace(value: Decimal, source: str, n_days: int = 0) -> Pace:
    return Pace(p25=value, p50=value, p75=value, n_days=n_days, source=source)


def own_pace(deltas: Sequence[Decimal]) -> Pace | None:
    """The raw quantiles of an asset's own days (no blending); None when it has no history."""
    if not deltas:
        return None
    return Pace(quantile(deltas, 0.25), quantile(deltas, 0.50), quantile(deltas, 0.75), len(deltas), "asset")


def estimate_pace(
    deltas: Sequence[Decimal],
    *,
    group: Pace | None,
    fallback_per_day: Decimal,
    fallback_source: str = "default",
    min_days: int = 7,
    shrink_k: int = 7,
) -> Pace:
    """Pace of one asset: its own recent days, pulled toward its group while data is thin.

    weight = n / (n + k): 30 days of data count ~80 %, 3 days ~30 %, none: the group (or the fallback).
    """
    n = len(deltas)
    if n == 0:
        return Pace(group.p25, group.p50, group.p75, 0, "group") if group is not None else _flat_pace(fallback_per_day, fallback_source)
    own = (quantile(deltas, 0.25), quantile(deltas, 0.50), quantile(deltas, 0.75))
    if group is None and n >= min_days:
        # enough own data and nothing better to compare with: a flat guess must not dilute it
        return Pace(own[0], own[1], own[2], n, "asset")
    # Thin data is blended with the group (or, lacking one, the flat fallback) so it cannot swing wildly.
    base = (fallback_per_day,) * 3 if group is None else (group.p25, group.p50, group.p75)
    weight = Decimal(n) / Decimal(n + shrink_k)
    mixed = tuple(weight * own_value + (Decimal(1) - weight) * base_value for own_value, base_value in zip(own, base))
    source = "asset" if n >= min_days else "blend"
    return Pace(mixed[0], mixed[1], mixed[2], n, source)


def group_pace(asset_paces: Sequence[Pace], *, min_days: int = 3) -> Pace | None:
    """Typical pace of a group of assets: the median of the members that have some history."""
    usable = [pace for pace in asset_paces if pace.n_days >= min_days]
    if not usable:
        return None
    return Pace(
        p25=quantile([pace.p25 for pace in usable], 0.5),
        p50=quantile([pace.p50 for pace in usable], 0.5),
        p75=quantile([pace.p75 for pace in usable], 0.5),
        n_days=sum(pace.n_days for pace in usable),
        source="group",
    )


# ── Obligation markers ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MeterInput:
    name: str  # 'km' | 'hours'
    limit: Decimal
    baseline: Decimal
    current: Decimal
    pace: Pace


@dataclass(frozen=True)
class CalendarInput:
    limit_days: int
    baseline_date: date


@dataclass(frozen=True)
class Markers:
    as_of: date
    limiting: str | None  # 'km' | 'hours' | 'days' | None when nothing can be projected
    used: Decimal
    limit: Decimal
    remaining: Decimal  # > 0 before the limit, <= 0 once it is reached
    tolerance: Decimal  # permitted overrun in the limiting unit
    pace_p50: Decimal  # per day, in the limiting unit
    date_p75: date | None  # cautious: the visit must not be later than this
    date_p50: date | None
    date_p25: date | None
    window_open: date | None
    state: str  # 'forecast' | 'due_soon' | 'over_limit' | 'over_tolerance'

    def projected_used(self, on: date) -> Decimal:
        return self.used + self.pace_p50 * Decimal(max(0, (on - self.as_of).days))

    def overrun_on(self, on: date) -> Decimal:
        """How far past the limit the unit will be on `on` at its typical pace (0 if still inside)."""
        return max(ZERO, self.projected_used(on) - self.limit)

    def beyond_tolerance_on(self, on: date) -> bool:
        return self.overrun_on(on) > self.tolerance


def project_date(today: date, remaining: Decimal, pace_per_day: Decimal) -> date | None:
    """The day a meter with `remaining` left runs out; a past date when it already has."""
    if remaining <= 0:
        days = -math.ceil(abs(remaining) / pace_per_day) if pace_per_day > 0 else 0
        return today + timedelta(days=max(days, -MAX_PLANNING_DAYS))
    if pace_per_day <= 0:
        return None
    days = math.ceil(remaining / pace_per_day)
    return today + timedelta(days=min(days, MAX_PLANNING_DAYS))


def compute_markers(
    today: date,
    meters: Sequence[MeterInput],
    calendar: CalendarInput | None,
    *,
    tolerance_pct: Decimal,
    lead_days: int,
) -> Markers:
    """The three dates (cautious, typical, slow) of the meter that runs out first, plus the window."""
    candidates: list[tuple[date | None, Markers]] = []

    for meter in meters:
        used = meter.current - meter.baseline
        remaining = meter.limit - used
        p75 = project_date(today, remaining, meter.pace.p75)
        p50 = project_date(today, remaining, meter.pace.p50)
        p25 = project_date(today, remaining, meter.pace.p25)
        tolerance = meter.limit * tolerance_pct / HUNDRED
        candidates.append((p75, _markers(today, meter.name, used, meter.limit, remaining, tolerance, meter.pace.p50, p75, p50, p25, lead_days)))

    if calendar is not None:
        used_days = Decimal((today - calendar.baseline_date).days)
        limit_days = Decimal(calendar.limit_days)
        remaining_days = limit_days - used_days
        due = calendar.baseline_date + timedelta(days=calendar.limit_days)
        tolerance = limit_days * tolerance_pct / HUNDRED
        candidates.append((due, _markers(today, "days", used_days, limit_days, remaining_days, tolerance, Decimal(1), due, due, due, lead_days)))

    if not candidates:
        return _markers(today, None, ZERO, ZERO, ZERO, ZERO, ZERO, None, None, None, lead_days)

    def sort_key(entry: tuple[date | None, Markers]) -> tuple[int, date]:
        when, _markers_obj = entry
        return (1, date.max) if when is None else (0, when)

    return min(candidates, key=sort_key)[1]


def _markers(
    today: date,
    limiting: str | None,
    used: Decimal,
    limit: Decimal,
    remaining: Decimal,
    tolerance: Decimal,
    pace_p50: Decimal,
    p75: date | None,
    p50: date | None,
    p25: date | None,
    lead_days: int,
) -> Markers:
    window_open = p75 - timedelta(days=lead_days) if p75 is not None else None
    if limiting is None:
        state = "forecast"
    elif used > limit + tolerance:
        state = "over_tolerance"
    elif used >= limit:
        state = "over_limit"
    elif window_open is not None and today >= window_open:
        state = "due_soon"
    else:
        state = "forecast"
    return Markers(
        as_of=today, limiting=limiting, used=used, limit=limit, remaining=remaining, tolerance=tolerance,
        pace_p50=pace_p50, date_p75=p75, date_p50=p50, date_p25=p25, window_open=window_open, state=state,
    )


def confidence(*, baseline_source: str, pace: Pace, stale: bool) -> str:
    """'stale' beats everything (the data may be wrong); 'low' = guessed baseline or thin pace data."""
    if stale:
        return "stale"
    if baseline_source == "provisional" or not pace.reliable:
        return "low"
    return "high"


# ── Rank cascade and visits ──────────────────────────────────────────────────

def covered_interval_ids(ranks: dict[object, int | None], completed: object) -> list[object]:
    """Intervals reset by completing `completed`: itself and every interval of a lower rank.

    An interval without a rank (None) is independent: it neither covers nor is covered.
    """
    rank = ranks.get(completed)
    if rank is None:
        return [completed]
    return [key for key, other in ranks.items() if other is not None and other <= rank or key == completed]


@dataclass
class ObligationDraft:
    """What the engine knows about one obligation while visits are being formed."""

    key: object  # interval id
    rank: int | None
    limit_km: Decimal | None
    markers: Markers
    planned_date: date | None = None
    merged_into: object | None = None


def merge_visits(drafts: list[ObligationDraft], *, merge_pct: Decimal) -> None:
    """One visit per stay: a lower rank whose cautious date falls shortly before a higher rank's
    is done together with it; the visit takes the earlier date (higher ranks are never done late).

    "Shortly" = merge_pct % of the lower interval at the typical pace. Mutates the drafts.
    """
    for draft in drafts:
        draft.planned_date = draft.markers.date_p75
        draft.merged_into = None
    ranked = sorted((d for d in drafts if d.rank is not None and d.markers.date_p75 is not None), key=lambda d: d.rank, reverse=True)
    for higher_index, higher in enumerate(ranked):
        for lower in ranked[higher_index + 1:]:
            if lower.merged_into is not None or higher.rank == lower.rank:
                continue
            pace = lower.markers.pace_p50
            if pace <= 0 or lower.limit_km is None or lower.markers.limiting != "km":
                continue
            horizon = math.ceil((lower.limit_km * merge_pct / HUNDRED) / pace)
            gap = (higher.markers.date_p75 - lower.markers.date_p75).days
            if 0 <= gap <= horizon:
                lower.merged_into = higher.key
                earliest = min(lower.markers.date_p75, higher.planned_date or higher.markers.date_p75)
                higher.planned_date = earliest
                lower.planned_date = earliest


# ── Priority ────────────────────────────────────────────────────────────────

OVER_LIMIT_FLOOR = 80
WEIGHTS = {"time": 40, "consequence": 20, "health": 15, "deferrals": 10, "readiness": 10, "calendar": 5}


@dataclass(frozen=True)
class Priority:
    score: int  # 0..100
    why: list[str] = field(default_factory=list)


def priority_score(
    *,
    days_to_limit: int | None,
    pace_p75: Decimal | None,
    health: float | None,
    deferrals: int,
    ready: bool | None,
    consequence: float = 0.5,
    baseline_provisional: bool = False,
) -> Priority:
    """0..100 and the reasons in plain words. Weights are the proposal's defaults (WEIGHTS)."""
    if days_to_limit is None:
        f_time = 0.0
    else:
        f_time = min(1.0, max(0.0, 1.0 - days_to_limit / 60.0))
    f_health = 0.5 if health is None else min(1.0, max(0.0, health))
    f_deferrals = min(1.0, deferrals / 3.0)
    f_ready = 0.5 if ready is None else (1.0 if ready else 0.0)
    total = (
        WEIGHTS["time"] * f_time
        + WEIGHTS["consequence"] * consequence
        + WEIGHTS["health"] * f_health
        + WEIGHTS["deferrals"] * f_deferrals
        + WEIGHTS["readiness"] * f_ready
        + WEIGHTS["calendar"] * 0.0
    )
    # A limit that is already reached outranks anything that is merely approaching, whatever else is missing.
    if days_to_limit is not None and days_to_limit <= 0:
        total = max(total, OVER_LIMIT_FLOOR)
    why: list[str] = []
    if days_to_limit is not None:
        if days_to_limit <= 0:
            why.append("лимит уже достигнут")
        else:
            why.append(f"до лимита ~{days_to_limit} дн.")
    if pace_p75 is not None and pace_p75 > 0:
        why.append(f"темп {pace_p75:.0f} ед./сут (p75)")
    if baseline_provisional:
        why.append("точка отсчёта предположительная")
    if deferrals:
        why.append(f"переносов: {deferrals}")
    if health is not None and health >= 0.6:
        why.append("высокий риск отказа")
    if ready is True:
        why.append("запчасти и место готовы")
    elif ready is False:
        why.append("запчасти или место не готовы")
    return Priority(score=int(round(min(100.0, total))), why=why)
