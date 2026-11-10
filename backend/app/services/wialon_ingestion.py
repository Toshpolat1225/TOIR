import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mileage import WialonOdometerReading, WialonRawReceipt
from app.repositories import wialon_counters as counters_repository


@dataclass(frozen=True)
class WialonIngestionResult:
    asset_id: UUID | None
    reading_id: int | None
    accepted: bool
    calculation_eligible: bool
    classification: str
    reason: str | None


def _safe_payload(
    *,
    unit_id: str | None,
    odometer_km: Decimal | None,
    reading_at: datetime | None,
    engine_hours: Decimal | None,
    speed: Decimal | None,
    source_time_raw: str | None,
) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "odometer_km": str(odometer_km) if odometer_km is not None else None,
        "reading_at": reading_at.isoformat() if reading_at is not None else None,
        "source_time_raw": source_time_raw[:200] if source_time_raw else None,
        "engine_hours": str(engine_hours) if engine_hours is not None else None,
        "speed": str(speed) if speed is not None else None,
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _measurement_key(
    *,
    unit_id: str,
    reading_at: datetime | None,
    odometer_km: Decimal,
    payload_hash: str,
) -> str:
    if reading_at is None:
        identity = f"{unit_id}|missing-time|{payload_hash}"
    else:
        identity = f"{unit_id}|{reading_at.isoformat()}|{odometer_km}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def ingest_wialon_reading(
    db: AsyncSession,
    *,
    unit_id: str | None,
    odometer_km: Decimal | None,
    reading_at: datetime | None,
    engine_hours: Decimal | None = None,
    speed: Decimal | None = None,
    transport: Literal["push", "pull"],
    received_at: datetime | None = None,
    source_time_raw: str | None = None,
    source_time_verified: bool = False,
) -> WialonIngestionResult:
    if source_time_verified:
        raise ValueError("Wialon source-time policy is still pending")
    received_at = received_at or datetime.now(timezone.utc)
    if reading_at is not None:
        if reading_at.tzinfo is None or reading_at.utcoffset() is None:
            reading_at = None
        else:
            reading_at = reading_at.astimezone(timezone.utc)

    safe_payload = _safe_payload(
        unit_id=unit_id,
        odometer_km=odometer_km,
        reading_at=reading_at,
        engine_hours=engine_hours,
        speed=speed,
        source_time_raw=source_time_raw,
    )
    payload_hash = _fingerprint(safe_payload)
    asset = (
        await counters_repository.get_asset_by_wialon_id(db, unit_id)
        if unit_id
        else None
    )
    valid_odometer = (
        odometer_km is not None
        and odometer_km.is_finite()
        and odometer_km >= 0
    )
    accepted = bool(valid_odometer)
    reason = None
    if not valid_odometer:
        reason = "odometer_missing_or_invalid"
    elif asset is None:
        reason = "unmapped_unit"
    elif reading_at is None:
        reason = "source_reading_time_missing_or_invalid"
    else:
        reason = "source_time_policy_pending"

    reading_id = None
    calculation_eligible = False
    classification = "HELD"
    conflict = False
    if unit_id and valid_odometer:
        measurement_key = _measurement_key(
            unit_id=unit_id,
            reading_at=reading_at,
            odometer_km=odometer_km,
            payload_hash=payload_hash,
        )
        if reading_at is not None:
            lock_key = f"wialon:{unit_id}:{reading_at.isoformat()}"
            await db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(lock_key, 0)
                    )
                )
            )
        calculation_eligible = False
        statement = (
            pg_insert(WialonOdometerReading)
            .values(
                asset_id=asset.id if asset is not None else None,
                source_unit_id=unit_id,
                odometer_km=odometer_km,
                reading_at=reading_at,
                received_at=received_at,
                accepted=accepted,
                calculation_eligible=calculation_eligible,
                classification=(
                    "CONFIRMED" if calculation_eligible else "HELD"
                ),
                rejection_reason=reason,
                payload_hash=payload_hash,
                measurement_key=measurement_key,
                payload=safe_payload,
            )
            .on_conflict_do_nothing()
        )
        await db.execute(statement)
        result = await db.execute(
            select(WialonOdometerReading).where(
                WialonOdometerReading.measurement_key == measurement_key
            )
        )
        reading = result.scalar_one_or_none()
        if reading is not None:
            reading_id = reading.id

        if reading_at is not None:
            result = await db.execute(
                select(WialonOdometerReading)
                .where(
                    WialonOdometerReading.source_unit_id == unit_id,
                    WialonOdometerReading.reading_at == reading_at,
                )
                .with_for_update()
            )
            same_time_readings = list(result.scalars().all())
            conflict = any(
                row.odometer_km != odometer_km for row in same_time_readings
            )
            if conflict:
                reason = "same_time_different_odometer"
                for row in same_time_readings:
                    row.calculation_eligible = False
                    row.classification = "HELD"
                    row.rejection_reason = reason

        if conflict:
            calculation_eligible = False
        classification = "CONFIRMED" if calculation_eligible else "HELD"
        if reading is not None and not source_time_verified:
            reason = reason or "source_time_policy_pending"
            reading.rejection_reason = reason

    db.add(
        WialonRawReceipt(
            source_unit_id=unit_id,
            asset_id=asset.id if asset is not None else None,
            reading_id=reading_id,
            transport=transport,
            received_at=received_at,
            payload_hash=payload_hash,
            payload=safe_payload,
        )
    )
    await db.flush()
    return WialonIngestionResult(
        asset.id if asset is not None else None,
        reading_id,
        accepted,
        calculation_eligible,
        classification,
        reason or ("source_time_policy_pending" if reading_id is not None else None),
    )
