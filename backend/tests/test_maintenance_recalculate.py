import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app import cli


class RecalculatePlansTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_filters_active_asset_types_and_continues_after_failure(self):
        assets = [
            SimpleNamespace(id=uuid4(), mileage=100),
            SimpleNamespace(id=uuid4(), mileage=200),
            SimpleNamespace(id=uuid4(), mileage=300),
        ]
        result = Mock()
        result.scalars.return_value.all.return_value = assets

        class Savepoint:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

        db = SimpleNamespace(
            execute=AsyncMock(return_value=result),
            begin_nested=Mock(side_effect=lambda: Savepoint()),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )

        class SessionContext:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *_):
                return None

        output = StringIO()
        with (
            patch.object(cli, "SessionFactory", return_value=SessionContext()),
            patch.object(
                cli, "engine", SimpleNamespace(dispose=AsyncMock())
            ) as engine,
            patch.object(
                cli.maintenance_service,
                "reconcile_asset_plans",
                new=AsyncMock(side_effect=[2, RuntimeError("asset failed"), 1]),
            ) as reconcile,
            self.assertLogs("app.cli", level="ERROR"),
            redirect_stdout(output),
        ):
            exit_code = await cli._recalculate_plans()

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "ko‘rib chiqildi: 3; yangi rejalar: 3; xatolar: 1",
            output.getvalue(),
        )
        self.assertEqual(reconcile.await_count, 3)
        self.assertEqual(db.commit.await_count, 2)
        db.rollback.assert_awaited_once()
        engine.dispose.assert_awaited_once()

        query = str(
            db.execute.await_args.args[0].compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("fixed_assets.asset_type IN ('locomotive', 'diesel')", query)
        self.assertIn("fixed_assets.status = 'operational'", query)


if __name__ == "__main__":
    unittest.main()
