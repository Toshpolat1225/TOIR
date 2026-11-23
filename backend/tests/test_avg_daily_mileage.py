from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.avg_daily_mileage import Unit, daily_km_from_meter, evaluate_group, select_lists


def _units(*miles):
    return [Unit(uuid4(), Decimal(m)) for m in miles]


def test_big_and_small_lists():
    units = _units(1000, 950, 850, 790, 500, 100, 99, 0)
    top, big, small = select_lists(units)
    assert top == 1000
    assert sorted(int(u.mileage) for u in big) == [100, 500, 790, 850, 950, 1000]  # >= 10% of max
    assert sorted(int(u.mileage) for u in small) == [850, 950, 1000]  # >= 80% of max


def test_zero_mileage_group_has_no_lists():
    top, big, small = select_lists(_units(0, 0))
    assert top == 0 and big == [] and small == []


def test_average_uses_only_small_list():
    units = _units(1000, 900, 500)
    daily = {units[0].asset_id: Decimal(10), units[1].asset_id: Decimal(20), units[2].asset_id: Decimal(999)}
    r = evaluate_group(units, daily)
    assert r.small_count == 2 and r.with_data_count == 2 and r.avg_daily_km == Decimal("15.00") and r.reason is None


def test_no_gps_data_gives_no_number():
    units = _units(1000, 900)
    r = evaluate_group(units, {})
    assert r.avg_daily_km is None and r.reason == "no_gps_data"


def test_unit_without_data_is_skipped_not_counted_as_zero():
    units = _units(1000, 900)
    r = evaluate_group(units, {units[0].asset_id: Decimal(30)})
    assert r.with_data_count == 1 and r.avg_daily_km == Decimal("30.00")


def test_meter_daily_km():
    d = date
    assert daily_km_from_meter([(d(2026, 11, 16), Decimal(100)), (d(2026, 11, 23), Decimal(170))]) == Decimal(10)
    assert daily_km_from_meter([(d(2026, 11, 16), Decimal(100))]) is None
    assert daily_km_from_meter([(d(2026, 11, 16), Decimal(100)), (d(2026, 11, 20), Decimal(50))]) is None  # meter reset
