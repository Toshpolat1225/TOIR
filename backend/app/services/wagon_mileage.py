from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Literal
from uuid import UUID

from app.core.config import settings
from app.services.wagon_mileage_engine import WagonMembershipInterval

MileageClass = Literal["CONFIRMED", "ESTIMATED", "HELD"]
MAX_WIALON_SAMPLE_GAP = timedelta(
    minutes=settings.wagon_mileage_max_bracket_gap_min
)
NOMINAL_WIALON_SAMPLE_GAP = timedelta(minutes=2)
CENT = Decimal("0.01")


@dataclass(frozen=True)
class OdometerPoint:
    reading_id: int
    locomotive_asset_id: UUID
    odometer_km: Decimal
    reading_at: datetime
    accepted: bool
    calculation_eligible: bool
    received_at: datetime | None = None


@dataclass(frozen=True)
class SegmentDecision:
    classification: MileageClass
    calculation_eligible: bool
    km: Decimal | None
    locomotive_asset_id: UUID | None
    source_reading_ids: tuple[int, ...]
    reason: str


@dataclass(frozen=True)
class MembershipMileageDecision:
    wagon_asset_id: UUID
    train_gtk_id: int
    period_from: datetime
    period_to: datetime
    decision: SegmentDecision


def decide_wialon_segment(
    start: OdometerPoint | None,
    end: OdometerPoint | None,
    *,
    period_from: datetime,
    period_to: datetime,
) -> SegmentDecision:
    if period_to <= period_from:
        return SegmentDecision(
            "HELD", False, None, None, (), "invalid_half_open_period"
        )
    if start is None or end is None:
        return SegmentDecision("HELD", False, None, None, (), "missing_odometer_bracket")
    if (
        not start.accepted
        or not end.accepted
        or not start.calculation_eligible
        or not end.calculation_eligible
    ):
        return SegmentDecision(
            "HELD",
            False,
            None,
            start.locomotive_asset_id,
            (start.reading_id, end.reading_id),
            "reading_not_calculation_eligible",
        )
    if start.locomotive_asset_id != end.locomotive_asset_id:
        return SegmentDecision(
            "HELD",
            False,
            None,
            None,
            (start.reading_id, end.reading_id),
            "locomotive_bracket_mismatch",
        )
    if (
        start.reading_at >= end.reading_at
        or end.odometer_km < start.odometer_km
        or period_from < start.reading_at
        or period_to > end.reading_at
    ):
        return SegmentDecision(
            "HELD",
            False,
            None,
            start.locomotive_asset_id,
            (start.reading_id, end.reading_id),
            "invalid_or_unbracketed_odometer_interval",
        )
    bracket = end.reading_at - start.reading_at
    distance = end.odometer_km - start.odometer_km
    exact_interval = period_from == start.reading_at and period_to == end.reading_at
    if distance == 0 and exact_interval:
        return SegmentDecision(
            "CONFIRMED",
            True,
            Decimal("0"),
            start.locomotive_asset_id,
            (start.reading_id, end.reading_id),
            "same_locomotive_zero_delta",
        )
    if bracket > MAX_WIALON_SAMPLE_GAP and distance > 0:
        return SegmentDecision(
            "HELD",
            False,
            None,
            start.locomotive_asset_id,
            (start.reading_id, end.reading_id),
            "odometer_sample_gap_exceeded",
        )
    overlap = period_to - period_from
    km = (
        distance
        * Decimal(str(overlap.total_seconds()))
        / Decimal(str(bracket.total_seconds()))
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    if exact_interval and bracket <= NOMINAL_WIALON_SAMPLE_GAP:
        return SegmentDecision(
            "CONFIRMED",
            True,
            km,
            start.locomotive_asset_id,
            (start.reading_id, end.reading_id),
            "same_locomotive_exact_reading_bracket",
        )
    return SegmentDecision(
        "ESTIMATED",
        True,
        km,
        start.locomotive_asset_id,
        (start.reading_id, end.reading_id),
        "sample_interval_proportional_estimate",
    )


def sum_wialon_sample_deltas(
    points: Iterable[OdometerPoint],
    *,
    period_from: datetime,
    period_to: datetime,
) -> SegmentDecision:
    if period_to <= period_from:
        return SegmentDecision("HELD", False, None, None, (), "invalid_half_open_period")

    ordered = sorted(points, key=lambda point: point.reading_at)
    cursor = period_from
    total_km = Decimal("0")
    estimated = False
    locomotive_id: UUID | None = None
    source_ids: list[int] = []
    coverage_started = False

    for start, end in zip(ordered, ordered[1:]):
        if end.reading_at <= period_from or start.reading_at >= period_to:
            continue
        if not coverage_started:
            if start.reading_at > period_from:
                return SegmentDecision(
                    "HELD",
                    False,
                    None,
                    start.locomotive_asset_id,
                    (start.reading_id, end.reading_id),
                    "missing_odometer_sample_bracket",
                )
            coverage_started = True
        if (
            not start.accepted
            or not end.accepted
            or not start.calculation_eligible
            or not end.calculation_eligible
        ):
            return SegmentDecision(
                "HELD",
                False,
                None,
                start.locomotive_asset_id,
                (start.reading_id, end.reading_id),
                "reading_not_calculation_eligible",
            )
        if start.locomotive_asset_id != end.locomotive_asset_id:
            return SegmentDecision(
                "HELD",
                False,
                None,
                None,
                (start.reading_id, end.reading_id),
                "locomotive_bracket_mismatch",
            )
        bracket = end.reading_at - start.reading_at
        if (
            bracket <= timedelta(0)
            or end.odometer_km < start.odometer_km
        ):
            return SegmentDecision(
                "HELD",
                False,
                None,
                start.locomotive_asset_id,
                (start.reading_id, end.reading_id),
                "invalid_or_decreasing_odometer_sample",
            )

        overlap_from = max(start.reading_at, period_from)
        overlap_to = min(end.reading_at, period_to)
        if overlap_from > cursor:
            return SegmentDecision(
                "HELD",
                False,
                None,
                start.locomotive_asset_id,
                tuple(source_ids + [start.reading_id, end.reading_id]),
                "missing_odometer_sample_bracket",
            )
        sample_km = end.odometer_km - start.odometer_km
        if (
            bracket > MAX_WIALON_SAMPLE_GAP
            and overlap_to > overlap_from
            and sample_km > 0
        ):
            return SegmentDecision(
                "HELD",
                False,
                None,
                start.locomotive_asset_id,
                tuple(dict.fromkeys(source_ids + [start.reading_id, end.reading_id])),
                "odometer_sample_gap_exceeded",
            )
        overlap_seconds = Decimal(str((overlap_to - overlap_from).total_seconds()))
        bracket_seconds = Decimal(str(bracket.total_seconds()))
        total_km += sample_km * overlap_seconds / bracket_seconds
        if (
            overlap_from != start.reading_at
            or overlap_to != end.reading_at
            or (
                bracket > NOMINAL_WIALON_SAMPLE_GAP
                and sample_km > 0
            )
        ):
            estimated = True
        locomotive_id = start.locomotive_asset_id
        source_ids.extend((start.reading_id, end.reading_id))
        cursor = max(cursor, overlap_to)
        if cursor >= period_to:
            break
    if cursor < period_to and ordered:
        final_point = ordered[-1]
        if cursor < final_point.reading_at:
            return SegmentDecision(
                "HELD",
                False,
                None,
                final_point.locomotive_asset_id,
                tuple(dict.fromkeys(source_ids + [final_point.reading_id])),
                "missing_odometer_sample_bracket",
            )

    if cursor < period_to or locomotive_id is None:
        return SegmentDecision(
            "HELD",
            False,
            None,
            locomotive_id,
            tuple(dict.fromkeys(source_ids)),
            "missing_odometer_sample_bracket",
        )

    classification: MileageClass = "ESTIMATED" if estimated else "CONFIRMED"
    return SegmentDecision(
        classification,
        True,
        total_km.quantize(CENT, rounding=ROUND_HALF_UP),
        locomotive_id,
        tuple(dict.fromkeys(source_ids)),
        "two_minute_sample_delta_sum_estimated"
        if estimated
        else "two_minute_sample_delta_sum",
    )


def decide_membership_mileage(
    points: Iterable[OdometerPoint],
    memberships: Iterable[WagonMembershipInterval],
) -> tuple[MembershipMileageDecision, ...]:
    membership_rows = sorted(
        set(memberships),
        key=lambda row: (
            row.wagon_asset_id,
            row.start_at,
            row.end_at,
            row.train_gtk_id,
        ),
    )
    conflicts: set[UUID] = set()
    by_wagon: dict[UUID, list[WagonMembershipInterval]] = {}
    for membership in membership_rows:
        by_wagon.setdefault(membership.wagon_asset_id, []).append(membership)

    for wagon_id, rows in by_wagon.items():
        for index, current in enumerate(rows):
            if current.end_at <= current.start_at:
                conflicts.add(wagon_id)
                continue
            for other in rows[index + 1 :]:
                if other.start_at >= current.end_at:
                    break
                if other.end_at > current.start_at:
                    conflicts.add(wagon_id)
                    break

    point_rows = tuple(points)
    decisions: list[MembershipMileageDecision] = []
    for membership in membership_rows:
        if membership.wagon_asset_id in conflicts:
            decision = SegmentDecision(
                "HELD",
                False,
                None,
                None,
                (),
                "wagon_membership_overlap",
            )
        else:
            decision = sum_wialon_sample_deltas(
                point_rows,
                period_from=membership.start_at,
                period_to=membership.end_at,
            )
        decisions.append(
            MembershipMileageDecision(
                wagon_asset_id=membership.wagon_asset_id,
                train_gtk_id=membership.train_gtk_id,
                period_from=membership.start_at,
                period_to=membership.end_at,
                decision=decision,
            )
        )
    return tuple(decisions)


def decide_wagon_idle(
    *,
    gtk_wagon_stationary: bool | None,
    wialon_locomotive_stopped: bool | None,
    odometer_delta_km: Decimal | None = None,
    gtk_stationary_duration_s: int | None = None,
    duration_seconds: int | None = None,
    minimum_minutes: int | None = None,
) -> tuple[str, str]:
    if gtk_wagon_stationary is None or wialon_locomotive_stopped is None:
        return "HELD", "insufficient_gtk_and_wialon_evidence"
    if not gtk_wagon_stationary or not wialon_locomotive_stopped:
        return "HELD", "gtk_and_wialon_activity_conflict_or_active"
    if (
        odometer_delta_km is None
        or gtk_stationary_duration_s is None
        or duration_seconds is None
    ):
        return "HELD", "idle_evidence_incomplete"
    if odometer_delta_km != 0:
        return "HELD", "odometer_delta_conflicts_with_idle"
    minimum_seconds = (
        minimum_minutes or settings.wagon_mileage_idle_min_minutes
    ) * 60
    if duration_seconds < minimum_seconds:
        return "HELD", "idle_duration_below_pending_threshold"
    if gtk_stationary_duration_s < duration_seconds:
        return "HELD", "gtk_stationary_duration_mismatch"
    return "CONFIRMED", "zero_odometer_and_gtk_stationary"
