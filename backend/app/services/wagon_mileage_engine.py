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
    is_main: bool = False
    calculation_eligible: bool = True


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
    km: Decimal | None
    estimated: bool
    source_id: str


def _hours(start: datetime, end: datetime) -> Decimal:
    return Decimal(str((end - start).total_seconds())) / Decimal("3600")


def _round_km(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _valid_interval(row: OdometerInterval) -> bool:
    if row.end_at <= row.start_at or row.end_km < row.start_km:
        return False
    elapsed = _hours(row.start_at, row.end_at)
    if elapsed <= ZERO:
        return False
    return row.end_at <= row.received_at


def select_main_locomotive(
    candidates: Iterable[OdometerInterval],
) -> MainLocomotiveDecision:
    """Select one trusted physical odometer source, without sum/average.

    A choice between different locomotives needs an approved policy. This
    primitive therefore holds multi-locomotive candidates instead of applying
    an unapproved tolerance, freshness window, or priority.
    """
    rows = [
        row
        for row in candidates
        if row.calculation_eligible and _valid_interval(row)
    ]
    if not rows:
        return MainLocomotiveDecision(None, "no_valid_odometer_interval", 0, "none")
    reference = rows[0]
    if any(
        row.start_at != reference.start_at
        or row.end_at != reference.end_at
        for row in rows[1:]
    ):
        return MainLocomotiveDecision(
            None, "candidate_periods_disagree", len(rows), "conflict"
        )
    if len({row.locomotive_asset_id for row in rows}) == 1:
        if any(
            row.start_km != reference.start_km or row.end_km != reference.end_km
            for row in rows[1:]
        ):
            return MainLocomotiveDecision(
                None, "same_locomotive_readings_disagree", len(rows), "conflict"
            )
        rows.sort(key=lambda row: row.source_id)
        return MainLocomotiveDecision(
            rows[0], "single_locomotive_source", len(rows), "high"
        )

    distances = [row.end_km - row.start_km for row in rows]
    largest_distance = max(distances)
    tolerance = max(Decimal("2"), largest_distance * Decimal("0.05"))
    if max(distances) - min(distances) > tolerance:
        return MainLocomotiveDecision(
            None, "locomotive_distance_conflict", len(rows), "conflict"
        )

    main_rows = [row for row in rows if row.is_main]
    if len(main_rows) == 1:
        selected = main_rows[0]
        reason = "gtk_main_locomotive_selected"
    else:
        rows.sort(key=lambda row: (-row.received_at.timestamp(), row.source_id))
        selected = rows[0]
        reason = (
            "locomotive_distances_within_tolerance"
            if len(rows) > 1
            else "single_locomotive_source"
        )
    return MainLocomotiveDecision(selected, reason, len(rows), "high")


def allocate_distance_to_wagons(
    odometer: OdometerInterval,
    memberships: Iterable[WagonMembershipInterval],
) -> tuple[WagonMileageAllocation, ...]:
    """Allocate only exact membership intervals over the odometer interval.

    Partial intervals are retained as estimated evidence with no invented
    distance. The interval boundaries are half-open: [start, end).
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
        full_interval = start == odometer.start_at and end == odometer.end_at
        km = _round_km(total_km) if full_interval else None
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
