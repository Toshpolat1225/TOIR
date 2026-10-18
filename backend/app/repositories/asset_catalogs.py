from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.localization import (
    FixedAssetStatus, FixedAssetStatusTranslation,
    FixedAssetType, FixedAssetTypeTranslation,
)


def _models(kind: str):
    if kind == "types":
        return FixedAssetType, FixedAssetTypeTranslation, "type_code", FixedAsset.asset_type
    return FixedAssetStatus, FixedAssetStatusTranslation, "status_code", FixedAsset.status


async def list_catalog(db: AsyncSession, *, kind: str, locale: str, q: str | None,
                       is_active: bool | None, limit: int, offset: int):
    model, translation, fk, asset_field = _models(kind)
    query = (select(model, translation).outerjoin(
        translation, getattr(translation, fk) == model.code
    ).where(translation.locale == locale))
    count = select(func.count(func.distinct(model.code))).select_from(model).join(
        translation, getattr(translation, fk) == model.code
    ).where(translation.locale == locale)
    if is_active is not None:
        query = query.where(model.is_active == is_active)
        count = count.where(model.is_active == is_active)
    if q:
        pattern = f"%{q.strip()}%"
        predicate = or_(model.code.ilike(pattern), translation.name.ilike(pattern))
        query, count = query.where(predicate), count.where(predicate)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(query.order_by(model.code).limit(limit).offset(offset))).all()
    items = []
    for row, localized in rows:
        all_names_result = await db.execute(select(translation.locale, translation.name).where(getattr(translation, fk) == row.code))
        all_names = dict(all_names_result.all())
        used = (await db.execute(select(func.count()).select_from(FixedAsset).where(asset_field == row.code))).scalar_one()
        items.append({"code": row.code, "name": localized.name, "names": all_names,
                      "is_active": row.is_active, "usage_count": used,
                      "behavior": getattr(row, "behavior", None), "color": row.color})
    return items, total


async def get_catalog(db: AsyncSession, *, kind: str, code: str):
    model, translation, fk, _ = _models(kind)
    row = await db.get(model, code)
    if row is None:
        return None
    names = dict((await db.execute(select(translation.locale, translation.name).where(getattr(translation, fk) == code))).all())
    return row, names


async def name_exists(db: AsyncSession, *, kind: str, code: str, names: dict[str, str]) -> bool:
    _, translation, fk, _ = _models(kind)
    for locale, name in names.items():
        query = select(translation.id).where(
            translation.locale == locale,
            func.lower(translation.name) == name.lower(),
            getattr(translation, fk) != code,
        ).limit(1)
        if (await db.execute(query)).first():
            return True
    return False


async def usage_count(db: AsyncSession, *, kind: str, code: str) -> int:
    _, _, _, asset_field = _models(kind)
    return (await db.execute(select(func.count()).select_from(FixedAsset).where(asset_field == code))).scalar_one()
