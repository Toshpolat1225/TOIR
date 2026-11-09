"""Deterministic wagon mileage allocation primitives.

The engine deliberately separates physical distance selection from wagon allocation:
multiple locomotive odometers are never summed or averaged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable
from uuid import UUID

ZERO = Decimal("0")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class OdometerInterval:
    locomotive_asset_id: UUID
    start_km: Decimal
    end_km: Decimal
    start_at: datetime
    end_at: datetime
    received_at: datetime
    source_id: str


@dataclass(frozen=True)
class WagonMembershipInterval:
    wagon_asset_id: UUID
    train_gtk_id: int
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class MainLocomotiveDecision:
    selected: OdometerInterval | None
    reason: str
    candidates: int
    confidence: str


@dataclass(frozen=True)
class WagonMileageAllocation:
    wagon_asset_id: UUID
    locomotive_asset_id: UUID
    train_gtk_id: int
    period_from: datetime
    period_to: datetime
    km: Decimal
    estimated: bool
    source_id: str


def _hours(start: datetime, end: datetime) -> Decimal:
    return Decimal(str((end - start).total_seconds())) / Decimal("3600")


def _round_km(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _valid_interval(row: OdometerInterval, *, max_speed_kmh: Decimal) -> bool:
    if row.end_at <= row.start_at or row.end_km < row.start_km:
        return False
    elapsed = _hours(row.start_at, row.end_at)
    if elapsed <= ZERO:
        return False
    # A small tolerance accommodates integer-km Wialon rounding.
    return row.end_km - row.start_km <= max_speed_kmh * elapsed + Decimal("10")


def select_main_locomotive(
    candidates: Iterable[OdometerInterval],
    *,
    max_speed_kmh: Decimal = Decimal("150"),
    agreement_tolerance_km: Decimal = Decimal("3"),
    max_received_lag_seconds: int = 900,
) -> MainLocomotiveDecision:
    """Select one trusted physical odometer source, without sum/average.

    If several valid locomotive odometers describe the same interval, they must
    agree within tolerance. The freshest received reading wins; ties are stable
    by source_id. A disagreement is held for review rather than guessed.
    """
    rows = [
        row for row in candidates
        if _valid_interval(row, max_speed_kmh=max_speed_kmh)
        and row.end_at <= row.received_at
        and (row.received_at - row.end_at).total_seconds() <= max_received_lag_seconds
    ]
    if not rows:
        return MainLocomotiveDecision(None, "no_valid_fresh_odometer_interval", 0, "none")

    reference = rows[0].end_km - rows[0].start_km
    reference_start = rows[0].start_at
    reference_end = rows[0].end_at
    for row in rows[1:]:
        distance = row.end_km - row.start_km
        if row.start_at != reference_start or row.end_at != reference_end:
            return MainLocomotiveDecision(
                None, "locomotive_odometer_time_boundaries_disagree", len(rows), "conflict"
            )
        if abs(distance - reference) > agreement_tolerance_km:
            return MainLocomotiveDecision(
                None, "locomotive_odometer_disagreement", len(rows), "conflict"
            )

    # Pick one physical odometer source; never combine candidate distances.
    rows.sort(key=lambda row: (row.received_at, row.end_at, row.source_id), reverse=True)
    confidence = "high" if len(rows) == 1 else "corroborated"
    return MainLocomotiveDecision(rows[0], "selected_freshest_consistent_source", len(rows), confidence)


def allocate_distance_to_wagons(
    odometer: OdometerInterval,
    memberships: Iterable[WagonMembershipInterval],
) -> tuple[WagonMileageAllocation, ...]:
    """Allocate selected physical distance over each wagon's membership overlap.

    Partial-interval allocations use elapsed-time interpolation and are marked
    estimated. Full-interval membership is not estimated. Non-overlapping or
    invalid intervals produce no mileage.
    """
    total_km = odometer.end_km - odometer.start_km
    total_seconds = Decimal(str((odometer.end_at - odometer.start_at).total_seconds()))
    if total_km <= ZERO or total_seconds <= ZERO:
        return ()

    allocations: list[WagonMileageAllocation] = []
    seen: set[tuple[UUID, int, datetime, datetime]] = set()
    for membership in memberships:
        start = max(odometer.start_at, membership.start_at)
        end = min(odometer.end_at, membership.end_at)
        if end <= start:
            continue
        key = (membership.wagon_asset_id, membership.train_gtk_id, start, end)
        if key in seen:
            continue
        seen.add(key)
        overlap_seconds = Decimal(str((end - start).total_seconds()))
        km = _round_km(total_km * overlap_seconds / total_seconds)
        if km <= ZERO:
            continue
        full_interval = start == odometer.start_at and end == odometer.end_at
        allocations.append(
            WagonMileageAllocation(
                wagon_asset_id=membership.wagon_asset_id,
                locomotive_asset_id=odometer.locomotive_asset_id,
                train_gtk_id=membership.train_gtk_id,
                period_from=start,
                period_to=end,
                km=km,
                estimated=not full_interval,
                source_id=odometer.source_id,
            )
        )
    return tuple(allocations)
