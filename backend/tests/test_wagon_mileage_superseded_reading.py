"""A benign same-message-time reading must not hold a whole wagon membership window."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.wagon_mileage import OdometerPoint, sum_wialon_sample_deltas
from app.services.wagon_mileage_run import is_superseded_same_time_reading
from app.services.wialon_quality import COUNTER_ADVANCED_REASON

START = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _row(eligible, reason=None):
    return SimpleNamespace(calculation_eligible=eligible, rejection_reason=reason)


def test_only_ineligible_counter_advance_rows_are_dropped():
    assert is_superseded_same_time_reading(_row(False, COUNTER_ADVANCED_REASON))
    assert not is_superseded_same_time_reading(_row(True, None))
    # a real rejection (jump / same-time conflict) still has to hold the window
    assert not is_superseded_same_time_reading(_row(False, "same_time_different_odometer"))
    assert not is_superseded_same_time_reading(_row(False, "cnm sakradi: +198.00 km, ruxsat 25.0 km"))
    # an eligible row is never dropped, whatever its reason text says
    assert not is_superseded_same_time_reading(_row(True, COUNTER_ADVANCED_REASON))


def _point(index, km, minutes, eligible=True):
    return OdometerPoint(
        reading_id=index,
        locomotive_asset_id=LOCO,
        odometer_km=Decimal(km),
        reading_at=START + timedelta(minutes=minutes),
        accepted=True,
        calculation_eligible=eligible,
    )


LOCO = uuid4()


def test_ineligible_point_inside_window_holds_it_but_dropping_it_keeps_the_km():
    period = dict(period_from=START, period_to=START + timedelta(minutes=6))
    superseded = _point(3, "103", 4, eligible=False)
    base = [_point(1, "100", 0), _point(2, "102", 2), _point(4, "104", 4), _point(5, "106", 6)]

    held = sum_wialon_sample_deltas(base + [superseded], **period)
    assert held.classification == "HELD" and held.reason == "reading_not_calculation_eligible"

    ok = sum_wialon_sample_deltas(base, **period)
    assert ok.classification in {"CONFIRMED", "ESTIMATED"}
    assert ok.km == Decimal("6.00")
