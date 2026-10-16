import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.realtime import RealtimeHub, event_visible_to_user
from app.routers import realtime as realtime_router


class RealtimeEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_insert_is_forwarded_as_created_event(self):
        hub = RealtimeHub()
        websocket = SimpleNamespace(send_json=AsyncMock())
        user = SimpleNamespace(role="admin", section_id=None)
        hub.connect(websocket, user, {"work_orders"})

        await hub.publish(
            {
                "table": "work_orders",
                "op": "INSERT",
                "id": str(uuid4()),
                "section_ids": [],
            }
        )

        websocket.send_json.assert_awaited_once()
        self.assertEqual(
            websocket.send_json.await_args.args[0]["resource"],
            "work_orders",
        )
        self.assertEqual(
            websocket.send_json.await_args.args[0]["action"],
            "created",
        )

    async def test_master_receives_only_events_for_assigned_section(self):
        hub = RealtimeHub()
        websocket = SimpleNamespace(send_json=AsyncMock())
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id)
        hub.connect(websocket, user, {"fixed_assets"})

        await hub.publish(
            {
                "table": "fixed_assets",
                "op": "UPDATE",
                "id": str(uuid4()),
                "section_ids": [str(uuid4())],
            }
        )
        websocket.send_json.assert_not_awaited()

        event_id = uuid4()
        await hub.publish(
            {
                "table": "fixed_assets",
                "op": "UPDATE",
                "id": str(event_id),
                "section_ids": [str(section_id)],
            }
        )
        websocket.send_json.assert_awaited_once_with(
            {"resource": "fixed_assets", "action": "updated", "id": str(event_id)}
        )

    def test_unscoped_master_and_unknown_tables_are_denied(self):
        section_id = uuid4()
        master = SimpleNamespace(role="master", section_id=section_id)
        unscoped = SimpleNamespace(role="master", section_id=None)
        event = {"table": "users", "section_ids": [str(section_id)]}

        self.assertTrue(event_visible_to_user(master, event))
        self.assertFalse(event_visible_to_user(unscoped, event))
        self.assertFalse(
            event_visible_to_user(master, {"table": "refresh_tokens", "section_ids": [str(section_id)]})
        )

    async def test_invalid_access_token_closes_websocket(self):
        websocket = SimpleNamespace(
            accept=AsyncMock(),
            receive_json=AsyncMock(
                return_value={
                    "type": "auth",
                    "access_token": "invalid",
                    "tables": ["work_orders"],
                }
            ),
            close=AsyncMock(),
        )
        with patch.object(
            realtime_router,
            "_authenticate",
            new=AsyncMock(return_value=(None, None)),
        ):
            await realtime_router.realtime_websocket(websocket)

        websocket.close.assert_awaited_once()
        self.assertEqual(websocket.close.await_args.kwargs["code"], 4401)


if __name__ == "__main__":
    unittest.main()
