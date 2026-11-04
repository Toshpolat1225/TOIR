import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from pydantic import SecretStr, ValidationError
from sqlalchemy.dialects import postgresql

from app.core import permissions
from app.core.config import Settings
from app.main import _create_gtk_sync_task
from app.integrations.gtk_client import (
    GtkClient,
    GtkClientError,
    GtkLoginError,
    GtkParseError,
    build_snapshot,
    norm_train,
    quality_report,
)
from app.models.gtk import (
    GtkCarriage,
    GtkLocomotive,
    GtkLocomotiveMileageCheckpoint,
    GtkSyncRun,
    GtkTrain,
    GtkTrainMember,
    GtkWagonMileageLog,
)
from app.models.assets import MileageHistory
from app.repositories import gtk as repository
from app.routers import gtk as gtk_router
from app.schemas.gtk import GtkStatusRead
from app.services import gtk as service


def _mini_html() -> str:
    blocks = {
        "locomotives": [
            {
                "id": 1,
                "name": "L-1",
                "garage_number": "12345",
                "inventory_number": "odd",
                "start_expl_date": "2024-01-01 00:00:00",
                "end_expl_date": None,
            }
        ],
        "carriages": [
            {
                "id": 2,
                "name": "Car 2",
                "reg_number": "R-1",
                "inventory_number": "C-2",
                "end_expl_date": None,
            },
            {
                "id": 3,
                "name": "Car 3",
                "reg_number": "R-1",
                "inventory_number": "C-3",
                "end_expl_date": "2020-01-01",
            },
        ],
        "trains": [
            {
                "id": 5,
                "number": "99999",
                "title": "Test train",
                "begin_time": "2023-10-01 12:00:00",
                "end_time": None,
                "locomotive_list": [
                    {"locomotive": 1, "is_main": True, "order": 1}
                ],
                "carriage_list": [
                    {"carriage": 2, "order": 1},
                    {"carriage": 3, "order": 2},
                ],
            }
        ],
        "carriageStates": [
            {
                "carriage_id": 2,
                "is_loaded": True,
                "is_not_serviceable": False,
                "point": {"lat": 41.3, "lon": 69.2},
                "state_duration": 120,
            }
        ],
    }
    return "\n".join(
        f"var {name} = {json.dumps(value)};" for name, value in blocks.items()
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Database:
    def begin(self):
        return _Transaction()


class GtkParserTests(unittest.IsolatedAsyncioTestCase):
    def test_synthetic_html_parses_utc_and_quality_checks(self):
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        snapshot = build_snapshot(_mini_html(), "synthetic", now=now)

        self.assertEqual(len(snapshot["locomotives"]), 1)
        self.assertEqual(len(snapshot["carriages"]), 2)
        self.assertEqual(len(snapshot["trains"]), 1)
        self.assertEqual(
            snapshot["locomotives"][0]["start_expl_date"],
            datetime(2023, 12, 31, 19, tzinfo=timezone.utc),
        )
        quality = snapshot["quality"]
        self.assertNotIn("checkpoint_mileage", snapshot["locomotives"][0])
        self.assertNotIn("checkpoint_at", snapshot["locomotives"][0])
        self.assertEqual(quality["locomotives_without_inventory"], [])
        self.assertEqual(len(quality["locomotives_odd_inventory_format"]), 1)
        self.assertEqual(quality["carriages_reg_number_duplicate_groups"]["R-1"], [2, 3])
        self.assertEqual(len(quality["inactive_carriages_in_open_trains"]), 1)
        self.assertEqual(len(quality["open_trains_older_than_days"]), 1)
        self.assertEqual(len(quality["train_number_locomotive_mismatches"]), 1)

    def test_missing_required_block_raises_parse_error(self):
        with self.assertRaises(GtkParseError):
            build_snapshot("<p>not a GTK page</p>", "synthetic")

    def test_empty_named_blocks_are_distinct_from_missing_blocks(self):
        html = "\n".join(
            f"var {name} = [];"
            for name in ("locomotives", "carriages", "trains", "carriageStates")
        )

        snapshot = build_snapshot(html, "synthetic")

        self.assertEqual(snapshot["locomotives"], [])
        self.assertEqual(snapshot["carriages"], [])
        self.assertEqual(snapshot["trains"], [])

    def test_open_train_stale_check_uses_exact_30_day_boundary(self):
        train_row = {
            "id": 5,
            "number": "5",
            "begin_time": "2024-01-01 00:00:00",
            "end_time": None,
        }
        exact_boundary = datetime(2024, 1, 30, 19, tzinfo=timezone.utc)
        exact_train = norm_train(train_row, exact_boundary)
        past_boundary = norm_train(
            train_row, datetime(2024, 1, 30, 19, 0, 1, tzinfo=timezone.utc)
        )

        self.assertEqual(
            quality_report([], [], [exact_train], [])["open_trains_older_than_days"],
            [],
        )
        self.assertEqual(
            len(
                quality_report([], [], [past_boundary], [])[
                    "open_trains_older_than_days"
                ]
            ),
            1,
        )

    async def test_login_and_content_fetch_use_only_three_read_only_requests(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if request.method == "GET" and len(calls) == 1:
                return httpx.Response(
                    200,
                    text='<form><input name="csrfmiddlewaretoken" value="csrf"><input type="password"></form>',
                )
            if request.method == "POST":
                self.assertEqual(request.headers["referer"], str(calls[0].url))
                return httpx.Response(200, text="logged in")
            return httpx.Response(200, text=_mini_html())

        client = GtkClient(
            "http://gtk.example",
            "reader",
            SecretStr("private-password"),
            "/railway/__railway_train/",
            "EnterprisesControlRB=1",
            transport=httpx.MockTransport(handler),
        )
        snapshot = await client.fetch_snapshot()

        self.assertEqual([request.method for request in calls], ["GET", "POST", "GET"])
        self.assertTrue(all(request.method in {"GET", "POST"} for request in calls))
        self.assertEqual(len(snapshot["trains"]), 1)
        self.assertNotIn("private-password", repr(snapshot))


class GtkRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_mirror_upsert_is_conflict_safe_and_preserves_first_seen(self):
        db = SimpleNamespace(execute=AsyncMock())
        now = datetime.now(timezone.utc)
        snapshot = {
            "locomotives": [{"gtk_id": 1, "name": "L", "is_active": True}],
            "carriages": [{"gtk_id": 2, "name": "C", "is_active": True}],
            "trains": [{"gtk_id": 3, "number": "T", "is_open": True}],
        }

        await repository.upsert_mirror(db, snapshot, synced_at=now)

        self.assertEqual(db.execute.await_count, 3)
        statements = [
            call.args[0].compile(dialect=postgresql.dialect())
            for call in db.execute.await_args_list
        ]
        for statement in statements:
            sql = str(statement)
            self.assertIn("ON CONFLICT (gtk_id) DO UPDATE", sql)
            self.assertNotIn("first_seen_at =", sql)
        for table_name in ("gtk_locomotives", "gtk_carriages", "gtk_trains"):
            self.assertTrue(any(table_name in str(statement) for statement in statements))

    async def test_membership_history_opens_updates_and_closes(self):
        now = datetime.now(timezone.utc)
        retained = SimpleNamespace(
            train_gtk_id=5,
            kind="locomotive",
            object_gtk_id=1,
            is_main=False,
            ord=0,
            gtk_begin_time=None,
            observed_to=None,
        )
        removed = SimpleNamespace(
            train_gtk_id=5,
            kind="carriage",
            object_gtk_id=8,
            observed_to=None,
        )
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_Result([retained, removed])),
            add=Mock(),
        )
        snapshot = {
            "trains": [
                {
                    "gtk_id": 5,
                    "begin_time": now,
                    "is_open": True,
                    "locomotives": [
                        {"gtk_id": 1, "is_main": True, "order": 2}
                    ],
                    "carriages": [{"gtk_id": 9, "order": 1}],
                }
            ]
        }

        await repository.sync_memberships(db, snapshot, observed_at=now)

        self.assertIsNone(retained.observed_to)
        self.assertTrue(retained.is_main)
        self.assertEqual(retained.ord, 2)
        self.assertEqual(removed.observed_to, now)
        created = db.add.call_args.args[0]
        self.assertEqual(created.object_gtk_id, 9)
        self.assertEqual(created.observed_from, now)
        self.assertIsNone(created.observed_to)


class GtkSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_more_than_half_drop_records_suspicious_without_mirror_change(self):
        snapshot = {
            "locomotives": [],
            "carriages": [{"gtk_id": 1}],
            "trains": [],
            "quality": {},
        }
        saved = []

        async def save_run(db, run):
            saved.append(run)

        with (
            patch.object(service, "_auto_sync_stopped", False),
            patch.object(service, "_consecutive_login_failures", 0),
            patch.object(service, "GtkClient") as client_class,
            patch.object(
                service.repository,
                "latest_successful_counts",
                new=AsyncMock(return_value={"carriages": 10, "trains": 10}),
            ),
            patch.object(service.repository, "upsert_mirror", new=AsyncMock()) as upsert,
            patch.object(service.repository, "sync_memberships", new=AsyncMock()) as memberships,
            patch.object(service.repository, "add_sync_run", new=save_run),
        ):
            client_class.return_value.fetch_snapshot = AsyncMock(return_value=snapshot)
            run = await service.sync_gtk(_Database())

        self.assertEqual(run.status, "suspicious")
        self.assertFalse(upsert.await_count)
        self.assertFalse(memberships.await_count)
        self.assertEqual(saved[0].status, "suspicious")

    async def test_three_login_failures_stop_further_fetches_until_restart(self):
        fetch = AsyncMock(side_effect=GtkLoginError("GTK login failed"))

        async def save_run(db, run):
            return run

        with (
            patch.object(service, "_auto_sync_stopped", False),
            patch.object(service, "_consecutive_login_failures", 0),
            patch.object(service, "GtkClient") as client_class,
            patch.object(service, "_write_run", new=save_run),
        ):
            client_class.return_value.fetch_snapshot = fetch
            db = _Database()
            results = [await service.sync_gtk(db) for _ in range(3)]
            stopped = await service.sync_gtk(db)
            self.assertTrue(service.auto_sync_stopped())

        self.assertEqual([run.status for run in results], ["login_failed"] * 3)
        self.assertIsNone(stopped)
        self.assertEqual(fetch.await_count, 3)

    async def test_exception_text_is_not_saved_logged_or_returned_by_status(self):
        secret = "private-gtk-password"
        saved = []

        async def save_run(db, run):
            run.id = 1
            saved.append(run)
            return run

        async def fail_fetch(*args, **kwargs):
            raise GtkClientError(secret)

        settings = SimpleNamespace(
            gtk_host=None,
            gtk_user=None,
            gtk_password=SecretStr(secret),
            gtk_page_path="/",
            gtk_page_query="",
            gtk_sync_enabled=True,
            gtk_pull_enabled=False,
            gtk_sync_interval_minutes=10,
        )
        with (
            patch.object(service, "_auto_sync_stopped", False),
            patch.object(service, "_consecutive_login_failures", 0),
            patch.object(service, "settings", settings),
            patch.object(service, "GtkClient") as client_class,
            patch.object(service, "_write_run", new=save_run),
            self.assertLogs("app.services.gtk", level="ERROR") as logs,
        ):
            client_class.return_value.fetch_snapshot = fail_fetch
            run = await service.sync_gtk(_Database())
            with patch.object(
                service.repository,
                "latest_sync_run",
                new=AsyncMock(return_value=run),
            ):
                status = GtkStatusRead.model_validate(
                    await service.get_status(_Database())
                ).model_dump_json()

        self.assertEqual(run.error, "GTK request failed")
        self.assertNotIn(secret, run.error)
        self.assertNotIn(secret, "\n".join(logs.output))
        self.assertNotIn(secret, status)
        self.assertFalse(GtkStatusRead.model_validate_json(status).enabled)


class GtkPermissionAndRouteTests(unittest.TestCase):
    def test_routes_and_permission_roles_match_read_only_scope(self):
        paths = {route.path for route in gtk_router.router.routes}
        self.assertTrue(
            {
                "/gtk/status",
                "/gtk/locomotives",
                "/gtk/carriages",
                "/gtk/trains",
                "/gtk/trains/{gtk_id}",
                "/gtk/sync",
            }.issubset(paths)
        )
        self.assertIn("gtk.view", permissions.ROLE_DEFAULTS["admin"])
        self.assertIn("gtk.view", permissions.ROLE_DEFAULTS["operator"])
        self.assertIn("gtk.view", permissions.ROLE_DEFAULTS["management"])
        self.assertNotIn("gtk.view", permissions.ROLE_DEFAULTS["master"])
        self.assertIn("gtk.manage", permissions.ROLE_DEFAULTS["admin"])
        self.assertIn("gtk.manage", permissions.ROLE_DEFAULTS["operator"])
        self.assertNotIn("gtk.manage", permissions.ROLE_DEFAULTS["management"])
        self.assertIn("gtk.view", permissions.ROLE_DENIED["master"])
        self.assertIn("gtk.manage", permissions.ROLE_DENIED["master"])


class GtkConfigTests(unittest.TestCase):
    def test_empty_gtk_variables_use_safe_defaults(self):
        config = Settings(
            _env_file=None,
            postgres_db="test_db",
            postgres_user="test_user",
            postgres_password=SecretStr("not-a-real-password"),
            jwt_secret=SecretStr("x" * 32),
            cors_origins="http://localhost",
            gtk_host="",
            gtk_user="",
            gtk_password="",
            gtk_page_path="",
            gtk_page_query="",
            gtk_sync_enabled="",
            gtk_sync_interval_minutes="",
        )

        self.assertIsNone(config.gtk_host)
        self.assertIsNone(config.gtk_user)
        self.assertIsNone(config.gtk_password)
        self.assertEqual(config.gtk_page_path, "/railway/__railway_train/")
        self.assertEqual(config.gtk_page_query, "EnterprisesControlRB=1")
        self.assertFalse(config.gtk_sync_enabled)
        self.assertFalse(config.gtk_pull_enabled)
        self.assertEqual(config.gtk_sync_interval_minutes, 10)

    def test_enabled_sync_without_credentials_is_disabled_and_warned(self):
        config = Settings(
            _env_file=None,
            postgres_db="test_db",
            postgres_user="test_user",
            postgres_password=SecretStr("not-a-real-password"),
            jwt_secret=SecretStr("x" * 32),
            cors_origins="http://localhost",
            gtk_host="",
            gtk_user="",
            gtk_password="",
            gtk_sync_enabled=True,
        )
        self.assertTrue(config.gtk_sync_enabled)
        self.assertFalse(config.gtk_credentials_configured)
        self.assertFalse(config.gtk_pull_enabled)

        with (
            patch("app.main.settings", config),
            self.assertLogs("app.main", level="WARNING") as logs,
        ):
            task = _create_gtk_sync_task()

        self.assertIsNone(task)
        self.assertIn("automatic synchronization is disabled", logs.output[0])
        self.assertNotIn("not-a-real-password", "\n".join(logs.output))

    def test_complete_credentials_enable_sync(self):
        config = Settings(
            _env_file=None,
            postgres_db="test_db",
            postgres_user="test_user",
            postgres_password=SecretStr("not-a-real-password"),
            jwt_secret=SecretStr("x" * 32),
            cors_origins="http://localhost",
            gtk_host="http://gtk.example",
            gtk_user="reader",
            gtk_password=SecretStr("private-gtk-password"),
            gtk_sync_enabled=True,
        )
        self.assertTrue(config.gtk_credentials_configured)
        self.assertTrue(config.gtk_pull_enabled)

    def test_sync_interval_has_five_minute_minimum(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                postgres_db="test_db",
                postgres_user="test_user",
                postgres_password=SecretStr("not-a-real-password"),
                jwt_secret=SecretStr("x" * 32),
                cors_origins="http://localhost",
                gtk_sync_interval_minutes=4,
            )


class GtkMigrationContractTests(unittest.TestCase):
    def test_gtk_migrations_are_linear_and_revision_ids_fit_alembic(self):
        migrations_dir = Path(__file__).parents[1] / "alembic" / "versions"
        expected = [
            ("0013_gtk_source", "0012_wialon_units"),
            ("0014_fixed_assets_gtk_id", "0013_gtk_source"),
            ("0015_gtk_wagon_mileage", "0014_fixed_assets_gtk_id"),
            ("0016_gtk_mirror_cleanup", "0015_gtk_wagon_mileage"),
        ]
        for revision, previous in expected:
            source = (migrations_dir / f"{revision}.py").read_text(
                encoding="utf-8"
            )
            self.assertLessEqual(len(revision), 32)
            self.assertIsNotNone(
                re.search(rf'^revision = "{revision}"', source, re.MULTILINE),
                revision,
            )
            self.assertIsNotNone(
                re.search(
                    rf'^down_revision = "{previous}"', source, re.MULTILINE
                ),
                revision,
            )

        baseline = (migrations_dir / "0001_baseline.sql").read_text(
            encoding="utf-8"
        )
        migration_15 = (migrations_dir / "0015_gtk_wagon_mileage.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "CHECK (source IN ('wialon','manual'))",
            baseline,
        )
        self.assertIn('"mileage_history_source_check"', migration_15)
        self.assertIn("source IN ('wialon','manual','gtk')", migration_15)
        self.assertIn(
            "mileage_history_source_check",
            {constraint.name for constraint in MileageHistory.__table__.constraints},
        )
        self.assertIn(
            "source       text NOT NULL DEFAULT 'wialon' CHECK "
            "(source IN ('wialon','manual','gtk'))",
            (Path(__file__).parents[2] / "postgres" / "schema.sql").read_text(
                encoding="utf-8"
            ),
        )
        migration_13 = (
            migrations_dir / "0013_gtk_source.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ON CONFLICT (code) DO NOTHING", migration_13)
        self.assertIn(
            "ON CONFLICT (role, permission_code) DO NOTHING",
            migration_13,
        )
        migration_16 = (
            migrations_dir / "0016_gtk_mirror_cleanup.py"
        ).read_text(encoding="utf-8")
        self.assertIn('op.drop_column("gtk_locomotives", "checkpoint_at")', migration_16)
        self.assertIn(
            'op.drop_column("gtk_locomotives", "checkpoint_mileage")',
            migration_16,
        )

    def test_gtk_tables_match_canonical_schema_and_unused_checkpoint_is_gone(self):
        schema = (Path(__file__).parents[2] / "postgres" / "schema.sql").read_text(
            encoding="utf-8"
        )
        model_tables = (
            GtkLocomotive,
            GtkCarriage,
            GtkTrain,
            GtkTrainMember,
            GtkSyncRun,
            GtkWagonMileageLog,
            GtkLocomotiveMileageCheckpoint,
        )
        for model in model_tables:
            match = re.search(
                rf"CREATE TABLE {model.__tablename__} \((.*?)\n\);",
                schema,
                re.DOTALL,
            )
            self.assertIsNotNone(match, model.__tablename__)
            sql_columns = {
                column
                for column in re.findall(
                    r"^\s+([a-z][a-z0-9_]*)\s+", match.group(1), re.MULTILINE
                )
                if column != "constraint"
            }
            self.assertEqual(
                sql_columns,
                set(model.__table__.columns.keys()),
                model.__tablename__,
            )
        self.assertNotIn("checkpoint_mileage", GtkLocomotive.__table__.columns)
        self.assertNotIn("checkpoint_at", GtkLocomotive.__table__.columns)
        self.assertIn(
            "gtk_id               varchar(100) CONSTRAINT uq_fixed_assets_gtk_id UNIQUE",
            schema,
        )

    def test_gtk_permission_seed_matches_role_defaults_without_master_grants(self):
        migration = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0013_gtk_source.py"
        ).read_text(encoding="utf-8")
        for role, permission in (
            ("admin", "gtk.view"),
            ("operator", "gtk.view"),
            ("management", "gtk.view"),
            ("admin", "gtk.manage"),
            ("operator", "gtk.manage"),
        ):
            self.assertIn(f"('{role}', '{permission}', true)", migration)
        for role, permission in (
            ("master", "gtk.view"),
            ("master", "gtk.manage"),
            ("management", "gtk.manage"),
        ):
            self.assertIn(f"('{role}', '{permission}', false)", migration)

    def test_frontend_gtk_types_and_visible_run_status_are_backend_compatible(self):
        repository_root = Path(__file__).parents[2]
        api_source = (repository_root / "lib" / "api.ts").read_text(
            encoding="utf-8"
        )
        page_source = (
            repository_root / "app" / "dashboard" / "os" / "gtk" / "page.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("gtk_id: string | null;", api_source)
        self.assertNotIn("checkpoint_mileage", api_source)
        self.assertNotIn("checkpoint_at: string", api_source)
        for status, label in (
            ("ok", "Успешно"),
            ("error", "Ошибка"),
            ("parse_error", "Ошибка разбора"),
            ("suspicious", "Подозрительные данные"),
            ("login_failed", "Ошибка входа"),
        ):
            self.assertIn(f'{status}: "{label}"', page_source)
        for reason, label in (
            ("inactive", "Вагон неактивен"),
            ("empty_name", "Нет названия вагона"),
            ("already_linked", "Уже привязан к ОС"),
            ("inventory_number_in_use", "Инвентарный номер уже занят"),
        ):
            self.assertIn(f'{reason}: "{label}"', page_source)


if __name__ == "__main__":
    unittest.main()
