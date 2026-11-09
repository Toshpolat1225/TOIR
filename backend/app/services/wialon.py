import asyncio
import hashlib
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory
from app.integrations.wialon_client import WialonClient, WialonClientError
from app.repositories import wialon as repository
from app.repositories import wialon_counters as counters_repo
from app.repositories import wialon_units as units_repo
from app.schemas.wialon import WialonSyncResult, WialonSyncStatus
from app.models.mileage import WialonOdometerReading
from app.services import assets as assets_service
from app.services.audit_log import set_audit_system_context
from app.services.wialon_quality import Reading, Verdict, evaluate

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
    if message in {
        "error: Wialon synchronization failed",
        "Wialon: token yo‘q yoki noto‘g‘ri; token sozlamasini tekshiring",
        "Wialon: host mask rad etdi; administratorga murojaat qiling",
        "Wialon: ruxsat rad etildi (xato 7)",
        "Wialon: sessiya eskirdi; qayta avtorizatsiya kerak",
        "Wialon: javob kutish vaqti tugadi (timeout)",
        "Wialon: tarmoq xatosi; ulanishni tekshiring",
        "Wialon: avtorizatsiya javobi noto‘g‘ri",
        "Wialon: birliklar ro‘yxati noto‘g‘ri formatda",
        "Wialon: server javobi noto‘g‘ri formatda",
    }:
        return message
    if re.fullmatch(r"Wialon: so‘rov rad etildi \(xato \d+\)", message):
        return message
    if re.fullmatch(r"Wialon: server HTTP \d{3} qaytardi", message):
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


async def _record_failure(
    db: AsyncSession, synced_at: datetime, status_message: str
) -> None:
    await repository.save_sync_status(
        db, synced_at=synced_at, status=status_message
    )


async def _gated_mileage(db, unit, *, now: datetime, stats: Counter) -> Decimal | None:
    """Wialon `cnm` ni TOIR mileage'iga ABSOLYUT emas, DELTA sifatida o'tkazadi.

    None qaytsa mileage yangilanmaydi (baseline, o'zgarishsiz, rad etilgan, eski, mapping yo'q).
    Mapping faqat aniq wialon_id bo'yicha: topilmasa mileage yozilmaydi (tezlik/online avvalgidek yangilanadi).
    """
    asset = await counters_repo.get_asset_by_wialon_id(db, unit.unit_id)
    if asset is None:
        stats["unmapped"] += 1
        return None
    row = await counters_repo.get_state_row(db, asset.id)
    reading = Reading(unit.mileage, unit.engine_hours, unit.last_message_at)
    gate = evaluate(counters_repo.to_state(row), reading, now=now)
    if unit.mileage is not None and unit.last_message_at is not None:
        raw_payload = {
            "unit_id": unit.unit_id,
            "name": unit.name,
            "odometer_km": str(unit.mileage),
            "engine_hours": str(unit.engine_hours) if unit.engine_hours is not None else None,
            "reading_at": unit.last_message_at.isoformat(),
            "speed": str(unit.speed) if unit.speed is not None else None,
            "calc_flags": unit.calc_flags,
        }
        payload_bytes = json.dumps(
            raw_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        accepted = gate.mileage.verdict in {
            Verdict.ACCEPTED, Verdict.BASELINE, Verdict.UNCHANGED
        }
        await db.execute(
            pg_insert(WialonOdometerReading)
            .values(
                asset_id=asset.id,
                source_unit_id=unit.unit_id,
                odometer_km=unit.mileage,
                reading_at=unit.last_message_at,
                accepted=accepted,
                rejection_reason=gate.mileage.reason,
                payload_hash=payload_hash,
                payload=raw_payload,
            )
            .on_conflict_do_nothing(
                index_elements=[WialonOdometerReading.payload_hash]
            )
        )
    await counters_repo.save_decision(db, asset.id, row, gate, reading, now=now)
    stats[f"mileage_{gate.mileage.verdict.value}"] += 1
    stats[f"hours_{gate.hours.verdict.value}"] += 1
    if gate.mileage.verdict is Verdict.ACCEPTED and gate.mileage.delta:
        return asset.mileage + gate.mileage.delta
    return None


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

    set_audit_system_context(db, "wialon")
    async with _sync_lock:
        synced_at = datetime.now(timezone.utc)
        try:
            client = WialonClient(
                settings.wialon_host,
                token.get_secret_value(),
            )
            units = await client.fetch_units()
            await units_repo.upsert_units(db, units, synced_at=synced_at)
            await db.commit()
            updated_names: list[str] = []
            missing_names: list[str] = []
            gate_stats: Counter = Counter()
            for unit in units:
                is_online = is_wialon_unit_online(
                    unit.last_message_at, now=synced_at
                )
                safe_mileage = await _gated_mileage(
                    db, unit, now=synced_at, stats=gate_stats
                )
                result = await assets_service.receive_wialon_update(
                    db,
                    unit_id=unit.unit_id,
                    unit_name=unit.name,
                    mileage=safe_mileage,
                    speed=unit.speed,
                    online=is_online,
                    allow_zero_mileage=True,
                )
                if result.get("found"):
                    updated_names.append(unit.name)
                else:
                    missing_names.append(unit.name)

            logger.info("Wialon counter gate: %s", dict(gate_stats))
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
            status_message = (
                exc.status_message
                if isinstance(exc, WialonClientError)
                else "error: Wialon synchronization failed"
            )
            await _record_failure(db, synced_at, status_message)
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
