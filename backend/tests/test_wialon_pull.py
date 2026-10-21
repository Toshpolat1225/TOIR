import asyncio
import io
import json
import logging
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import HTTPException
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.wialon_client import (
    SEARCH_FLAGS,
    WialonClient,
    WialonClientError,
    WialonUnit,
    parse_units,
)
from app.services import assets, wialon


class WialonClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_parses_message_speed_and_odometer(self):
        requests: list[dict[str, str]] = []
        request_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            request_urls.append(str(request.url))
            form = parse_qs(request.content.decode())
            requests.append({key: values[0] for key, values in form.items()})
            service = form["svc"][0]
            if service == "token/login":
                return httpx.Response(200, json={"eid": "session-id"})
            if service == "core/search_items":
                params = json.loads(form["params"][0])
                self.assertEqual(params["flags"], SEARCH_FLAGS)
                self.assertEqual(params["spec"]["itemsType"], "avl_unit")
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": 71,
                                "nm": "TЭМ 1234",
                                "lmsg": {
                                    "t": 1_782_000_000,
                                    "pos": {"s": 12.5},
                                },
                                "counters": {"mileage": {"act": 23456.7}},
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"error": 0})

        client = WialonClient(
            "https://gps.agmk.uz",
            "never-log-this-token",
            transport=httpx.MockTransport(handler),
        )
        units = await client.fetch_units()

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].unit_id, "71")
        self.assertEqual(units[0].name, "TЭМ 1234")
        self.assertEqual(units[0].speed, Decimal("12.5"))
        self.assertEqual(units[0].mileage, Decimal("23456.7"))
        self.assertIsNotNone(units[0].last_message_at)
        self.assertEqual(
            [request["svc"] for request in requests],
            ["token/login", "core/search_items", "core/logout"],
        )
        self.assertNotIn("never-log-this-token", " ".join(request_urls))
        self.assertEqual(urlparse(request_urls[0]).query, "")
        self.assertEqual(
            parse_qs(urlparse(request_urls[1]).query),
            {"sid": ["session-id"]},
        )
        self.assertEqual(
            parse_qs(urlparse(request_urls[2]).query),
            {"sid": ["session-id"]},
        )
        self.assertIn("never-log-this-token", requests[0]["params"])

    async def test_expired_session_reauthenticates_once(self):
        call_counts = {"login": 0, "search": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            form = parse_qs(request.content.decode())
            service = form["svc"][0]
            if service == "token/login":
                call_counts["login"] += 1
                return httpx.Response(
                    200, json={"eid": f"session-{call_counts['login']}"}
                )
            if service == "core/search_items":
                call_counts["search"] += 1
                if call_counts["search"] == 1:
                    return httpx.Response(200, json={"error": 1})
                return httpx.Response(200, json={"items": []})
            return httpx.Response(200, json={"error": 0})

        client = WialonClient(
            "https://gps.agmk.uz",
            "test-token",
            transport=httpx.MockTransport(handler),
        )
        self.assertEqual(await client.fetch_units(), [])
        self.assertEqual(call_counts, {"login": 2, "search": 2})

    async def test_transient_timeout_retries_up_to_three_attempts(self):
        attempts = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise httpx.ReadTimeout("mock timeout")
            return httpx.Response(200, json={"eid": "session-id"})

        client = WialonClient("https://gps.agmk.uz", "test-token")
        with patch("app.integrations.wialon_client.asyncio.sleep", new=AsyncMock()):
            async with httpx.AsyncClient(
                base_url="https://gps.agmk.uz",
                transport=httpx.MockTransport(handler),
            ) as transport_client:
                response = await client._request(
                    transport_client, "token/login", {"token": "test-token"}
                )
        self.assertEqual(response, {"eid": "session-id"})
        self.assertEqual(attempts, 3)

    async def test_login_rejection_never_logs_token(self):
        token = "must-not-appear-in-logs"

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": 4})

        client = WialonClient(
            "https://gps.agmk.uz",
            token,
            transport=httpx.MockTransport(handler),
        )
        log_output = io.StringIO()
        handler = logging.StreamHandler(log_output)
        target_logger = logging.getLogger("app.integrations.wialon_client")
        target_logger.addHandler(handler)
        try:
            with self.assertRaises(WialonClientError):
                await client.fetch_units()
        finally:
            target_logger.removeHandler(handler)
            handler.close()
        self.assertNotIn(token, log_output.getvalue())

    def test_unit_without_required_fields_is_skipped(self):
        self.assertEqual(
            parse_units({"items": [{"id": 1}, {"nm": "missing id"}, None]}),
            [],
        )

    def test_empty_credentials_disable_pull_and_default_is_off(self):
        config = Settings(
            _env_file=None,
            postgres_db="unit-test",
            postgres_user="unit-test",
            postgres_password="local-only",
            jwt_secret="local-only-secret-with-at-least-32-bytes",
            cors_origins="http://localhost:3000",
            wialon_host="",
            wialon_token="",
            wialon_sync_enabled=True,
        )
        self.assertFalse(config.wialon_pull_enabled)
        self.assertEqual(config.wialon_sync_interval_minutes, 2)

    def test_online_window_rejects_reports_older_than_fifteen_minutes(self):
        now = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(
            wialon.is_wialon_unit_online(
                now - timedelta(minutes=15), now=now
            )
        )
        self.assertFalse(
            wialon.is_wialon_unit_online(
                now - timedelta(minutes=15, seconds=1), now=now
            )
        )
        self.assertFalse(wialon.is_wialon_unit_online(None, now=now))

    async def test_pull_sync_counts_matches_and_persists_safe_status(self):
        now = datetime.now(timezone.utc)
        units = [
            WialonUnit("1", "ТЭМ 1234", now, Decimal("8"), Decimal("100")),
            WialonUnit("2", "Unknown 7777", None, None, None),
        ]
        settings = SimpleNamespace(
            wialon_pull_enabled=True,
            wialon_host="https://gps.agmk.uz",
            wialon_token=SecretStr("test-token"),
        )
        with (
            patch("app.services.wialon.settings", settings),
            patch(
                "app.services.wialon.WialonClient"
            ) as client_type,
            patch(
                "app.services.wialon.assets_service.receive_wialon_update",
                new=AsyncMock(
                    side_effect=[
                        {"found": True, "name": "ТЭМ 1234"},
                        {"found": False},
                    ]
                ),
            ) as update_asset,
            patch(
                "app.services.wialon.repository.save_sync_status",
                new=AsyncMock(),
            ) as save_status,
        ):
            client_type.return_value.fetch_units = AsyncMock(return_value=units)
            result = await wialon.sync_wialon_assets(object())

        self.assertEqual(result.found, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.not_found, 1)
        self.assertEqual(result.not_found_units, ["Unknown 7777"])
        self.assertTrue(update_asset.await_args_list[0].kwargs["online"])
        self.assertFalse(update_asset.await_args_list[1].kwargs["online"])
        self.assertNotIn("test-token", save_status.await_args.kwargs["status"])

    async def test_login_failure_is_sanitized_and_recorded(self):
        settings = SimpleNamespace(
            wialon_pull_enabled=True,
            wialon_host="https://gps.agmk.uz",
            wialon_token=SecretStr("never-log-this-token"),
        )
        failed_client = SimpleNamespace(
            fetch_units=AsyncMock(
                side_effect=WialonClientError("authentication rejected")
            )
        )
        db = SimpleNamespace(rollback=AsyncMock())
        with (
            patch("app.services.wialon.settings", settings),
            patch("app.services.wialon.WialonClient", return_value=failed_client),
            patch(
                "app.services.wialon.repository.save_sync_status",
                new=AsyncMock(),
            ) as save_status,
        ):
            with self.assertRaises(HTTPException) as raised:
                await wialon.sync_wialon_assets(db)
        self.assertEqual(getattr(raised.exception, "status_code", None), 502)
        self.assertNotIn("never-log-this-token", save_status.await_args.kwargs["status"])

    def test_unsafe_legacy_status_is_not_returned(self):
        self.assertEqual(
            wialon._display_status("token=secret https://host/path?token=secret"),
            "previous status omitted because it is not a recognized safe status",
        )

    async def test_periodic_loop_continues_after_failed_sync(self):
        class SessionContext:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *_):
                return None

        sleeps = AsyncMock(side_effect=[None, asyncio.CancelledError()])
        with (
            patch(
                "app.services.wialon.settings",
                SimpleNamespace(wialon_pull_enabled=True, wialon_sync_interval_minutes=1),
            ),
            patch(
                "app.services.wialon.SessionFactory",
                return_value=SessionContext(),
            ),
            patch(
                "app.services.wialon.sync_wialon_assets",
                new=AsyncMock(side_effect=HTTPException(status_code=502)),
            ) as sync,
            patch("app.services.wialon.asyncio.sleep", new=sleeps),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await wialon.run_periodic_wialon_sync()
        self.assertEqual(sync.await_count, 2)


class WialonAssetMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_wialon_id_match_is_used(self):
        asset = SimpleNamespace(id="asset-id", name="ТЭМ 1234")
        with (
            patch(
                "app.services.assets.repository.find_asset_by_wialon_id",
                new=AsyncMock(return_value=asset),
            ) as by_id,
            patch(
                "app.services.assets.repository.find_assets_by_name",
                new=AsyncMock(),
            ) as by_name,
        ):
            result = await assets.find_wialon_asset(
                object(), unit_id="w-123", unit_name="Different"
            )
        self.assertIs(result, asset)
        by_id.assert_awaited_once()
        by_name.assert_not_awaited()

    async def test_exact_name_and_unique_number_fallbacks(self):
        asset = SimpleNamespace(id="asset-id", name="ТЭМ 1234")
        db = object()
        with (
            patch(
                "app.services.assets.repository.find_asset_by_wialon_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.assets.repository.find_assets_by_name",
                new=AsyncMock(return_value=[asset]),
            ),
        ):
            self.assertIs(
                await assets.find_wialon_asset(
                    db, unit_id="unknown", unit_name="ТЭМ 1234"
                ),
                asset,
            )

        with (
            patch(
                "app.services.assets.repository.find_assets_by_name",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.assets.repository.list_wialon_assets",
                new=AsyncMock(return_value=[asset]),
            ),
        ):
            self.assertIs(
                await assets.find_wialon_asset(
                    db, unit_id=None, unit_name="Remote locomotive 1234"
                ),
                asset,
            )

    async def test_ambiguous_number_fallback_is_not_matched(self):
        first = SimpleNamespace(id="one", name="ТЭМ 1234")
        second = SimpleNamespace(id="two", name="ТЭМ 1234A")
        with (
            patch(
                "app.services.assets.repository.find_assets_by_name",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.assets.repository.list_wialon_assets",
                new=AsyncMock(return_value=[first, second]),
            ),
        ):
            result = await assets.find_wialon_asset(
                object(), unit_id=None, unit_name="Remote 1234"
            )
        self.assertIsNone(result)

    async def test_lower_odometer_updates_are_recorded_and_zero_is_allowed(self):
        asset = SimpleNamespace(
            id="asset-id",
            name="ТЭМ 1234",
            mileage=Decimal("1000"),
            wialon_speed=None,
            wialon_online=True,
            wialon_last_sync=None,
            updated_at=None,
        )
        with (
            patch(
                "app.services.assets.find_wialon_asset",
                new=AsyncMock(return_value=asset),
            ),
            patch(
                "app.services.assets._save_mileage_change",
                new=AsyncMock(),
            ) as save_mileage,
            patch(
                "app.services.assets._commit",
                new=AsyncMock(),
            ),
        ):
            result = await assets.receive_wialon_update(
                object(),
                unit_id="w-1",
                unit_name=asset.name,
                mileage=Decimal("0"),
                speed=Decimal("0"),
                online=False,
                allow_zero_mileage=True,
            )
        save_mileage.assert_awaited_once_with(
            unittest.mock.ANY, asset, Decimal("0"), "wialon"
        )
        self.assertFalse(asset.wialon_online)
        self.assertEqual(asset.wialon_speed, Decimal("0"))
        self.assertEqual(result["wialon_online"], False)

    async def test_decreased_mileage_is_persisted_with_wialon_source(self):
        asset = SimpleNamespace(
            id="asset-id",
            mileage=Decimal("1000"),
            updated_at=None,
        )
        db = object()
        with (
            patch(
                "app.services.assets.maintenance_repository.lock_asset_mileage",
                new=AsyncMock(return_value=Decimal("1000")),
            ),
            patch(
                "app.services.assets.repository.add_mileage_history",
                new=AsyncMock(),
            ) as add_history,
            patch(
                "app.services.assets.maintenance_service.reconcile_asset_plans",
                new=AsyncMock(),
            ),
        ):
            await assets._save_mileage_change(
                db, asset, Decimal("900"), "wialon"
            )
        self.assertEqual(asset.mileage, Decimal("900"))
        add_history.assert_awaited_once_with(
            db, asset.id, Decimal("900"), "wialon"
        )
