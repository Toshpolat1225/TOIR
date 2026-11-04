import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.services.mileage_attribution import (
    LocomotiveMileage,
    MileageCheckpoint,
    TrainMembership,
    WagonAsset,
    compute_attribution,
)


class MileageAttributionTests(unittest.TestCase):
    def setUp(self):
        self.started_at = datetime(2026, 11, 4, tzinfo=timezone.utc)
        self.observed_at = self.started_at + timedelta(hours=1)
        self.loco_asset_id = uuid4()
        self.wagon_asset_id = uuid4()
        self.loco_assets = {
            1: LocomotiveMileage(self.loco_asset_id, Decimal("110"))
        }
        self.wagon_assets = {
            2: WagonAsset(self.wagon_asset_id, is_active=True)
        }
        self.checkpoints = {
            1: MileageCheckpoint(
                self.loco_asset_id,
                Decimal("100"),
                self.started_at,
            )
        }
        self.previous = [
            TrainMembership(10, "locomotive", 1, is_main=True),
            TrainMembership(10, "carriage", 2),
        ]
        self.current = list(self.previous)

    def compute(self, **overrides):
        values = {
            "previous_memberships": self.previous,
            "current_memberships": self.current,
            "locomotive_assets": self.loco_assets,
            "wagon_assets": self.wagon_assets,
            "checkpoints": self.checkpoints,
            "observed_at": self.observed_at,
        }
        values.update(overrides)
        return compute_attribution(**values)

    def test_attributes_locomotive_delta_to_common_wagon(self):
        result = self.compute()
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].wagon_asset_id, self.wagon_asset_id)
        self.assertEqual(result.entries[0].km, Decimal("10.00"))
        self.assertEqual(result.attributed_km, Decimal("10.00"))
        self.assertEqual(result.wagons_updated, 1)

    def test_newly_added_wagon_does_not_receive_existing_delta(self):
        added_asset_id = uuid4()
        self.current.append(TrainMembership(10, "carriage", 3))
        result = self.compute(
            wagon_assets={
                **self.wagon_assets,
                3: WagonAsset(added_asset_id, is_active=True),
            }
        )
        self.assertEqual(
            [entry.wagon_asset_id for entry in result.entries],
            [self.wagon_asset_id],
        )

    def test_detached_wagon_is_not_attributed(self):
        self.current = [self.previous[0]]
        result = self.compute()
        self.assertEqual(result.entries, ())
        self.assertEqual(result.unattributed_km, Decimal("10.00"))

    def test_wagon_seen_in_two_trains_is_skipped(self):
        self.previous.append(TrainMembership(20, "carriage", 2))
        self.current.append(TrainMembership(20, "carriage", 2))
        result = self.compute()
        self.assertEqual(result.entries, ())
        self.assertEqual(result.unattributed_km, Decimal("10.00"))

    def test_excessive_delta_is_rejected_without_advancing_checkpoint(self):
        result = self.compute(
            locomotive_assets={
                1: LocomotiveMileage(self.loco_asset_id, Decimal("261"))
            }
        )
        self.assertEqual(result.entries, ())
        self.assertEqual(result.loco_rejected, 1)
        self.assertNotIn(1, result.checkpoints)

    def test_unlinked_main_locomotive_is_counted(self):
        result = self.compute(locomotive_assets={})
        self.assertEqual(result.entries, ())
        self.assertEqual(result.loco_unlinked, 1)

    def test_first_link_only_sets_baseline(self):
        result = self.compute(checkpoints={})
        self.assertEqual(result.entries, ())
        self.assertEqual(result.checkpoints[1].mileage, Decimal("110"))
        self.assertEqual(result.checkpoints[1].at, self.observed_at)

    def test_nonpositive_delta_is_not_attributed_and_rebaselines(self):
        result = self.compute(
            locomotive_assets={
                1: LocomotiveMileage(self.loco_asset_id, Decimal("99"))
            }
        )
        self.assertEqual(result.entries, ())
        self.assertEqual(result.checkpoints[1].mileage, Decimal("99"))

    def test_inactive_wagon_is_not_attributed(self):
        result = self.compute(
            wagon_assets={2: WagonAsset(self.wagon_asset_id, is_active=False)}
        )
        self.assertEqual(result.entries, ())
        self.assertEqual(result.unattributed_km, Decimal("10.00"))


if __name__ == "__main__":
    unittest.main()
