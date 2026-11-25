"""Migration journal service: list, correct and roll back values that an import wrote into assets.

The asset column stays the source of truth. A change is allowed only while the asset still holds exactly the value the
migration wrote; if someone changed it elsewhere in the meantime the request is refused (409) and nothing is overwritten.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.timeutil import today_local
from app.models.asset_models import AssetModel  # noqa: F401  (keeps the mapper registry complete)
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.data_migration import DataMigrationBatch, DataMigrationItem
from app.models.identity import User
from app.models.organization import Section
from app.services.audit_log import set_audit_actor

MIN_DATE = date(1990, 1, 1)


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Date must be YYYY-MM-DD") from exc
    if parsed > today_local():
        raise HTTPException(status_code=422, detail="Date cannot be in the future")
    if parsed < MIN_DATE:
        raise HTTPException(status_code=422, detail="Date is too old")
    return parsed


class FieldSpec:
    def __init__(self, column: InstrumentedAttribute, attribute: str, parse: Callable[[str], Any]) -> None:
        self.column = column
        self.attribute = attribute
        self.parse = parse


# only fields that are listed here can ever be written by this journal
FIELD_SPECS: dict[str, FieldSpec] = {
    "last_maint_date": FieldSpec(FixedAsset.last_maint_date, "last_maint_date", _parse_date),
}
ITEM_SORT_FIELDS = {"inv_number", "serial_number", "section_name", "old_value", "new_value", "raw_value", "status", "updated_at"}


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _spec(field: str) -> FieldSpec:
    spec = FIELD_SPECS.get(field)
    if spec is None:
        raise HTTPException(status_code=422, detail=f"Unsupported migration field: {field}")
    return spec


async def list_batches(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                DataMigrationBatch,
                func.count(DataMigrationItem.id),
                func.count(DataMigrationItem.id).filter(DataMigrationItem.status == "applied"),
                func.count(DataMigrationItem.id).filter(DataMigrationItem.status == "reverted"),
            )
            .outerjoin(DataMigrationItem, DataMigrationItem.batch_id == DataMigrationBatch.id)
            .group_by(DataMigrationBatch.id)
            .order_by(DataMigrationBatch.created_at.desc())
        )
    ).all()
    return [
        {
            "id": b.id, "name": b.name, "source_file": b.source_file, "field": b.field, "description": b.description,
            "created_at": b.created_at, "total": total, "applied": applied, "reverted": reverted,
        }
        for b, total, applied, reverted in rows
    ]


async def list_items(
    db: AsyncSession, batch_id: UUID, *, q: str | None = None, status_filter: str | None = None,
    sort_by: str = "inv_number", sort_dir: str = "asc", limit: int = 50, offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    batch = await db.get(DataMigrationBatch, batch_id)
    if batch is None:
        raise _not_found()
    if sort_by not in ITEM_SORT_FIELDS:
        raise HTTPException(status_code=422, detail="sort_by must be one of: " + ", ".join(sorted(ITEM_SORT_FIELDS)))
    spec = _spec(batch.field)
    sort_columns: dict[str, Any] = {
        "inv_number": FixedAsset.inv_number, "serial_number": FixedAsset.serial_number, "section_name": Section.name,
        "old_value": DataMigrationItem.old_value, "new_value": DataMigrationItem.new_value, "raw_value": DataMigrationItem.raw_value,
        "status": DataMigrationItem.status, "updated_at": DataMigrationItem.updated_at,
    }
    base = (
        select(DataMigrationItem, FixedAsset, Section.name, fixed_asset_name_expression())
        .join(FixedAsset, FixedAsset.id == DataMigrationItem.asset_id)
        .outerjoin(Section, Section.id == FixedAsset.section_id)
        .where(DataMigrationItem.batch_id == batch_id)
    )
    if status_filter in ("applied", "reverted"):
        base = base.where(DataMigrationItem.status == status_filter)
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(or_(
            FixedAsset.inv_number.ilike(like), FixedAsset.serial_number.ilike(like),
            DataMigrationItem.raw_value.ilike(like), cast(DataMigrationItem.new_value, String).ilike(like),
        ))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    order = sort_columns[sort_by]
    order = order.desc() if sort_dir == "desc" else order.asc()
    rows = (await db.execute(base.order_by(order.nulls_last(), DataMigrationItem.id).limit(limit).offset(offset))).all()
    items = [
        {
            "id": item.id, "batch_id": item.batch_id, "asset_id": item.asset_id, "inv_number": asset.inv_number,
            "serial_number": asset.serial_number, "asset_name": name, "asset_type": asset.asset_type, "section_name": section_name,
            "old_value": item.old_value, "new_value": item.new_value, "current_value": _text(getattr(asset, spec.attribute)),
            "raw_value": item.raw_value, "status": item.status, "updated_at": item.updated_at,
        }
        for item, asset, section_name, name in rows
    ]
    return items, total


async def _load_locked(db: AsyncSession, item_id: int) -> tuple[DataMigrationItem, DataMigrationBatch, FixedAsset]:
    item = (await db.execute(select(DataMigrationItem).where(DataMigrationItem.id == item_id).with_for_update())).scalar_one_or_none()
    if item is None:
        raise _not_found()
    batch = await db.get(DataMigrationBatch, item.batch_id)
    asset = (await db.execute(select(FixedAsset).where(FixedAsset.id == item.asset_id).with_for_update())).scalar_one_or_none()
    if batch is None or asset is None:
        raise _not_found()
    return item, batch, asset


def _actor(db: AsyncSession, user: User, route: str) -> None:
    set_audit_actor(db, actor_id=user.id, actor_name=user.full_name, actor_type="user", route=route)


def _ensure_unchanged(item: DataMigrationItem, asset: FixedAsset, spec: FieldSpec) -> None:
    if item.status != "applied":
        raise HTTPException(status_code=409, detail="This value was already rolled back")
    if _text(getattr(asset, spec.attribute)) != item.new_value:
        raise HTTPException(status_code=409, detail="The value was changed elsewhere since the migration; nothing was overwritten")


async def update_item(db: AsyncSession, item_id: int, new_value: str, user: User) -> dict[str, Any]:
    item, batch, asset = await _load_locked(db, item_id)
    spec = _spec(batch.field)
    _ensure_unchanged(item, asset, spec)
    parsed = spec.parse(new_value)
    _actor(db, user, f"/api/v1/data-migrations/items/{item_id}")
    setattr(asset, spec.attribute, parsed)
    item.new_value = _text(parsed)
    item.updated_by = user.id
    item.updated_at = func.now()
    await db.commit()
    rows, _ = await list_items(db, batch.id, q=asset.inv_number, limit=200)
    return next(r for r in rows if r["id"] == item_id)


async def revert_item(db: AsyncSession, item_id: int, user: User) -> None:
    item, batch, asset = await _load_locked(db, item_id)
    spec = _spec(batch.field)
    _ensure_unchanged(item, asset, spec)
    _actor(db, user, f"/api/v1/data-migrations/items/{item_id}")
    setattr(asset, spec.attribute, spec.parse(item.old_value) if item.old_value is not None else None)
    item.status = "reverted"
    item.updated_by = user.id
    item.updated_at = func.now()
    await db.commit()


async def revert_batch(db: AsyncSession, batch_id: UUID, user: User) -> dict[str, int]:
    batch = await db.get(DataMigrationBatch, batch_id)
    if batch is None:
        raise _not_found()
    spec = _spec(batch.field)
    _actor(db, user, f"/api/v1/data-migrations/{batch_id}/revert")
    items = (
        await db.execute(select(DataMigrationItem).where(DataMigrationItem.batch_id == batch_id).order_by(DataMigrationItem.id).with_for_update())
    ).scalars().all()
    asset_ids = [i.asset_id for i in items]
    assets = {
        a.id: a
        for a in (await db.execute(select(FixedAsset).where(FixedAsset.id.in_(asset_ids)).with_for_update())).scalars().all()
    } if asset_ids else {}
    reverted = skipped = already = 0
    for item in items:
        if item.status != "applied":
            already += 1
            continue
        asset = assets.get(item.asset_id)
        if asset is None or _text(getattr(asset, spec.attribute)) != item.new_value:
            skipped += 1  # changed elsewhere: never overwritten
            continue
        setattr(asset, spec.attribute, spec.parse(item.old_value) if item.old_value is not None else None)
        item.status = "reverted"
        item.updated_by = user.id
        item.updated_at = func.now()
        reverted += 1
    await db.commit()
    return {"reverted": reverted, "skipped_changed_elsewhere": skipped, "already_reverted": already}
