from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.localization import (
    FixedAssetStatus, FixedAssetStatusTranslation,
    FixedAssetType, FixedAssetTypeTranslation,
)
from app.repositories import asset_catalogs as repository
from app.schemas.asset_catalogs import AssetCatalogUpdate, AssetCatalogWrite


def _models(kind: str):
    if kind == "types":
        return FixedAssetType, FixedAssetTypeTranslation, "type_code"
    return FixedAssetStatus, FixedAssetStatusTranslation, "status_code"


def _check_kind(kind: str):
    if kind not in ("types", "statuses"):
        raise HTTPException(404, "Asset catalog not found")


async def list_items(db: AsyncSession, *, kind: str, locale: str, q: str | None,
                     is_active: bool | None, limit: int, offset: int):
    _check_kind(kind)
    items, total = await repository.list_catalog(db, kind=kind, locale=locale, q=q,
                                                  is_active=is_active, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def create(db: AsyncSession, *, kind: str, payload: AssetCatalogWrite):
    _check_kind(kind)
    model, translation, fk = _models(kind)
    if kind == "statuses" and payload.behavior is None:
        raise HTTPException(422, "Status behavior is required")
    if await repository.get_catalog(db, kind=kind, code=payload.code):
        raise HTTPException(409, "Catalog code already exists")
    if await repository.name_exists(db, kind=kind, code=payload.code, names=payload.names):
        raise HTTPException(409, "A catalog name already exists in one of the locales")
    row = model(code=payload.code, is_active=payload.is_active, color=payload.color)
    if kind == "statuses":
        row.behavior = payload.behavior
    db.add(row)
    for locale, name in payload.names.items():
        db.add(translation(**{fk: payload.code, "locale": locale, "name": name}))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Catalog entry conflicts with an existing value") from exc
    return await detail(db, kind=kind, code=payload.code)


async def update(db: AsyncSession, *, kind: str, code: str, payload: AssetCatalogUpdate):
    _check_kind(kind)
    model, translation, fk = _models(kind)
    found = await repository.get_catalog(db, kind=kind, code=code)
    if found is None:
        raise HTTPException(404, "Catalog entry not found")
    if kind == "statuses" and payload.behavior is None:
        raise HTTPException(422, "Status behavior is required")
    if await repository.name_exists(db, kind=kind, code=code, names=payload.names):
        raise HTTPException(409, "A catalog name already exists in one of the locales")
    row, _ = found
    if kind == "statuses" and row.behavior != payload.behavior:
        used = await repository.usage_count(db, kind=kind, code=code)
        if used:
            raise HTTPException(409, f"Status is used by {used} fixed assets; its behavior cannot be changed")
    row.is_active, row.color = payload.is_active, payload.color
    if kind == "statuses":
        row.behavior = payload.behavior
    existing = (await db.execute(select(translation).where(getattr(translation, fk) == code))).scalars().all()
    by_locale = {entry.locale: entry for entry in existing}
    for locale, name in payload.names.items():
        if locale in by_locale:
            by_locale[locale].name = name
        else:
            db.add(translation(**{fk: code, "locale": locale, "name": name}))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Catalog entry conflicts with an existing value") from exc
    return await detail(db, kind=kind, code=code)


async def detail(db: AsyncSession, *, kind: str, code: str):
    found = await repository.get_catalog(db, kind=kind, code=code)
    if found is None:
        raise HTTPException(404, "Catalog entry not found")
    row, names = found
    return {"code": code, "names": names, "is_active": row.is_active,
            "usage_count": await repository.usage_count(db, kind=kind, code=code),
            "behavior": getattr(row, "behavior", None), "color": row.color}


async def delete(db: AsyncSession, *, kind: str, code: str):
    _check_kind(kind)
    model, _, _ = _models(kind)
    row = await db.get(model, code)
    if row is None:
        raise HTTPException(404, "Catalog entry not found")
    used = await repository.usage_count(db, kind=kind, code=code)
    if used:
        raise HTTPException(409, f"Entry is used by {used} fixed assets; deactivate it instead")
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Entry is referenced by existing data") from exc
