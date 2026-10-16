import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.repositories import maintenance as repository
from app.services import maintenance as service


class MaintenancePlanningTests(unittest.TestCase):
    def test_next_trigger_at_interval_boundary(self):
        self.assertEqual(
            service._next_km_trigger(Decimal("5000"), Decimal("5000"), []),
            Decimal("5000"),
        )

    def test_skipped_intervals_keep_latest_crossed_threshold_overdue(self):
        trigger = service._next_km_trigger(
            Decimal("12500"), Decimal("5000"), []
        )
        self.assertEqual(trigger, Decimal("10000"))
        today = date.today()
        scheduled = service.estimate_date(
            today, trigger - Decimal("12500"), Decimal("200")
        )
        self.assertEqual(scheduled, today - timedelta(days=13))

    def test_day_interval_forecast_does_not_require_daily_kilometers(self):
        today = date(2026, 10, 16)
        asset = SimpleNamespace(id=uuid4(), mileage=Decimal("0"))
        interval = SimpleNamespace(
            id=uuid4(), interval_km=None, interval_days=30
        )
        _, scheduled = service._interval_target(
            asset, interval, {}, None, today
        )
        self.assertEqual(scheduled, today + timedelta(days=30))

    def test_scheduled_plan_with_past_date_is_overdue(self):
        plan = SimpleNamespace(
            status="scheduled",
            trigger_mileage=None,
            scheduled_date=date.today() - timedelta(days=1),
        )
        self.assertEqual(service._plan_status(plan, Decimal("0")), "overdue")


class MaintenancePlanPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_warning_boundary_uses_expected_threshold_and_date(self):
        today = date.today()
        asset = SimpleNamespace(
            id=uuid4(), asset_type="locomotive", mileage=Decimal("4500")
        )
        interval = SimpleNamespace(
            id=uuid4(),
            interval_km=Decimal("5000"),
            interval_days=None,
            warn_percent=Decimal("10"),
        )
        db = Mock()
        with (
            patch.object(
                service, "get_daily_average_km", new=AsyncMock(return_value=Decimal("200"))
            ),
            patch.object(
                service.repository,
                "list_active_intervals",
                new=AsyncMock(return_value=[interval]),
            ),
            patch.object(
                service.repository, "plans_for_interval", new=AsyncMock(return_value=[])
            ),
            patch.object(
                service.repository, "upsert_scheduled_plan", new=AsyncMock()
            ) as upsert,
        ):
            await service.reconcile_asset_plans(db=db, asset=asset, mileage=asset.mileage)

        upsert.assert_awaited_once_with(
            db,
            asset_id=asset.id,
            interval_id=interval.id,
            trigger_mileage=Decimal("5000"),
            scheduled_date=today + timedelta(days=3),
        )

    async def test_upsert_reuses_scheduled_plan_for_same_trigger(self):
        today = date.today()
        plan = SimpleNamespace(
            status="scheduled",
            scheduled_date=today,
            updated_at=None,
        )
        db = SimpleNamespace(add=Mock(), flush=AsyncMock())
        asset_id = uuid4()
        interval_id = uuid4()
        with patch.object(
            repository,
            "get_plan_for_trigger",
            new=AsyncMock(return_value=plan),
        ) as get_existing:
            first = await repository.upsert_scheduled_plan(
                db,
                asset_id=asset_id,
                interval_id=interval_id,
                trigger_mileage=Decimal("5000"),
                scheduled_date=today + timedelta(days=1),
            )
            second = await repository.upsert_scheduled_plan(
                db,
                asset_id=asset_id,
                interval_id=interval_id,
                trigger_mileage=Decimal("5000"),
                scheduled_date=today + timedelta(days=2),
            )

        self.assertIs(first, plan)
        self.assertIs(second, plan)
        self.assertEqual(get_existing.await_count, 2)
        self.assertEqual(plan.scheduled_date, today + timedelta(days=2))
        db.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
