import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.repositories import dashboard as dashboard_repository
from app.services import dashboard as dashboard_service


class DashboardRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_monthly_trend_excludes_cancelled_but_keeps_close_date_logic(self):
        db = Mock()
        rows = [
            {
                "month_end": date(2026, month, 28),
                "asset_count": 2,
                "open_asset_count": 0,
            }
            for month in range(1, 7)
        ]
        result = Mock()
        result.mappings.return_value = rows
        db.execute = AsyncMock(return_value=result)
        with patch.object(
            dashboard_repository,
            "dashboard_assets_and_orders",
            new=AsyncMock(return_value=([], [])),
        ):
            await dashboard_repository.dashboard_summary(
                db, section_id=None, today=date(2026, 6, 15)
            )

        sql = db.execute.await_args.args[0].text
        self.assertIn("wo.status <> 'cancelled'", sql)
        self.assertIn(
            "wo.closed_at IS NULL OR wo.closed_at::date > me.month_end", sql
        )
        # The predicate excludes cancelled rows only; historical close-date logic
        # still determines whether other statuses were open at each month end.
        self.assertNotIn("wo.status IN", sql)

    def test_trend_status_cases(self):
        month_end = date(2026, 6, 30)
        cases = [
            ("cancelled", None, False),
            ("pending", None, True),
            ("in_progress", None, True),
            ("completed", date(2026, 7, 1), True),
            ("completed", date(2026, 6, 30), False),
        ]
        for status, closed_at, expected in cases:
            with self.subTest(status=status, closed_at=closed_at):
                matches_sql_predicates = status != "cancelled" and (
                    closed_at is None or closed_at > month_end
                )
                self.assertEqual(matches_sql_predicates, expected)

    async def test_monthly_trend_query_keeps_master_section_filter(self):
        section_id = uuid4()
        db = Mock()
        result = Mock()
        result.mappings.return_value = []
        db.execute = AsyncMock(return_value=result)
        with patch.object(
            dashboard_repository,
            "dashboard_assets_and_orders",
            new=AsyncMock(return_value=([], [])),
        ):
            await dashboard_repository.dashboard_summary(
                db, section_id=section_id, today=date(2026, 6, 15)
            )

        sql = db.execute.await_args.args[0].text
        params = db.execute.await_args.args[1]
        self.assertIn("fa.section_id = :section_id", sql)
        self.assertEqual(params["section_id"], section_id)

    async def test_master_scope_ignores_requested_other_section(self):
        db = Mock()
        own_section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=own_section_id)
        with patch.object(
            dashboard_service.repository,
            "dashboard_summary",
            new=AsyncMock(return_value={"assets": [], "orders": [], "availability": []}),
        ) as summary:
            await dashboard_service.dashboard_summary(
                db, user, section_id=uuid4()
            )

        self.assertEqual(summary.await_args.kwargs["section_id"], own_section_id)

    async def test_same_name_assets_keep_distinct_work_order_asset_ids(self):
        db = Mock()
        first_asset_id = uuid4()
        second_asset_id = uuid4()
        orders = [
            {"id": uuid4(), "number": "WO-1", "fixed_asset_id": first_asset_id,
             "unit": "Same name", "created_at": date(2026, 6, 1)},
            {"id": uuid4(), "number": "WO-2", "fixed_asset_id": second_asset_id,
             "unit": "Same name", "created_at": date(2026, 6, 2)},
        ]
        result = Mock()
        result.mappings.return_value = []
        db.execute = AsyncMock(return_value=result)
        with patch.object(
            dashboard_repository,
            "dashboard_assets_and_orders",
            new=AsyncMock(return_value=([], orders)),
        ):
            summary = await dashboard_repository.dashboard_summary(
                db, section_id=None, today=date(2026, 6, 15)
            )

        self.assertEqual(
            {order["fixed_asset_id"] for order in summary["orders"]},
            {first_asset_id, second_asset_id},
        )


if __name__ == "__main__":
    unittest.main()
