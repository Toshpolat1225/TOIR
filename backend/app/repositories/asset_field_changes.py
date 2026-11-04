from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_field_changes import AssetFieldChange
from app.models.assets import FixedAsset


async def add(db: AsyncSession, change: AssetFieldChange) -> None:
    db.add(change)
    await db.flush()


async def list_changes(
    db: AsyncSession, *, status: str, limit: int, offset: int
) -> tuple[list[AssetFieldChange], int]:
    filters = (AssetFieldChange.status == status,)
    total = (
        await db.execute(
            select(func.count()).select_from(AssetFieldChange).where(*filters)
        )
    ).scalar_one()
    result = await db.execute(
        select(AssetFieldChange)
        .where(*filters)
        .order_by(AssetFieldChange.created_at.desc(), AssetFieldChange.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def get_change_for_update(
    db: AsyncSession, change_id: int
) -> AssetFieldChange | None:
    result = await db.execute(
        select(AssetFieldChange)
        .where(AssetFieldChange.id == change_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_asset_for_update(
    db: AsyncSession, asset_id: UUID
) -> FixedAsset | None:
    result = await db.execute(
        select(FixedAsset)
        .where(FixedAsset.id == asset_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def list_pending_for_field(
    db: AsyncSession, asset_id: UUID, field: str
) -> list[AssetFieldChange]:
    result = await db.execute(
        select(AssetFieldChange).where(
            AssetFieldChange.asset_id == asset_id,
            AssetFieldChange.field == field,
            AssetFieldChange.status == "pending",
        )
    )
    return list(result.scalars().all())
