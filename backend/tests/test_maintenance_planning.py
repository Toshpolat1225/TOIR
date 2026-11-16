import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repositories import maintenance as repository
from app.services.maintenance_planning import (
    calculate_maintenance_target,
    maintenance_urgency,
    next_mileage_threshold,
)


class MaintenancePlanningTests(unittest.TestCase):
    def test_next_threshold_uses_ceiling_boundary(self):
        self.assertEqual(
            next_mileage_threshold(Decimal("199000"), Decimal("200000")),
            Decimal("200000"),
        )

    def test_zero_mileage_first_threshold_is_one_interval_not_zero(self):
        self.assertEqual(
            next_mileage_threshold(Decimal("0"), Decimal("5000")), Decimal("5000")
        )
        # a unit that has just reached a threshold is due now (remaining 0), not a full interval away
        self.assertEqual(
            next_mileage_threshold(Decimal("5000"), Decimal("5000")), Decimal("5000")
        )
        self.assertEqual(
            next_mileage_threshold(Decimal("5001"), Decimal("5000")), Decimal("10000")
        )

    def test_new_unit_with_zero_mileage_is_not_due_for_maintenance(self):
        target = calculate_maintenance_target(
            asset_type="locomotive",
            interval_asset_types=["locomotive", "diesel"],
            mileage=Decimal("0"),
            interval_km=Decimal("5000"),
            warn_percent=Decimal("10"),
            daily_km_estimate=200,
            today=date(2026, 11, 2),
        )

        self.assertIsNone(target)

    def test_warning_percent_excludes_distance_above_warning_window(self):
        target = calculate_maintenance_target(
            asset_type="locomotive",
            interval_asset_types=["locomotive", "diesel"],
            mileage=Decimal("178000"),
            interval_km=Decimal("200000"),
            warn_percent=Decimal("10"),
            daily_km_estimate=200,
            today=date(2026, 11, 2),
        )

        self.assertIsNone(target)

    def test_warning_boundary_returns_target(self):
        target = calculate_maintenance_target(
            asset_type="locomotive",
            interval_asset_types=["locomotive", "diesel"],
            mileage=Decimal("180000"),
            interval_km=Decimal("200000"),
            warn_percent=Decimal("10"),
            daily_km_estimate=200,
            today=date(2026, 11, 2),
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.trigger_mileage, Decimal("200000"))
        self.assertEqual(target.remaining_km, Decimal("20000"))

    def test_scheduled_date_rounds_remaining_days_up(self):
        target = calculate_maintenance_target(
            asset_type="diesel",
            interval_asset_types=["locomotive", "diesel"],
            mileage=Decimal("198500"),
            interval_km=Decimal("200000"),
            warn_percent=Decimal("10"),
            daily_km_estimate=200,
            today=date(2026, 11, 2),
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.scheduled_date, date(2026, 11, 2) + timedelta(days=8))

    def test_asset_type_mismatch_is_skipped(self):
        self.assertIsNone(
            calculate_maintenance_target(
                asset_type="wagon",
                interval_asset_types=["locomotive", "diesel"],
                mileage=Decimal("199000"),
                interval_km=Decimal("200000"),
                warn_percent=Decimal("10"),
                daily_km_estimate=200,
                today=date(2026, 11, 2),
            )
        )

    def test_interval_without_kilometers_is_skipped(self):
        self.assertIsNone(
            calculate_maintenance_target(
                asset_type="locomotive",
                interval_asset_types=["locomotive", "diesel"],
                mileage=Decimal("199000"),
                interval_km=None,
                warn_percent=Decimal("10"),
                daily_km_estimate=200,
                today=date(2026, 11, 2),
            )
        )

    def test_urgency_uses_remaining_interval_percent_bands(self):
        self.assertEqual(maintenance_urgency(Decimal("3"), Decimal("10")), "high")
        self.assertEqual(maintenance_urgency(Decimal("5"), Decimal("10")), "medium")
        self.assertEqual(maintenance_urgency(Decimal("8"), Decimal("10")), "low")
        self.assertIsNone(maintenance_urgency(Decimal("11"), Decimal("10")))


class MaintenancePlanPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_uses_unique_conflict_key(self):
        plan = SimpleNamespace(status="scheduled")
        result = Mock()
        result.scalar_one_or_none.return_value = plan
        db = SimpleNamespace(execute=AsyncMock(return_value=result))

        actual = await repository.upsert_scheduled_plan(
            db,
            asset_id=uuid4(),
            interval_id=uuid4(),
            trigger_mileage=Decimal("200000"),
            scheduled_date=date(2026, 11, 7),
        )

        self.assertIs(actual, plan)
        statement = db.execute.await_args.args[0]
        self.assertIn(
            "ON CONFLICT ON CONSTRAINT "
            "maintenance_plan_asset_id_interval_id_trigger_mileage_key",
            str(statement.compile(dialect=postgresql.dialect())),
        )

if __name__ == "__main__":
    unittest.main()
