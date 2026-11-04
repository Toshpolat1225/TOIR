import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.asset_field_policy import ASSET_FIELD_POLICY, PASSPORT_FIELD_NAMES
from app.models.asset_field_changes import AssetFieldChange
from app.models.assets import FixedAsset
from app.repositories import asset_field_changes as repository
from app.repositories import asset_models as asset_models_repository
from app.services.asset_passport import normalize_token

logger = logging.getLogger(__name__)


def _json_value(value: Any) -> Any:
    if isinstance(value, (UUID, date, datetime, Decimal)):
        return str(value) if not isinstance(value, (date, datetime)) else value.isoformat()
    return value


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return normalize_token(left) == normalize_token(right)
    return _json_value(left) == _json_value(right)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def record_changes(
    db: AsyncSession,
    asset: FixedAsset,
    *,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    source: str,
    kind: str,
) -> None:
    for field in PASSPORT_FIELD_NAMES.intersection(new_values):
        old_value = old_values.get(field)
        new_value = new_values[field]
        if _json_value(old_value) == _json_value(new_value):
            continue
        db.add(
            AssetFieldChange(
                asset_id=asset.id,
                field=field,
                old_value=_json_value(old_value),
                new_value=_json_value(new_value),
                source=source,
                kind=kind,
                status="applied",
            )
        )


def record_manual_changes(
    db: AsyncSession,
    asset: FixedAsset,
    *,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
) -> None:
    record_changes(
        db,
        asset,
        old_values=old_values,
        new_values=new_values,
        source="toir",
        kind="manual",
    )


async def propose_field(
    db: AsyncSession,
    *,
    asset_id: UUID,
    field: str,
    value: Any,
    source: str,
) -> str:
    policy = ASSET_FIELD_POLICY.get(field)
    if policy is None or policy.mode is None:
        raise ValueError(f"Field {field!r} cannot receive proposals")
    if source != policy.source:
        logger.warning(
            "Rejected asset field proposal from non-owning source for field %s",
            field,
        )
        return "rejected"
    if policy.mode == "manual_only":
        logger.warning("Rejected proposal for manual-only asset field %s", field)
        return "rejected"
    if _is_empty(value):
        return "ignored"

    asset = await repository.get_asset_for_update(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    if field in {"number", "model_id"} and asset.asset_type != "wagon":
        logger.warning(
            "Rejected GTK passport proposal for non-wagon asset %s",
            asset.id,
        )
        return "rejected"
    if field == "model_id":
        try:
            model_id = UUID(str(value))
        except (TypeError, ValueError):
            logger.warning("Rejected invalid GTK model proposal for asset %s", asset.id)
            return "rejected"
        model = await asset_models_repository.get_model(db, model_id)
        if model is None or model.asset_type != asset.asset_type:
            logger.warning(
                "Rejected asset model proposal with incompatible asset type for %s",
                asset.id,
            )
            return "rejected"
    current = getattr(asset, field)
    if not _is_empty(current) and _same_value(current, value):
        return "unchanged"
    if policy.mode == "auto_fill_if_empty" and _is_empty(current):
        setattr(asset, field, value)
        if field == "number":
            asset.number_normalized = normalize_token(value)
        asset.updated_at = datetime.now(timezone.utc)
        await repository.add(
            db,
            AssetFieldChange(
                asset_id=asset.id,
                field=field,
                old_value=_json_value(current),
                new_value=_json_value(value),
                source=source,
                kind="auto_fill",
                status="applied",
            ),
        )
        return "applied"

    pending = await repository.list_pending_for_field(db, asset.id, field)
    if any(_same_value(change.new_value, value) for change in pending):
        return "duplicate"
    await repository.add(
        db,
        AssetFieldChange(
            asset_id=asset.id,
            field=field,
            old_value=_json_value(current),
            new_value=_json_value(value),
            source=source,
            kind="conflict",
            status="pending",
        ),
    )
    return "pending"


async def list_conflicts(
    db: AsyncSession, *, status_filter: str, limit: int, offset: int
):
    return await repository.list_changes(
        db, status=status_filter, limit=limit, offset=offset
    )


def _coerce_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in {"model_id", "org_unit_id"}:
        return UUID(str(value))
    if field in {"commissioned_at", "year_built"}:
        return date.fromisoformat(value) if field == "commissioned_at" else int(value)
    if field in {"inv_number", "accounting_inv_number", "serial_number", "number", "asset_type"}:
        return str(value)
    raise ValueError(f"Field {field!r} cannot be resolved")


async def _resolve_conflict(
    db: AsyncSession, change_id: int, user_id: UUID, *, accept: bool
) -> AssetFieldChange:
    change = await repository.get_change_for_update(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Asset conflict not found")
    if change.status != "pending":
        raise HTTPException(status_code=409, detail="Asset conflict is no longer pending")

    if accept:
        policy = ASSET_FIELD_POLICY.get(change.field)
        if (
            policy is None
            or policy.mode == "manual_only"
            or policy.source != change.source
            or change.kind != "conflict"
        ):
            raise HTTPException(status_code=409, detail="Asset conflict cannot be applied")
        asset = await repository.get_asset_for_update(db, change.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Fixed asset not found")
        if (
            change.field in {"number", "model_id"}
            and asset.asset_type != "wagon"
        ):
            raise HTTPException(
                status_code=409, detail="GTK passport change requires a wagon asset"
            )
        current = getattr(asset, change.field)
        if not _same_value(current, change.old_value):
            raise HTTPException(
                status_code=409,
                detail="Fixed asset field changed after the proposal",
            )
        try:
            value = _coerce_value(change.field, change.new_value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=409, detail="Proposed field value is invalid"
            ) from exc
        if change.field == "model_id" and value is not None:
            model = await asset_models_repository.get_model(db, value)
            if model is None or model.asset_type != asset.asset_type:
                raise HTTPException(
                    status_code=409, detail="Proposed model does not match asset type"
                )
        setattr(asset, change.field, value)
        if change.field == "number":
            asset.number_normalized = normalize_token(value) if value else None
        asset.updated_at = datetime.now(timezone.utc)
        change.status = "accepted"
    else:
        change.status = "rejected"
    change.resolved_by = user_id
    change.resolved_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset field change conflicts with existing data",
        ) from exc
    await db.refresh(change)
    return change


async def accept_conflict(
    db: AsyncSession, change_id: int, user_id: UUID
) -> AssetFieldChange:
    return await _resolve_conflict(db, change_id, user_id, accept=True)


async def reject_conflict(
    db: AsyncSession, change_id: int, user_id: UUID
) -> AssetFieldChange:
    return await _resolve_conflict(db, change_id, user_id, accept=False)
