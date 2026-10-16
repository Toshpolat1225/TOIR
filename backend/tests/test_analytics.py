import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services import analytics


class AnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_analytics_block_returns_empty_page(self):
        db = object()
        user = SimpleNamespace(role="admin", section_id=None)
        with patch.object(
            analytics.repository,
            "list_analytics",
            new=AsyncMock(return_value=([], 0)),
        ) as list_analytics:
            items, total = await analytics.list_analytics(
                db,
                user,
                view_name="section_efficiency",
                section_id=None,
                limit=50,
                offset=0,
            )

        self.assertEqual(items, [])
        self.assertEqual(total, 0)
        list_analytics.assert_awaited_once_with(
            db,
            view_name="section_efficiency",
            section_id=None,
            limit=50,
            offset=0,
        )

    async def test_master_scope_is_applied_by_service(self):
        db = object()
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id)
        with patch.object(
            analytics.repository,
            "list_analytics",
            new=AsyncMock(return_value=([], 0)),
        ) as list_analytics:
            await analytics.list_analytics(
                db,
                user,
                view_name="work_type_efficiency",
                section_id=None,
                limit=50,
                offset=0,
            )

        self.assertEqual(list_analytics.await_args.kwargs["section_id"], section_id)


if __name__ == "__main__":
    unittest.main()
