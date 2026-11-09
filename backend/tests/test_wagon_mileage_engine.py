import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.services.wagon_mileage_engine import (
    OdometerInterval,
    WagonMembershipInterval,
    allocate_distance_to_wagons,
    select_main_locomotive,
)


class WagonMileageEngineTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.end = self.start + timedelta(hours=2)
        self.received = self.end + timedelta(minutes=1)
        self.loco_a = uuid4()
        self.wagon_a = uuid4()
        self.wagon_b = uuid4()

    def interval(self, loco=None, start_km="100", end_km="140", source="a", received=None):
        return OdometerInterval(
            locomotive_asset_id=loco or self.loco_a,
            start_km=Decimal(start_km),
            end_km=Decimal(end_km),
            start_at=self.start,
            end_at=self.end,
            received_at=received or self.received,
            source_id=source,
        )

    def test_single_valid_locomotive_is_selected(self):
        decision = select_main_locomotive([self.interval()])
        self.assertEqual(decision.selected.source_id, "a")
        self.assertEqual(decision.confidence, "high")

    def test_multiple_odometer_readings_are_not_summed_or_averaged(self):
        second = self.interval(loco=uuid4(), start_km="500", end_km="540", source="b")
        decision = select_main_locomotive([self.interval(), second])
        self.assertIsNotNone(decision.selected)
        self.assertEqual(decision.selected.end_km - decision.selected.start_km, Decimal("40"))
        self.assertEqual(decision.confidence, "corroborated")

    def test_disagreeing_locomotives_are_held(self):
        second = self.interval(loco=uuid4(), start_km="500", end_km="560", source="b")
        decision = select_main_locomotive([self.interval(), second])
        self.assertIsNone(decision.selected)
        self.assertEqual(decision.confidence, "conflict")

    def test_stale_reading_is_not_selected(self):
        stale = self.interval(received=self.end + timedelta(hours=1))
        decision = select_main_locomotive([stale])
        self.assertIsNone(decision.selected)

    def test_full_membership_receives_full_distance(self):
        allocations = allocate_distance_to_wagons(
            self.interval(),
            [WagonMembershipInterval(self.wagon_a, 10, self.start, self.end)],
        )
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].km, Decimal("40.00"))
        self.assertFalse(allocations[0].estimated)

    def test_partial_membership_is_interpolated_and_flagged(self):
        membership_start = self.start + timedelta(minutes=30)
        allocations = allocate_distance_to_wagons(
            self.interval(),
            [WagonMembershipInterval(self.wagon_a, 10, membership_start, self.end)],
        )
        self.assertEqual(allocations[0].km, Decimal("30.00"))
        self.assertTrue(allocations[0].estimated)

    def test_non_overlapping_wagon_gets_no_mileage(self):
        allocations = allocate_distance_to_wagons(
            self.interval(),
            [WagonMembershipInterval(
                self.wagon_a, 10, self.end + timedelta(minutes=1),
                self.end + timedelta(hours=1)
            )],
        )
        self.assertEqual(allocations, ())

    def test_duplicate_membership_is_not_double_counted(self):
        membership = WagonMembershipInterval(self.wagon_a, 10, self.start, self.end)
        allocations = allocate_distance_to_wagons(self.interval(), [membership, membership])
        self.assertEqual(len(allocations), 1)

    def test_invalid_odometer_decrease_is_rejected(self):
        decision = select_main_locomotive([self.interval(start_km="140", end_km="100")])
        self.assertIsNone(decision.selected)


if __name__ == "__main__":
    unittest.main()
