from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

MileageClass = Literal["CONFIRMED", "ESTIMATED", "HELD"]


@dataclass(frozen=True)
class OdometerPoint:
    reading_id: int
    locomotive_asset_id: UUID
    odometer_km: Decimal
    reading_at: datetime
    accepted: bool
    calculation_eligible: bool


@dataclass(frozen=True)
class SegmentDecision:
    classification: MileageClass
    calculation_eligible: bool
    km: Decimal | None
    locomotive_asset_id: UUID | None
    source_reading_ids: tuple[int, ...]
    reason: str


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
    if period_from == start.reading_at and period_to == end.reading_at:
        return SegmentDecision(
            "CONFIRMED",
            True,
            end.odometer_km - start.odometer_km,
            start.locomotive_asset_id,
            (start.reading_id, end.reading_id),
            "same_locomotive_exact_reading_bracket",
        )
    return SegmentDecision(
        "ESTIMATED",
        False,
        None,
        start.locomotive_asset_id,
        (start.reading_id, end.reading_id),
        "interpolation_formula_policy_pending",
    )


def decide_wagon_idle(
    *,
    gtk_wagon_stationary: bool | None,
    wialon_locomotive_stopped: bool | None,
) -> tuple[str, str]:
    if gtk_wagon_stationary is None or wialon_locomotive_stopped is None:
        return "HELD", "insufficient_gtk_and_wialon_evidence"
    if not gtk_wagon_stationary or not wialon_locomotive_stopped:
        return "HELD", "gtk_and_wialon_activity_conflict_or_active"
    return "HELD", "idle_duration_policy_pending"
