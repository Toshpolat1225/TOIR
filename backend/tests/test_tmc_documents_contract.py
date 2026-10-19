import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.repositories import tmc_documents as tmc_repository
from app.routers.tmc_documents import router
from app.services import tmc_documents


class TmcDocumentContractTests(unittest.IsolatedAsyncioTestCase):
    def test_documents_router_exposes_read_only_http_contract(self):
        route_methods = {
            method
            for route in router.routes
            for method in route.methods or set()
        }
        self.assertEqual(route_methods, {"GET"})

    async def test_list_search_query_builds_sql_without_database_writes(self):
        count_result = Mock()
        count_result.scalar_one.return_value = 0
        rows_result = Mock()
        rows_result.all.return_value = []
        db = Mock()
        db.execute = AsyncMock(side_effect=[count_result, rows_result])

        items, total = await tmc_repository.list_documents(
            db, section_id=None, department_id=None, status_filter=None,
            work_order_id=None, limit=20, offset=0, q="bearing",
        )

        self.assertEqual((items, total), ([], 0))
        self.assertEqual(db.execute.await_count, 2)

    async def test_master_list_passes_authenticated_section_to_repository(self):
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id)
        with patch.object(
            tmc_documents.repository,
            "list_documents",
            new=AsyncMock(return_value=([], 0)),
        ) as list_documents:
            items, total = await tmc_documents.list_documents(
                Mock(), user, department_id=None, status_filter=None,
                work_order_id=None, limit=50, offset=0,
            )

        self.assertEqual((items, total), ([], 0))
        self.assertEqual(list_documents.await_args.kwargs["section_id"], section_id)

    async def test_master_receives_404_for_foreign_or_missing_work_order(self):
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id)
        with (
            patch.object(
                tmc_documents.work_orders_repository,
                "get_order",
                new=AsyncMock(return_value=None),
            ) as get_order,
            patch.object(
                tmc_documents.repository,
                "list_documents",
                new=AsyncMock(),
            ) as list_documents,
        ):
            with self.assertRaises(HTTPException) as raised:
                await tmc_documents.list_documents(
                    Mock(), user, department_id=None, status_filter=None,
                    work_order_id=uuid4(), limit=50, offset=0,
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(get_order.await_args.kwargs["master_section_id"], section_id)
        list_documents.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
