import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.repositories import assets as repository
from app.schemas.assets import (
    AssetStatus,
    AssetType,
    FixedAssetCreate,
    FixedAssetStats,
    FixedAssetUpdate,
    MileageHistoryList,
    MileageHistoryRead,
    MileageUpdate,
    asset_read,
)

logger = logging.getLogger(__name__)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Fixed asset not found",
    )


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _commit(db: AsyncSession, detail: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict(detail) from exc


async def _get_scoped_asset(
    db: AsyncSession, asset_id: UUID, master_section_id: UUID | None = None
) -> FixedAsset:
    asset = await repository.get_asset(
        db, asset_id, master_section_id=master_section_id
    )
    if asset is None:
        raise _not_found()
    return asset


async def list_fixed_assets(
    db: AsyncSession,
    *,
    asset_type: AssetType | None,
    asset_status: AssetStatus | None,
    section_id: UUID | None,
    master_section_id: UUID | None,
    depot: str | None,
    q: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
):
    effective_section_id = (
        master_section_id if master_section_id is not None else section_id
    )
    try:
        assets, total = await repository.list_assets(
            db,
            asset_type=asset_type,
            status=asset_status,
            section_id=effective_section_id,
            depot=depot,
            q=q,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported sort field",
        ) from exc
    return [asset_read(asset) for asset in assets], total


async def get_fixed_asset(
    db: AsyncSession, asset_id: UUID, *, master_section_id: UUID | None
):
    return asset_read(await _get_scoped_asset(db, asset_id, master_section_id))


async def get_fixed_asset_stats(
    db: AsyncSession, *, master_section_id: UUID | None
) -> FixedAssetStats:
    total, type_counts, status_counts, depots = await repository.asset_stats(
        db, master_section_id=master_section_id
    )
    asset_types: tuple[AssetType, ...] = ("locomotive", "diesel", "wagon")
    statuses: tuple[AssetStatus, ...] = (
        "operational",
        "maintenance",
        "repair",
        "out_of_service",
    )
    return FixedAssetStats(
        total=total,
        by_asset_type={key: type_counts.get(key, 0) for key in asset_types},
        by_status={key: status_counts.get(key, 0) for key in statuses},
        depots=depots,
    )


async def create_fixed_asset(
    db: AsyncSession, payload: FixedAssetCreate
):
    asset = FixedAsset(**payload.model_dump())
    await repository.add_asset(db, asset)
    await _commit(db, "Inventory number or Wialon ID already exists, or section is invalid")
    await db.refresh(asset)
    return asset_read(asset)


async def _save_mileage_change(
    db: AsyncSession, asset: FixedAsset, mileage: Decimal, source: str
) -> None:
    if asset.mileage == mileage:
        return
    previous_mileage = asset.mileage
    asset.mileage = mileage
    asset.updated_at = datetime.now(timezone.utc)
    await repository.add_mileage_history(db, asset.id, mileage, source)
    if source == "wialon" and mileage < previous_mileage:
        logger.warning("Wialon mileage decreased for fixed asset %s", asset.id)


async def update_fixed_asset(
    db: AsyncSession,
    asset_id: UUID,
    payload: FixedAssetUpdate,
    *,
    master_section_id: UUID | None = None,
):
    asset = await _get_scoped_asset(db, asset_id, master_section_id)
    changes = payload.model_dump(exclude_unset=True)
    mileage = changes.pop("mileage", None)
    for field_name, value in changes.items():
        setattr(asset, field_name, value)
    asset.updated_at = datetime.now(timezone.utc)
    if mileage is not None:
        await _save_mileage_change(db, asset, mileage, "manual")
    await _commit(
        db,
        "Inventory number or Wialon ID already exists, or section is invalid",
    )
    await db.refresh(asset)
    return asset_read(asset)


async def set_fixed_asset_mileage(
    db: AsyncSession,
    asset_id: UUID,
    payload: MileageUpdate,
    *,
    master_section_id: UUID | None = None,
):
    asset = await _get_scoped_asset(db, asset_id, master_section_id)
    await _save_mileage_change(db, asset, payload.mileage, "manual")
    await _commit(db, "Could not update fixed asset mileage")
    await db.refresh(asset)
    return asset_read(asset)


async def delete_fixed_asset(db: AsyncSession, asset_id: UUID) -> None:
    asset = await repository.get_asset(db, asset_id)
    if asset is None:
        raise _not_found()
    if await repository.count_asset_references(db, asset.id):
        raise _conflict(
            "Cannot delete fixed asset: it is referenced by work orders"
        )
    await db.delete(asset)
    await _commit(db, "Cannot delete fixed asset: it is referenced by existing records")


async def get_mileage_history(
    db: AsyncSession,
    asset_id: UUID,
    *,
    days: int,
    limit: int,
    master_section_id: UUID | None,
) -> MileageHistoryList:
    await _get_scoped_asset(db, asset_id, master_section_id)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    items, total = await repository.list_mileage_history(
        db, asset_id, since=since, limit=limit
    )
    return MileageHistoryList(
        items=[MileageHistoryRead.model_validate(item) for item in items],
        total=total,
        days=days,
        limit=limit,
    )


def _extract_number(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(match) for match in re.findall(r"(?<!\d)\d{2,4}(?!\d)", value)}


async def find_wialon_asset(
    db: AsyncSession, *, unit_id: str | None, unit_name: str | None
) -> FixedAsset | None:
    if unit_id:
        by_id = await repository.find_asset_by_wialon_id(db, unit_id.strip())
        if by_id is not None:
            return by_id

    name = unit_name.strip() if unit_name else ""
    if name:
        by_name = await repository.find_assets_by_name(db, name)
        if len(by_name) == 1:
            return by_name[0]

    numbers = _extract_number(name)
    if not numbers:
        return None
    candidates = await repository.list_wialon_assets(db)
    matches = [
        asset
        for asset in candidates
        if _extract_number(asset.name).intersection(numbers)
    ]
    return matches[0] if len(matches) == 1 else None


async def receive_wialon_update(
    db: AsyncSession,
    *,
    unit_id: str | None,
    unit_name: str | None,
    mileage: Decimal | None,
    speed: Decimal | None,
) -> dict[str, object]:
    asset = await find_wialon_asset(db, unit_id=unit_id, unit_name=unit_name)
    if asset is None:
        return {"found": False}

    now = datetime.now(timezone.utc)
    asset.wialon_last_sync = now
    asset.updated_at = now
    if speed is not None:
        asset.wialon_speed = speed
    asset.wialon_online = True
    if mileage is not None and mileage > 0:
        await _save_mileage_change(db, asset, mileage, "wialon")
    await _commit(db, "Could not save Wialon update")
    return {
        "found": True,
        "asset_id": str(asset.id),
        "name": asset.name,
        "mileage": str(asset.mileage),
        "wialon_online": True,
    }


def parse_wialon_decimal(value: object, field_name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} value",
        ) from exc
    if not parsed.is_finite():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} value",
        )
    max_integer_digits, max_decimal_places = (
        (10, 2) if field_name == "mileage" else (4, 2)
    )
    decimal_parts = parsed.as_tuple()
    integer_digits = max(len(decimal_parts.digits) + decimal_parts.exponent, 0)
    decimal_places = max(-decimal_parts.exponent, 0)
    if integer_digits > max_integer_digits or decimal_places > max_decimal_places:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} precision",
        )
    return parsed
