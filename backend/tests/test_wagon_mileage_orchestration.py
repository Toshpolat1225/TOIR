from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.services.wagon_mileage import (
    MAX_WIALON_SAMPLE_GAP,
    OdometerPoint,
    decide_membership_mileage,
    decide_wagon_idle,
    decide_wialon_segment,
    sum_wialon_sample_deltas,
)
from app.services.wagon_mileage_engine import WagonMembershipInterval


def _point(reading_id, locomotive_id, km, at, *, eligible=True):
    return OdometerPoint(
        reading_id=reading_id,
        locomotive_asset_id=locomotive_id,
        odometer_km=Decimal(km),
        reading_at=at,
        accepted=True,
        calculation_eligible=eligible,
    )


def test_wialon_maximum_bracket_gap_defaults_to_thirty_minutes():
    assert MAX_WIALON_SAMPLE_GAP == timedelta(minutes=30)


def test_exact_same_locomotive_bracket_is_confirmed_and_half_open():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=2)
    locomotive = uuid4()

    decision = decide_wialon_segment(
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "150", end),
        period_from=start,
        period_to=end,
    )

    assert decision.classification == "CONFIRMED"
    assert decision.calculation_eligible is True
    assert decision.km == Decimal("50")
    assert decision.source_reading_ids == (1, 2)


def test_partial_two_minute_sample_is_estimated_by_time():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=2)
    middle = start + timedelta(minutes=1)
    locomotive = uuid4()

    decision = decide_wialon_segment(
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "140", end),
        period_from=middle,
        period_to=end,
    )

    assert decision.classification == "ESTIMATED"
    assert decision.calculation_eligible is True
    assert decision.km == Decimal("20")
    assert decision.reason == "sample_interval_proportional_estimate"


def test_zero_delta_bracket_is_confirmed_zero_km():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=4)
    locomotive = uuid4()

    decision = decide_wialon_segment(
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "100", end),
        period_from=start,
        period_to=end,
    )

    assert decision.classification == "CONFIRMED"
    assert decision.calculation_eligible is True
    assert decision.km == Decimal("0")
    assert decision.reason == "same_locomotive_zero_delta"


def test_four_minute_moving_bracket_is_estimated():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=4)
    locomotive = uuid4()

    decision = decide_wialon_segment(
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "104", end),
        period_from=start,
        period_to=end,
    )

    assert decision.classification == "ESTIMATED"
    assert decision.calculation_eligible is True
    assert decision.km == Decimal("4.00")
    assert decision.reason == "sample_interval_proportional_estimate"


def test_45_minute_movement_gap_is_held():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=45)
    locomotive = uuid4()

    decision = decide_wialon_segment(
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "140", end),
        period_from=start,
        period_to=end,
    )

    assert decision.classification == "HELD"
    assert decision.calculation_eligible is False
    assert decision.km is None
    assert decision.reason == "odometer_sample_gap_exceeded"


def test_held_if_wagon_segment_falls_inside_long_gap_even_when_ends_are_close():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    locomotive = uuid4()
    decision = decide_wialon_segment(
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "140", start + timedelta(minutes=45)),
        period_from=start + timedelta(minutes=10),
        period_to=start + timedelta(minutes=11),
    )

    assert decision.classification == "HELD"
    assert decision.km is None
    assert decision.reason == "odometer_sample_gap_exceeded"


def test_sample_delta_sum_returns_twenty_km_for_half_hour_of_forty_km_hour():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    locomotive = uuid4()
    increments = (
        [Decimal("1.33")] * 14
        + [Decimal("1.38")]
        + [Decimal("1.33")] * 14
        + [Decimal("1.38")]
    )
    points = [_point(0, locomotive, "0", start)]
    odometer = Decimal("0")
    for index, increment in enumerate(increments, start=1):
        odometer += increment
        points.append(
            _point(
                index,
                locomotive,
                str(odometer),
                start + timedelta(minutes=2 * index),
            )
        )

    decision = sum_wialon_sample_deltas(
        points,
        period_from=start,
        period_to=start + timedelta(minutes=30),
    )

    assert decision.classification == "CONFIRMED"
    assert decision.calculation_eligible is True
    assert decision.km == Decimal("20.00")
    assert decision.source_reading_ids == tuple(range(16))


def test_sample_delta_sum_holds_if_any_required_reading_is_ineligible():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    locomotive = uuid4()
    points = [
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "102", start + timedelta(minutes=2), eligible=False),
        _point(3, locomotive, "104", start + timedelta(minutes=4)),
    ]

    decision = sum_wialon_sample_deltas(
        points,
        period_from=start,
        period_to=start + timedelta(minutes=4),
    )

    assert decision.classification == "HELD"
    assert decision.calculation_eligible is False
    assert decision.reason == "reading_not_calculation_eligible"


def test_sample_delta_sum_holds_after_gap_without_zero_filling():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    locomotive = uuid4()
    points = [
        _point(1, locomotive, "100", start + timedelta(minutes=1)),
        _point(2, locomotive, "110", start + timedelta(minutes=3)),
    ]

    decision = sum_wialon_sample_deltas(
        points,
        period_from=start,
        period_to=start + timedelta(minutes=4),
    )

    assert decision.classification == "HELD"
    assert decision.reason == "missing_odometer_sample_bracket"


def test_membership_overlap_between_trains_holds_both_wagon_segments():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    locomotive = uuid4()
    wagon = uuid4()
    points = [
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "102", start + timedelta(minutes=2)),
        _point(3, locomotive, "104", start + timedelta(minutes=4)),
        _point(4, locomotive, "106", start + timedelta(minutes=6)),
    ]

    decisions = decide_membership_mileage(
        points,
        [
            WagonMembershipInterval(
                wagon, 10, start, start + timedelta(minutes=4)
            ),
            WagonMembershipInterval(
                wagon,
                11,
                start + timedelta(minutes=3),
                start + timedelta(minutes=6),
            ),
        ],
    )

    assert len(decisions) == 2
    assert all(row.decision.classification == "HELD" for row in decisions)
    assert all(row.decision.reason == "wagon_membership_overlap" for row in decisions)


def test_membership_windows_are_half_open_and_adjacent_windows_count_separately():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    locomotive = uuid4()
    wagon = uuid4()
    points = [
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "102", start + timedelta(minutes=2)),
        _point(3, locomotive, "104", start + timedelta(minutes=4)),
    ]

    decisions = decide_membership_mileage(
        points,
        [
            WagonMembershipInterval(
                wagon, 10, start, start + timedelta(minutes=2)
            ),
            WagonMembershipInterval(
                wagon,
                11,
                start + timedelta(minutes=2),
                start + timedelta(minutes=4),
            ),
        ],
    )

    assert len(decisions) == 2
    assert [row.decision.km for row in decisions] == [
        Decimal("2.00"),
        Decimal("2.00"),
    ]
    assert all(row.decision.classification == "CONFIRMED" for row in decisions)


def test_membership_boundary_inside_sample_is_estimated():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    locomotive = uuid4()
    wagon = uuid4()
    points = [
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "102", start + timedelta(minutes=2)),
        _point(3, locomotive, "104", start + timedelta(minutes=4)),
    ]

    decision = decide_membership_mileage(
        points,
        [
            WagonMembershipInterval(
                wagon,
                10,
                start + timedelta(minutes=1),
                start + timedelta(minutes=3),
            )
        ],
    )[0].decision

    assert decision.classification == "ESTIMATED"
    assert decision.calculation_eligible is True
    assert decision.km == Decimal("2.00")
    assert decision.reason == "two_minute_sample_delta_sum_estimated"


def test_interpolation_never_brackets_across_locomotives():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    decision = decide_wialon_segment(
        _point(1, uuid4(), "100", start),
        _point(2, uuid4(), "150", end),
        period_from=start,
        period_to=end,
    )

    assert decision.classification == "HELD"
    assert decision.reason == "locomotive_bracket_mismatch"
    assert decision.km is None


def test_locomotive_stop_alone_does_not_confirm_wagon_idle():
    status, reason = decide_wagon_idle(
        gtk_wagon_stationary=None,
        wialon_locomotive_stopped=True,
    )

    assert status == "HELD"
    assert reason == "insufficient_gtk_and_wialon_evidence"


def test_even_agreeing_idle_signals_wait_for_duration_policy():
    status, reason = decide_wagon_idle(
        gtk_wagon_stationary=True,
        wialon_locomotive_stopped=True,
    )

    assert status == "HELD"
    assert reason == "idle_evidence_incomplete"


def test_idle_is_confirmed_only_with_zero_delta_and_matching_gtk_duration():
    status, reason = decide_wagon_idle(
        gtk_wagon_stationary=True,
        wialon_locomotive_stopped=True,
        odometer_delta_km=Decimal("0"),
        gtk_stationary_duration_s=1800,
        duration_seconds=1800,
        minimum_minutes=30,
    )

    assert status == "CONFIRMED"
    assert reason == "zero_odometer_and_gtk_stationary"


def test_idle_requires_the_approved_minimum_and_matching_duration():
    status, reason = decide_wagon_idle(
        gtk_wagon_stationary=True,
        wialon_locomotive_stopped=True,
        odometer_delta_km=Decimal("0"),
        gtk_stationary_duration_s=1200,
        duration_seconds=1200,
        minimum_minutes=30,
    )

    assert status == "HELD"
    assert reason == "idle_duration_below_pending_threshold"
