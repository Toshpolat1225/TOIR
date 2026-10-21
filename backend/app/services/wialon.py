import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory
from app.integrations.wialon_client import WialonClient, WialonClientError
from app.repositories import wialon as repository
from app.schemas.wialon import WialonSyncResult, WialonSyncStatus
from app.services import assets as assets_service

logger = logging.getLogger(__name__)
_sync_lock = asyncio.Lock()
ONLINE_WINDOW = timedelta(minutes=15)


def is_wialon_unit_online(
    last_message_at: datetime | None, *, now: datetime
) -> bool:
    return last_message_at is not None and last_message_at >= now - ONLINE_WINDOW


def _safe_status(message: str) -> str:
    return message.replace("\n", " ").replace("\r", " ")[:500]


def _display_status(message: str | None) -> str | None:
    if message is None:
        return None
    if message == "error: Wialon synchronization failed":
        return message
    if re.fullmatch(
        r"ok: found=\d+, updated=\d+, not_found=\d+",
        message,
    ):
        return message
    return "previous status omitted because it is not a recognized safe status"


async def get_sync_status(db: AsyncSession) -> WialonSyncStatus:
    row = await repository.get_sync_settings(db)
    return WialonSyncStatus(
        enabled=settings.wialon_pull_enabled,
        interval_minutes=settings.wialon_sync_interval_minutes,
        last_sync_at=row.last_sync_at if row is not None else None,
        last_sync_status=(
            _display_status(row.last_sync_status) if row is not None else None
        ),
    )


async def _record_failure(db: AsyncSession, synced_at: datetime) -> None:
    await repository.save_sync_status(
        db, synced_at=synced_at, status="error: Wialon synchronization failed"
    )


async def sync_wialon_assets(db: AsyncSession) -> WialonSyncResult:
    if not settings.wialon_pull_enabled or settings.wialon_host is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Wialon pull synchronization is not configured",
        )
    token = settings.wialon_token
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Wialon pull synchronization is not configured",
        )

    async with _sync_lock:
        synced_at = datetime.now(timezone.utc)
        try:
            client = WialonClient(
                settings.wialon_host,
                token.get_secret_value(),
            )
            units = await client.fetch_units()
            updated_names: list[str] = []
            missing_names: list[str] = []
            for unit in units:
                is_online = is_wialon_unit_online(
                    unit.last_message_at, now=synced_at
                )
                result = await assets_service.receive_wialon_update(
                    db,
                    unit_id=unit.unit_id,
                    unit_name=unit.name,
                    mileage=unit.mileage,
                    speed=unit.speed,
                    online=is_online,
                    allow_zero_mileage=True,
                )
                if result.get("found"):
                    updated_names.append(unit.name)
                else:
                    missing_names.append(unit.name)

            result = WialonSyncResult(
                found=len(updated_names),
                updated=len(updated_names),
                not_found=len(missing_names),
                not_found_units=missing_names,
            )
            summary = (
                f"ok: found={result.found}, updated={result.updated}, "
                f"not_found={result.not_found}"
            )
            await repository.save_sync_status(
                db,
                synced_at=synced_at,
                status=_safe_status(summary),
            )
            return result
        except Exception as exc:
            await db.rollback()
            await _record_failure(db, synced_at)
            logger.error("Wialon synchronization failed (%s)", type(exc).__name__)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Wialon synchronization failed",
            ) from None


async def run_periodic_wialon_sync() -> None:
    while True:
        if settings.wialon_pull_enabled:
            try:
                async with SessionFactory() as db:
                    await sync_wialon_assets(db)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Background Wialon synchronization failed (%s)",
                    type(exc).__name__,
                )
        await asyncio.sleep(settings.wialon_sync_interval_minutes * 60)
