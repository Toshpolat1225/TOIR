import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.repositories import asset_source_links as asset_links_repository
from app.repositories import assets as repository
from app.repositories import references as references_repository
from app.repositories import maintenance as maintenance_repository
from app.repositories import wialon_counters as wialon_counters_repository
from app.repositories import wialon_units as wialon_units_repository
from app.repositories import gtk as gtk_repository
from app.services import maintenance as maintenance_service
from app.services import asset_links as asset_links_service
from app.services import asset_passport
from app.services import asset_field_changes as field_changes_service
from app.repositories import asset_models as asset_models_repository
from app.schemas.assets import (
    AssetStatus,
    AssetType,
    FixedAssetBulkOrgUnitUpdate,
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
    db: AsyncSession,
    asset_id: UUID,
    master_section_id: UUID | None = None,
    *,
    for_update: bool = False,
) -> FixedAsset:
    getter = repository.get_asset_for_update if for_update else repository.get_asset
    asset = await getter(db, asset_id, master_section_id=master_section_id)
    if asset is None:
        raise _not_found()
    return asset


async def list_fixed_assets(
    db: AsyncSession,
    *,
    asset_type: AssetType | None,
    asset_status: AssetStatus | None,
    status_behavior: str | None,
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
            status_behavior=status_behavior,
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
    db: AsyncSession, *, master_section_id: UUID | None, asset_type: str | None = None,
    asset_status: str | None = None, status_behavior: str | None = None,
    section_id: UUID | None = None, depot: str | None = None, q: str | None = None,
) -> FixedAssetStats:
    total, type_counts, status_counts, behavior_counts, section_counts, depots = await repository.asset_stats(
        db, master_section_id=master_section_id, asset_type=asset_type, status=asset_status,
        status_behavior=status_behavior, section_id=section_id, depot=depot, q=q,
    )
    return FixedAssetStats(
        total=total,
        by_asset_type=type_counts,
        by_status=status_counts,
        by_status_behavior=behavior_counts,
        by_section=section_counts,
        depots=depots,
    )


async def get_fixed_asset_passport_report(db: AsyncSession) -> dict:
    assets, sections = await repository.list_passport_report_data(db)
    return asset_passport.build_passport_report(assets, sections)


async def create_fixed_asset(
    db: AsyncSession, payload: FixedAssetCreate, *, by: UUID | None = None
):
    try:
        asset_passport.validate_passport_values(
            year_built=payload.year_built,
            commissioned_at=payload.commissioned_at,
            decommissioned_at=payload.decommissioned_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _validate_gtk_link(db, payload.gtk_id, payload.asset_type)
    if payload.section_id is not None and await references_repository.get_non_archived_section(
        db, payload.section_id
    ) is None:
        raise HTTPException(
            status_code=422,
            detail="Cannot assign an archived or missing section to a fixed asset",
        )
    if payload.org_unit_id is not None and await references_repository.get_non_archived_section(
        db, payload.org_unit_id
    ) is None:
        raise HTTPException(status_code=422, detail="Organization unit is unavailable")
    if not await repository.active_catalog_value_exists(db, kind="types", code=payload.asset_type):
        raise HTTPException(status_code=422, detail="Asset type is unavailable")
    if not await repository.active_catalog_value_exists(db, kind="statuses", code=payload.status):
        raise HTTPException(status_code=422, detail="Asset status is unavailable")
    passport_fields = await asset_passport.prepare_new_asset(
        db,
        asset_type=payload.asset_type,
        name=payload.name,
        model_id=payload.model_id,
        model_name=payload.series,
        number=payload.number,
    )
    asset_values = payload.model_dump()
    asset_values.update(passport_fields)
    asset_values["number_normalized"] = passport_fields["number_normalized"]
    asset_values["inv_number_is_provisional"] = payload.inv_number.upper().startswith(
        "WIALON-"
    )
    asset = FixedAsset(**asset_values)
    await repository.add_asset(db, asset)
    await db.flush()
    field_changes_service.record_manual_changes(
        db,
        asset,
        old_values={},
        new_values={
            field: getattr(asset, field)
            for field in field_changes_service.PASSPORT_FIELD_NAMES
        },
    )
    if payload.wialon_id is not None or payload.gtk_id is not None:
        await db.flush()
        if payload.wialon_id is not None:
            wialon_unit = await wialon_units_repository.get_unit_record(
                db, payload.wialon_id
            )
            await asset_links_service.link(
                db,
                asset.id,
                "wialon",
                payload.wialon_id,
                by,
                external_name=wialon_unit.name if wialon_unit is not None else None,
            )
        if payload.gtk_id is not None:
            gtk_kind = await gtk_repository.gtk_kind(db, payload.gtk_id)
            gtk_object = (
                await gtk_repository.get_locomotive(db, int(payload.gtk_id))
                if gtk_kind == "locomotive"
                else await gtk_repository.get_carriage(db, int(payload.gtk_id))
            )
            await asset_links_service.link(
                db,
                asset.id,
                "gtk",
                payload.gtk_id,
                by,
                external_name=gtk_object.name if gtk_object is not None else None,
            )
            if gtk_kind == "locomotive":
                await gtk_repository.reset_locomotive_mileage_checkpoint(
                    db, int(payload.gtk_id)
                )
    await _commit(
        db,
        "Inventory number, accounting number, model, number, source ID, or section conflicts",
    )
    await db.refresh(asset)
    return asset_read(asset)


async def _save_mileage_change(
    db: AsyncSession, asset: FixedAsset, mileage: Decimal, source: str
) -> None:
    previous_mileage = await maintenance_repository.lock_asset_mileage(db, asset.id)
    if previous_mileage is None or previous_mileage == mileage:
        return
    asset.mileage = mileage
    asset.updated_at = datetime.now(timezone.utc)
    await repository.add_mileage_history(db, asset.id, mileage, source)
    try:
        async with db.begin_nested():
            await maintenance_service.reconcile_asset_plans(db, asset, mileage)
    except Exception:
        logger.exception(
            "Could not reconcile maintenance plans for fixed asset %s",
            asset.id,
        )
    if source == "wialon" and mileage < previous_mileage:
        logger.warning("Wialon mileage decreased for fixed asset %s", asset.id)


async def update_fixed_asset(
    db: AsyncSession,
    asset_id: UUID,
    payload: FixedAssetUpdate,
    *,
    master_section_id: UUID | None = None,
    by: UUID | None = None,
):
    asset = await _get_scoped_asset(
        db, asset_id, master_section_id, for_update=True
    )
    changes = payload.model_dump(exclude_unset=True)
    active_links = {
        link.source: link
        for link in await asset_links_repository.get_active(db, asset.id)
    }
    previous_gtk_id = active_links.get("gtk").external_id if "gtk" in active_links else None
    previous_wialon_id = (
        active_links.get("wialon").external_id if "wialon" in active_links else None
    )
    next_asset_type = changes.get("asset_type", asset.asset_type)
    if "asset_type" in changes and not await repository.active_catalog_value_exists(db, kind="types", code=changes["asset_type"]):
        raise HTTPException(status_code=422, detail="Asset type is unavailable")
    for source, link_row in active_links.items():
        field_name = f"{source}_id"
        if field_name not in changes or changes[field_name] == link_row.external_id:
            await asset_links_service.validate_asset_type(
                db, next_asset_type, source, link_row.external_id
            )
    next_gtk_id = changes.get("gtk_id", previous_gtk_id)
    wialon_id_changed = (
        "wialon_id" in changes and changes["wialon_id"] != previous_wialon_id
    )
    if "status" in changes and not await repository.active_catalog_value_exists(db, kind="statuses", code=changes["status"]):
        raise HTTPException(status_code=422, detail="Asset status is unavailable")
    if "org_unit_id" in changes and changes["org_unit_id"] is not None:
        if await references_repository.get_non_archived_section(
            db, changes["org_unit_id"]
        ) is None:
            raise HTTPException(status_code=422, detail="Organization unit is unavailable")
    passport_fields_changed = {
        "year_built",
        "commissioned_at",
        "decommissioned_at",
    }.intersection(changes)
    if passport_fields_changed:
        try:
            asset_passport.validate_passport_values(
                year_built=changes.get("year_built", asset.year_built),
                commissioned_at=changes.get(
                    "commissioned_at", asset.commissioned_at
                ),
                decommissioned_at=changes.get(
                    "decommissioned_at", asset.decommissioned_at
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    model_id = changes.get("model_id", asset.model_id)
    if model_id is not None:
        model = await asset_models_repository.get_model(db, model_id)
        if model is None or model.asset_type != next_asset_type:
            raise HTTPException(
                status_code=422, detail="Asset model type does not match asset type"
            )
    if "number" in changes or "number_normalized" in changes:
        number = changes.get("number", asset.number)
        changes["number_normalized"] = (
            asset_passport.normalize_token(number) if number else None
        )
    if "inv_number" in changes or "inv_number_is_provisional" in changes:
        inv_number = changes.get("inv_number", asset.inv_number)
        changes["inv_number_is_provisional"] = inv_number.upper().startswith(
            "WIALON-"
        )
    section_id = changes.get("section_id")
    if section_id is not None and section_id != asset.section_id:
        if await references_repository.get_non_archived_section(db, section_id) is None:
            raise HTTPException(
                status_code=422,
                detail="Cannot assign an archived or missing section to a fixed asset",
            )
    mileage = changes.pop("mileage", None)
    old_passport_values = {
        field: getattr(asset, field, None)
        for field in field_changes_service.PASSPORT_FIELD_NAMES
    }
    new_passport_values = {
        field: changes[field]
        for field in field_changes_service.PASSPORT_FIELD_NAMES
        if field in changes
    }
    field_changes_service.record_manual_changes(
        db,
        asset,
        old_values=old_passport_values,
        new_values=new_passport_values,
    )
    for field_name, value in changes.items():
        setattr(asset, field_name, value)
    asset.updated_at = datetime.now(timezone.utc)
    if "wialon_id" in changes:
        next_wialon_id = changes["wialon_id"]
        if next_wialon_id is None:
            if previous_wialon_id is not None:
                await asset_links_service.unlink(db, asset.id, "wialon")
        else:
            wialon_unit = await wialon_units_repository.get_unit_record(
                db, next_wialon_id
            )
            await asset_links_service.link(
                db,
                asset.id,
                "wialon",
                next_wialon_id,
                by,
                external_name=wialon_unit.name if wialon_unit is not None else None,
            )
    if "gtk_id" in changes:
        if next_gtk_id is None:
            if previous_gtk_id is not None:
                await asset_links_service.unlink(db, asset.id, "gtk")
        else:
            gtk_kind = await gtk_repository.gtk_kind(db, next_gtk_id)
            gtk_object = (
                await gtk_repository.get_locomotive(db, int(next_gtk_id))
                if gtk_kind == "locomotive"
                else await gtk_repository.get_carriage(db, int(next_gtk_id))
            )
            await asset_links_service.link(
                db,
                asset.id,
                "gtk",
                next_gtk_id,
                by,
                external_name=gtk_object.name if gtk_object is not None else None,
            )
    if previous_gtk_id != next_gtk_id:
        if previous_gtk_id is not None:
            previous_kind = await gtk_repository.gtk_kind(db, previous_gtk_id)
            if previous_kind == "locomotive":
                await gtk_repository.reset_locomotive_mileage_checkpoint(
                    db, int(previous_gtk_id)
                )
        if next_gtk_id is not None:
            next_kind = await gtk_repository.gtk_kind(db, next_gtk_id)
            if next_kind == "locomotive":
                await gtk_repository.reset_locomotive_mileage_checkpoint(
                    db, int(next_gtk_id)
                )
    if wialon_id_changed:
        linked_unit = (
            await wialon_units_repository.get_unit_record(
                db, changes.get("wialon_id")
            )
            if changes.get("wialon_id") is not None
            else None
        )
        await wialon_counters_repository.rebaseline(
            db,
            asset.id,
            cnm=linked_unit.cnm if linked_unit is not None else None,
            cneh=linked_unit.cneh if linked_unit is not None else None,
            at=(
                linked_unit.last_message_at
                if linked_unit is not None and linked_unit.last_message_at is not None
                else asset.updated_at
            ),
        )
    if mileage is not None:
        await _save_mileage_change(db, asset, mileage, "manual")
    await _commit(
        db,
        "Inventory number, accounting number, model, number, source ID, or section conflicts",
    )
    await db.refresh(asset)
    return asset_read(asset)


async def _validate_gtk_link(
    db: AsyncSession, gtk_id: str | None, asset_type: str
) -> None:
    if gtk_id is None:
        return
    gtk_kind = await gtk_repository.gtk_kind(db, gtk_id)
    if gtk_kind is None:
        raise HTTPException(status_code=422, detail="GTK record was not found")
    if gtk_kind == "locomotive" and asset_type not in {"locomotive", "diesel"}:
        raise HTTPException(
            status_code=422,
            detail="GTK locomotive can only be linked to a locomotive or diesel asset",
        )
    if gtk_kind == "carriage" and asset_type != "wagon":
        raise HTTPException(
            status_code=422,
            detail="GTK carriage can only be linked to a wagon asset",
        )


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


async def bulk_update_org_unit(
    db: AsyncSession,
    payload: FixedAssetBulkOrgUnitUpdate,
    *,
    by: UUID,
) -> int:
    if payload.org_unit_id is not None:
        section = await references_repository.get_non_archived_section(
            db, payload.org_unit_id
        )
        if section is None:
            raise HTTPException(
                status_code=422, detail="Organization unit is unavailable"
            )

    assets = await repository.get_assets_for_update(db, payload.asset_ids)
    if len(assets) != len(payload.asset_ids):
        raise _not_found()

    now = datetime.now(timezone.utc)
    updated = 0
    for asset in assets:
        previous_org_unit_id = asset.org_unit_id
        if previous_org_unit_id == payload.org_unit_id:
            continue
        field_changes_service.record_manual_changes(
            db,
            asset,
            old_values={"org_unit_id": previous_org_unit_id},
            new_values={"org_unit_id": payload.org_unit_id},
        )
        asset.org_unit_id = payload.org_unit_id
        asset.updated_at = now
        updated += 1

    await _commit(db, "Unable to update organizational unit")
    return updated


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


async def find_wialon_asset(
    db: AsyncSession, *, unit_id: str | None, unit_name: str | None
) -> FixedAsset | None:
    """Resolve only explicit Wialon links; names are for suggestions, not writes."""
    if not unit_id or not unit_id.strip():
        return None
    return await asset_links_service.find_asset(db, "wialon", unit_id.strip())


async def receive_wialon_update(
    db: AsyncSession,
    *,
    unit_id: str | None,
    unit_name: str | None,
    mileage: Decimal | None,
    speed: Decimal | None,
    online: bool = True,
    allow_zero_mileage: bool = False,
) -> dict[str, object]:
    asset = await find_wialon_asset(db, unit_id=unit_id, unit_name=unit_name)
    if asset is None:
        return {"found": False}

    now = datetime.now(timezone.utc)
    asset.wialon_last_sync = now
    asset.updated_at = now
    if speed is not None:
        asset.wialon_speed = speed
    asset.wialon_online = online
    if mileage is not None and (mileage > 0 or allow_zero_mileage):
        await _save_mileage_change(db, asset, mileage, "wialon")
    await _commit(db, "Could not save Wialon update")
    return {
        "found": True,
        "asset_id": str(asset.id),
        "name": asset.name,
        "mileage": str(asset.mileage),
        "wialon_online": online,
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
    if field_name == "mileage" and parsed < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mileage must not be negative",
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
