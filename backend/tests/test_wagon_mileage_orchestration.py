from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.services.wagon_mileage import (
    OdometerPoint,
    decide_wagon_idle,
    decide_wialon_segment,
)


def _point(reading_id, locomotive_id, km, at, *, eligible=True):
    return OdometerPoint(
        reading_id=reading_id,
        locomotive_asset_id=locomotive_id,
        odometer_km=Decimal(km),
        reading_at=at,
        accepted=True,
        calculation_eligible=eligible,
    )


def test_exact_same_locomotive_bracket_is_confirmed_and_half_open():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
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


def test_wialon_interpolation_is_estimated_but_has_no_unapproved_formula():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    middle = start + timedelta(hours=1)
    locomotive = uuid4()

    decision = decide_wialon_segment(
        _point(1, locomotive, "100", start),
        _point(2, locomotive, "140", end),
        period_from=middle,
        period_to=end,
    )

    assert decision.classification == "ESTIMATED"
    assert decision.calculation_eligible is False
    assert decision.km is None
    assert decision.reason == "interpolation_formula_policy_pending"


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
    assert reason == "idle_duration_policy_pending"
