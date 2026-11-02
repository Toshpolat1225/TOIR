import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repositories import unified_assets as repository
from app.services import unified_assets


class UnifiedAssetTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_three_sources_are_mapped(self):
        now = datetime.now(timezone.utc)
        asset_id = uuid4()
        section_id = uuid4()
        rows = [
            (
                SimpleNamespace(
                    id=asset_id,
                    wialon_id="unit-1",
                    name="TOIR name",
                    asset_type="diesel",
                    series="TEM18",
                    inv_number="A-1",
                    status="operational",
                    section_id=section_id,
                    mileage=Decimal("200"),
                ),
                SimpleNamespace(
                    unit_id="unit-1",
                    name="Wialon name",
                    cnm=Decimal("500"),
                    cneh=Decimal("10"),
                    speed=Decimal("0"),
                    last_message_at=now,
                    suspect_absolute=False,
                ),
                SimpleNamespace(name="Section A"),
            ),
            (
                SimpleNamespace(
                    id=uuid4(),
                    wialon_id=None,
                    name="TOIR only",
                    asset_type="wagon",
                    series=None,
                    inv_number="A-2",
                    status="operational",
                    section_id=None,
                    mileage=Decimal("20"),
                ),
                None,
                None,
            ),
            (
                None,
                SimpleNamespace(
                    unit_id="unit-only",
                    name="Wialon only",
                    cnm=Decimal("30"),
                    cneh=None,
                    speed=None,
                    last_message_at=None,
                    suspect_absolute=True,
                ),
                None,
            ),
        ]
        with patch.object(
            unified_assets.repository,
            "list_unified_assets",
            new=AsyncMock(return_value=(rows, 3)),
        ):
            items, total = await unified_assets.list_unified_assets(
                object(),
                source=None,
                asset_type=None,
                asset_status=None,
                section_id=None,
                master_section_id=None,
                q=None,
                limit=50,
                offset=0,
                sort_by="name",
                sort_order="asc",
            )
        self.assertEqual(total, 3)
        self.assertEqual([item.source for item in items], ["both", "toir", "wialon"])
        self.assertEqual(items[0].name, "TOIR name")
        self.assertIsNone(items[2].asset_type)
        self.assertTrue(items[2].suspect_absolute)

    async def test_query_uses_full_join_filters_and_master_section_scope(self):
        own_section = uuid4()
        requested_section = uuid4()

        class Result:
            def scalar_one(self):
                return 0

            def all(self):
                return []

        class FakeDb:
            def __init__(self):
                self.statements = []

            async def execute(self, statement):
                self.statements.append(statement)
                return Result()

        db = FakeDb()
        await repository.list_unified_assets(
            db,
            source="wialon",
            asset_type="diesel",
            status="operational",
            section_id=requested_section,
            master_section_id=own_section,
            q="unit",
            limit=20,
            offset=5,
            sort_by="name",
            sort_order="desc",
            now=datetime(2026, 11, 2, tzinfo=timezone.utc),
        )

        count_sql, page_sql = (
            str(statement.compile(dialect=postgresql.dialect()))
            for statement in db.statements
        )
        self.assertIn("FULL OUTER JOIN wialon_units", page_sql)
        self.assertIn("fixed_assets.section_id", count_sql)
        self.assertIn("fixed_assets.asset_type", count_sql)
        self.assertIn("fixed_assets.status", count_sql)
        self.assertIn("CASE", count_sql)
        params = db.statements[0].compile(dialect=postgresql.dialect()).params
        self.assertIn(own_section, params.values())
        self.assertNotIn(requested_section, params.values())


if __name__ == "__main__":
    unittest.main()
