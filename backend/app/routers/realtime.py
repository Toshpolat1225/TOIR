import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.identity import User
from app.models.permissions import RolePermission
from app.realtime import ALLOWED_TABLES, hub

router = APIRouter()
AUTH_TIMEOUT_SECONDS = 10


async def _authenticate(token: str) -> tuple[User | None, float | None]:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        if claims.get("type") != "access":
            return None, None
        user_id = UUID(claims["sub"])
        expires_at = float(claims["exp"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None, None

    async with SessionFactory() as db:
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            return None, None
        if user.role != "admin":
            allowed = await db.execute(
                select(RolePermission.id).where(
                    RolePermission.role == user.role,
                    RolePermission.permission_code == "realtime.view",
                    RolePermission.granted.is_(True),
                )
            )
            if allowed.scalar_one_or_none() is None:
                return None, None
        return user, expires_at


def _requested_tables(message: dict[str, Any]) -> set[str] | None:
    tables = message.get("tables")
    if (
        not isinstance(tables, list)
        or len(tables) > len(ALLOWED_TABLES)
        or any(not isinstance(table, str) for table in tables)
        or not set(tables).issubset(ALLOWED_TABLES)
    ):
        return None
    return set(tables)


@router.websocket("/ws")
async def realtime_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        try:
            message = await asyncio.wait_for(
                websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            await websocket.close(code=4401, reason="Authentication required")
            return
        except WebSocketDisconnect:
            return
        except (ValueError, RuntimeError):
            await websocket.close(code=4400, reason="Invalid authentication message")
            return

        if (
            not isinstance(message, dict)
            or message.get("type") != "auth"
            or not isinstance(message.get("access_token"), str)
            or len(message["access_token"]) > 8192
        ):
            await websocket.close(code=4401, reason="Invalid authentication")
            return
        tables = _requested_tables(message)
        if tables is None:
            await websocket.close(code=4400, reason="Invalid table subscription")
            return

        user, expires_at = await _authenticate(message["access_token"])
        if user is None or expires_at is None:
            await websocket.close(code=4401, reason="Invalid or expired access token")
            return

        client = hub.connect(websocket, user, tables)
        access_token = message["access_token"]
        loop = asyncio.get_running_loop()
        last_auth_check = loop.time()
        await websocket.send_json({"type": "ready"})
        while True:
            remaining = expires_at - datetime.now(timezone.utc).timestamp()
            if remaining <= 0:
                await websocket.close(code=4401, reason="Access token expired")
                break
            try:
                command = await asyncio.wait_for(websocket.receive_json(), timeout=min(30, remaining))
            except asyncio.TimeoutError:
                refreshed_user, refreshed_expiry = await _authenticate(access_token)
                if refreshed_user is None or refreshed_expiry is None:
                    await websocket.close(code=4403, reason="Permission denied")
                    break
                client.user = refreshed_user
                last_auth_check = loop.time()
                continue
            except (ValueError, RuntimeError):
                await websocket.close(code=4400, reason="Invalid subscription message")
                break
            if loop.time() - last_auth_check >= 30:
                refreshed_user, refreshed_expiry = await _authenticate(access_token)
                if refreshed_user is None or refreshed_expiry is None:
                    await websocket.close(code=4403, reason="Permission denied")
                    break
                client.user = refreshed_user
                last_auth_check = loop.time()
            if not isinstance(command, dict) or command.get("type") != "subscribe":
                await websocket.close(code=4400, reason="Unsupported command")
                break
            tables = _requested_tables(command)
            if tables is None:
                await websocket.close(code=4400, reason="Invalid table subscription")
                break
            client.tables = tables
            await websocket.send_json({"type": "subscribed", "tables": sorted(tables)})
    except WebSocketDisconnect:
        pass
    finally:
        for client in tuple(hub.clients):
            if client.websocket is websocket:
                hub.disconnect(client)
