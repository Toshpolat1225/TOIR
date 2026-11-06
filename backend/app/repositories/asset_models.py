from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_models import AssetModel


async def get_model(db: AsyncSession, model_id: UUID) -> AssetModel | None:
    return (
        await db.execute(select(AssetModel).where(AssetModel.id == model_id))
    ).scalar_one_or_none()


async def get_by_normalized_name(
    db: AsyncSession, name_normalized: str
) -> AssetModel | None:
    return (
        await db.execute(
            select(AssetModel).where(AssetModel.name_normalized == name_normalized)
        )
    ).scalar_one_or_none()


async def add_if_missing(
    db: AsyncSession,
    *,
    name: str,
    name_normalized: str,
    asset_type: str,
    series: str | None,
) -> AssetModel:
    inserted_id = (
        await db.execute(
            insert(AssetModel)
            .values(
                name=name,
                name_normalized=name_normalized,
                asset_type=asset_type,
                series=series,
            )
            .on_conflict_do_nothing(
                index_elements=[AssetModel.name_normalized]
            )
            .returning(AssetModel.id)
        )
    ).scalar_one_or_none()
    if inserted_id is not None:
        return await get_model(db, inserted_id)
    existing = await get_by_normalized_name(db, name_normalized)
    if existing is None:
        raise RuntimeError("Asset model insert was not visible after conflict")
    return existing


async def delete_unused_models(db: AsyncSession, model_ids: list[UUID]) -> None:
    if not model_ids:
        return
    from app.models.assets import FixedAsset

    await db.execute(
        delete(AssetModel).where(
            AssetModel.id.in_(model_ids),
            ~select(FixedAsset.id)
            .where(FixedAsset.model_id == AssetModel.id)
            .exists(),
        )
    )


async def list_report_data(db: AsyncSession):
    from app.models.assets import FixedAsset
    from app.models.organization import Section

    assets = (
        await db.execute(select(FixedAsset).order_by(FixedAsset.id.asc()))
    ).scalars().all()
    sections = (
        await db.execute(
            select(Section.id, Section.name).where(Section.is_archived.is_(False))
        )
    ).all()
    return list(assets), list(sections)


async def list_models(
    db: AsyncSession,
    *,
    asset_type: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[AssetModel], int]:
    query = select(AssetModel)
    count_query = select(func.count()).select_from(AssetModel)
    if asset_type is not None:
        query = query.where(AssetModel.asset_type == asset_type)
        count_query = count_query.where(AssetModel.asset_type == asset_type)
    if q:
        search = f"%{q.strip()}%"
        query = query.where(AssetModel.name.ilike(search))
        count_query = count_query.where(AssetModel.name.ilike(search))

    total = int((await db.execute(count_query)).scalar_one())
    items = list(
        (
            await db.execute(
                query.order_by(AssetModel.name.asc(), AssetModel.id.asc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return items, total
