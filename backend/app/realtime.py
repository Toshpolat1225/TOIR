import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import WebSocket

from app.core.config import settings
from app.models.identity import User

logger = logging.getLogger(__name__)

ALLOWED_TABLES = frozenset({"work_orders", "fixed_assets", "users"})
EVENT_QUEUE_SIZE = 1000


def event_visible_to_user(user: User, event: dict[str, Any]) -> bool:
    if event.get("table") not in ALLOWED_TABLES:
        return False
    if user.role != "master":
        return True
    if user.section_id is None:
        return False
    try:
        scopes = {UUID(str(value)) for value in event.get("section_ids", [])}
    except (TypeError, ValueError):
        return False
    return user.section_id in scopes


@dataclass(eq=False)
class RealtimeClient:
    websocket: WebSocket
    user: User
    tables: set[str] = field(default_factory=set)


class RealtimeHub:
    def __init__(self) -> None:
        self.clients: set[RealtimeClient] = set()
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=EVENT_QUEUE_SIZE
        )

    def connect(self, websocket: WebSocket, user: User, tables: set[str]) -> RealtimeClient:
        client = RealtimeClient(websocket=websocket, user=user, tables=tables)
        self.clients.add(client)
        return client

    def disconnect(self, client: RealtimeClient) -> None:
        self.clients.discard(client)

    async def publish(self, event: dict[str, Any]) -> None:
        if event.get("table") not in ALLOWED_TABLES:
            return
        operation = event.get("op")
        action = {"INSERT": "created", "UPDATE": "updated", "DELETE": "deleted"}.get(
            str(operation).upper()
        )
        if action is None:
            return
        try:
            event_id = str(UUID(str(event["id"])))
        except (KeyError, TypeError, ValueError):
            logger.warning("Ignoring malformed PostgreSQL realtime event")
            return

        payload = {
            "resource": event["table"],
            "action": action,
            "id": event_id,
        }
        for client in tuple(self.clients):
            if event["table"] not in client.tables:
                continue
            if not event_visible_to_user(client.user, event):
                continue
            try:
                await client.websocket.send_json(payload)
            except Exception:
                logger.warning("Realtime send failed; removing disconnected client")
                self.disconnect(client)


hub = RealtimeHub()


async def listen_for_database_events() -> None:
    delay = 1
    dsn = settings.sqlalchemy_database_url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    while True:
        connection: asyncpg.Connection | None = None
        try:
            connection = await asyncpg.connect(dsn=dsn)
            await connection.add_listener(
                "toir_changes",
                lambda _connection, _pid, _channel, payload: _enqueue_payload(payload),
            )
            logger.info("Listening for PostgreSQL realtime notifications")
            delay = 1
            while True:
                await asyncio.sleep(30)
                await connection.execute("SELECT 1")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("PostgreSQL realtime listener disconnected; reconnecting")
        finally:
            if connection is not None and not connection.is_closed():
                try:
                    await connection.close()
                except Exception:
                    logger.debug("Failed to close PostgreSQL realtime connection")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)


def _enqueue_payload(payload: str) -> None:
    try:
        event = json.loads(payload)
        if not isinstance(event, dict):
            raise ValueError("Event payload must be an object")
        hub.events.put_nowait(event)
    except (json.JSONDecodeError, ValueError, asyncio.QueueFull):
        logger.warning("Ignoring invalid or overloaded PostgreSQL realtime event")


async def dispatch_database_events() -> None:
    while True:
        event = await hub.events.get()
        try:
            await hub.publish(event)
        finally:
            hub.events.task_done()
