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

    def interval(
        self,
        loco=None,
        start_km="100",
        end_km="140",
        source="a",
        received=None,
        is_main=False,
    ):
        return OdometerInterval(
            locomotive_asset_id=loco or self.loco_a,
            start_km=Decimal(start_km),
            end_km=Decimal(end_km),
            start_at=self.start,
            end_at=self.end,
            received_at=received or self.received,
            source_id=source,
            is_main=is_main,
        )

    def test_single_valid_locomotive_is_selected(self):
        decision = select_main_locomotive([self.interval()])
        self.assertEqual(decision.selected.source_id, "a")
        self.assertEqual(decision.confidence, "high")

    def test_within_tolerance_selects_one_locomotive_without_summing(self):
        primary = self.interval(start_km="100", end_km="140", source="a")
        second = self.interval(
            loco=uuid4(), start_km="500", end_km="541", source="b"
        )
        decision = select_main_locomotive([primary, second])

        self.assertIsNotNone(decision.selected)
        self.assertEqual(decision.selected.source_id, "a")
        self.assertEqual(decision.reason, "locomotive_distances_within_tolerance")

    def test_ten_percent_locomotive_disagreement_is_held(self):
        first = self.interval(start_km="100", end_km="140", source="a")
        second = self.interval(
            loco=uuid4(), start_km="500", end_km="544", source="b"
        )
        decision = select_main_locomotive([first, second])

        self.assertIsNone(decision.selected)
        self.assertEqual(decision.reason, "locomotive_distance_conflict")
        self.assertEqual(decision.confidence, "conflict")

    def test_single_gtk_main_locomotive_has_selection_priority(self):
        primary = self.interval(
            loco=uuid4(), start_km="100", end_km="140", source="main", is_main=True
        )
        newer = self.interval(
            loco=uuid4(), start_km="500", end_km="141", source="newer"
        )
        decision = select_main_locomotive([newer, primary])

        self.assertIsNotNone(decision.selected)
        self.assertEqual(decision.selected.source_id, "main")

    def test_disagreeing_locomotives_are_held(self):
        second = self.interval(loco=uuid4(), start_km="500", end_km="560", source="b")
        decision = select_main_locomotive([self.interval(), second])
        self.assertIsNone(decision.selected)
        self.assertEqual(decision.confidence, "conflict")

    def test_no_unapproved_receipt_lag_cutoff_is_applied(self):
        stale = self.interval(received=self.end + timedelta(hours=1))
        decision = select_main_locomotive([stale])
        self.assertIsNotNone(decision.selected)

    def test_full_membership_receives_full_distance(self):
        allocations = allocate_distance_to_wagons(
            self.interval(),
            [WagonMembershipInterval(self.wagon_a, 10, self.start, self.end)],
        )
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].km, Decimal("40.00"))
        self.assertFalse(allocations[0].estimated)

    def test_partial_membership_is_estimated_without_fabricated_distance(self):
        membership_start = self.start + timedelta(minutes=30)
        allocations = allocate_distance_to_wagons(
            self.interval(),
            [WagonMembershipInterval(self.wagon_a, 10, membership_start, self.end)],
        )
        self.assertIsNone(allocations[0].km)
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

    def test_membership_starting_at_interval_end_is_outside_half_open_interval(self):
        allocations = allocate_distance_to_wagons(
            self.interval(),
            [
                WagonMembershipInterval(
                    self.wagon_a,
                    10,
                    self.end,
                    self.end + timedelta(hours=1),
                )
            ],
        )
        self.assertEqual(allocations, ())

    def test_invalid_odometer_decrease_is_rejected(self):
        decision = select_main_locomotive([self.interval(start_km="140", end_km="100")])
        self.assertIsNone(decision.selected)


if __name__ == "__main__":
    unittest.main()
