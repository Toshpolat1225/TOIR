import asyncio
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repositories import maintenance as repository
from app.services import maintenance as maintenance_service
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

    def test_locomotive_fixed_asset_mileage_is_not_used_for_maintenance_target(self):
        today = date.today()
        asset = SimpleNamespace(
            id=uuid4(), asset_type="locomotive", mileage=Decimal("90000")
        )
        interval = SimpleNamespace(id=uuid4(), interval_km=Decimal("10000"))

        self.assertEqual(
            asyncio.run(
                maintenance_service._interval_target(
                    asset, interval, {}, Decimal("200"), today
                )
            ),
            (None, today),
        )


class MaintenancePlanPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconcile_upserts_targets_for_matching_active_interval(self):
        today = date.today()
        asset = SimpleNamespace(
            id=uuid4(), asset_type="wagon", mileage=Decimal("199000")
        )
        interval = SimpleNamespace(
            id=uuid4(),
            asset_types=["wagon"],
            interval_km=Decimal("200000"),
            warn_percent=Decimal("10"),
            is_active=True,
        )
        with (
            patch.object(
                maintenance_service.settings, "daily_km_estimate", 200
            ),
            patch.object(
                maintenance_service.repository,
                "list_active_intervals",
                new=AsyncMock(return_value=[interval]),
            ),
            patch.object(
                maintenance_service.mileage_repository,
                "has_confirmed_projection",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                maintenance_service.repository,
                "upsert_scheduled_plan_with_created",
                new=AsyncMock(return_value=(SimpleNamespace(), True)),
            ) as upsert,
        ):
            created = await maintenance_service.reconcile_asset_plans(
                db=Mock(), asset=asset, mileage=asset.mileage
            )

        self.assertEqual(created, 1)
        upsert.assert_awaited_once_with(
            unittest.mock.ANY,
            asset_id=asset.id,
            interval_id=interval.id,
            trigger_mileage=Decimal("200000"),
            scheduled_date=today + timedelta(days=5),
        )

    async def test_reconcile_does_not_use_locomotive_fixed_asset_mileage(self):
        asset = SimpleNamespace(
            id=uuid4(), asset_type="locomotive", mileage=Decimal("199000")
        )
        with patch.object(
            maintenance_service.repository,
            "list_active_intervals",
            new=AsyncMock(),
        ) as list_intervals:
            created = await maintenance_service.reconcile_asset_plans(
                db=Mock(), asset=asset, mileage=asset.mileage
            )
        self.assertEqual(created, 0)
        list_intervals.assert_not_awaited()

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
