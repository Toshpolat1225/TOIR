from datetime import datetime, timezone
from decimal import Decimal
import re
import unicodedata
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.services import asset_links as asset_links_service
from app.services import asset_passport
from app.repositories import assets as assets_repository
from app.repositories import wialon_counters as counters_repository
from app.repositories import wialon_units as repository
from app.schemas.assets import asset_read
from app.schemas.wialon import (
    WialonAssetSuggestion,
    WialonAssetSuggestions,
    WialonCreateAssetRequest,
    WialonCreateAssetResponse,
    WialonRejectedReadingRead,
    WialonUnitDetail,
    WialonUnitRead,
)
from app.services.wialon import is_wialon_unit_online
from app.services.wialon_asset_import import (
    extract_asset_numbers,
    extract_asset_series,
)
from app.services.wialon_quality import Reading, evaluate

_SERIES_TRANSLATION = str.maketrans(
    {
        "a": "а",
        "c": "с",
        "d": "д",
        "e": "э",
        "h": "н",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "п",
        "t": "т",
        "x": "х",
        "y": "у",
    }
)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Wialon unit not found")


def _unit_read(row, *, now: datetime) -> WialonUnitRead:
    unit, asset, state, rejected_count = row
    return WialonUnitRead(
        unit_id=unit.unit_id,
        name=unit.name,
        cnm=unit.cnm,
        cneh=unit.cneh,
        speed=unit.speed,
        last_message_at=unit.last_message_at,
        is_online=is_wialon_unit_online(unit.last_message_at, now=now),
        suspect_absolute=unit.suspect_absolute,
        linked_asset=(
            {
                "id": asset.id,
                "name": asset.name,
                "inv_number": asset.inv_number,
            }
            if asset is not None
            else None
        ),
        counter_state=(
            {
                "last_status": state.last_status,
                "last_reason": state.last_reason,
            }
            if state is not None
            else None
        ),
        rejected_count=rejected_count,
    )


async def list_wialon_units(
    db: AsyncSession,
    *,
    linked: bool | None,
    q: str | None,
    online: bool | None,
    suspect: bool | None,
    stale: bool | None,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[WialonUnitRead], int]:
    now = datetime.now(timezone.utc)
    try:
        rows, total = await repository.list_units(
            db,
            linked=linked,
            q=q,
            online=online,
            suspect=suspect,
            stale=stale,
            master_section_id=master_section_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            now=now,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported sort field",
        ) from exc
    return [_unit_read(row, now=now) for row in rows], total


async def get_wialon_unit(
    db: AsyncSession, unit_id: str, *, master_section_id: UUID | None
) -> WialonUnitDetail:
    row = await repository.get_unit(
        db, unit_id, master_section_id=master_section_id
    )
    if row is None:
        raise _not_found()
    unit, asset, state, rejected_count = row
    result = _unit_read((unit, asset, state, rejected_count), now=datetime.now(timezone.utc))
    rejected = (
        await repository.list_rejected_readings(db, asset.id)
        if asset is not None
        else []
    )
    return WialonUnitDetail(
        **result.model_dump(),
        rejected_readings=[
            WialonRejectedReadingRead.model_validate(item) for item in rejected
        ],
    )


def _normalized_series(value: str | None) -> str | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold().translate(
        _SERIES_TRANSLATION
    )
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE) or None


async def suggest_wialon_asset_links(
    db: AsyncSession, unit_id: str, *, master_section_id: UUID | None
) -> WialonAssetSuggestions:
    unit = await repository.get_unit_record(
        db, unit_id, master_section_id=master_section_id
    )
    if unit is None:
        raise _not_found()
    if await repository.get_linked_asset(db, unit_id) is not None:
        return WialonAssetSuggestions(items=[])
    unit_series = extract_asset_series(unit.name)
    unit_numbers = extract_asset_numbers(unit.name) - extract_asset_numbers(
        unit_series
    )
    normalized_unit_series = _normalized_series(unit_series)
    if normalized_unit_series is None or not unit_numbers:
        return WialonAssetSuggestions(items=[])

    assets = await repository.list_unlinked_assets(
        db, master_section_id=master_section_id
    )
    suggestions: list[WialonAssetSuggestion] = []
    for asset in assets:
        asset_series = asset.series or extract_asset_series(asset.name)
        if _normalized_series(asset_series) != normalized_unit_series:
            continue
        asset_numbers = extract_asset_numbers(asset.name) - extract_asset_numbers(
            asset_series
        )
        matched_numbers = sorted(unit_numbers & asset_numbers)
        if not matched_numbers:
            continue
        suggestions.append(
            WialonAssetSuggestion(
                asset_id=asset.id,
                name=asset.name,
                inv_number=asset.inv_number,
                asset_type=asset.asset_type,
                series=asset.series,
                section_id=asset.section_id,
                matched_series=True,
                matched_numbers=matched_numbers,
            )
        )
    return WialonAssetSuggestions(items=suggestions)


async def create_asset_from_wialon_unit(
    db: AsyncSession,
    unit_id: str,
    payload: WialonCreateAssetRequest,
    *,
    by: UUID | None = None,
) -> WialonCreateAssetResponse:
    unit = await repository.get_unit_record(db, unit_id)
    if unit is None:
        raise _not_found()
    if await repository.get_linked_asset(db, unit_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wialon unit is already linked to a fixed asset",
        )
    if not await assets_repository.active_catalog_value_exists(
        db, kind="types", code=payload.asset_type
    ):
        raise HTTPException(status_code=422, detail="Asset type is unavailable")
    if not await assets_repository.active_catalog_value_exists(
        db, kind="statuses", code="operational"
    ):
        raise HTTPException(status_code=422, detail="Asset status is unavailable")
    if payload.section_id is not None and await repository.get_section(
        db, payload.section_id
    ) is None:
        raise HTTPException(
            status_code=422,
            detail="Cannot assign an archived or missing section to a fixed asset",
        )

    now = datetime.now(timezone.utc)
    mileage = Decimal("0") if unit.suspect_absolute else (unit.cnm or Decimal("0"))
    passport_fields = await asset_passport.prepare_new_asset(
        db,
        asset_type=payload.asset_type,
        name=payload.name or unit.name,
        model_id=payload.model_id,
        model_name=payload.series,
        number=payload.number,
    )
    if payload.name is None:
        passport_fields["name"] = (
            f"{passport_fields['series']} {passport_fields['number']}"
        )
    asset = FixedAsset(
        inv_number=payload.inv_number,
        **passport_fields,
        asset_type=payload.asset_type,
        section_id=payload.section_id,
        status="operational",
        mileage=mileage,
        wialon_id=unit_id,
        wialon_last_sync=unit.last_synced_at,
        wialon_speed=unit.speed,
        wialon_online=is_wialon_unit_online(
            unit.last_message_at, now=now
        ),
        inv_number_is_provisional=(
            payload.inv_number.upper().startswith("WIALON-")
        ),
        updated_at=now,
    )
    try:
        await assets_repository.add_asset(db, asset)
        await db.flush()
        await asset_links_service.link(
            db,
            asset.id,
            "wialon",
            unit_id,
            by,
            external_name=unit.name,
        )
        reading = Reading(unit.cnm, unit.cneh, unit.last_message_at)
        gate = evaluate(None, reading, now=now)
        await counters_repository.save_decision(
            db, asset.id, None, gate, reading, now=now
        )
        await assets_repository.add_mileage_history(
            db, asset.id, mileage, "wialon"
        )
        await db.commit()
        await db.refresh(asset)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory number or Wialon ID already exists, or section is invalid",
        ) from exc
    except Exception:
        await db.rollback()
        raise

    return WialonCreateAssetResponse(
        asset=asset_read(asset),
        warning=(
            "Wialon mileage is suspicious; fixed-asset mileage was set to 0 "
            "and needs manual correction."
            if unit.suspect_absolute
            else None
        ),
    )
