from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset


async def get_active(
    db: AsyncSession, asset_id: UUID
) -> list[AssetSourceLink]:
    result = await db.execute(
        select(AssetSourceLink)
        .where(
            AssetSourceLink.asset_id == asset_id,
            AssetSourceLink.status == "active",
        )
        .order_by(AssetSourceLink.source)
    )
    return list(result.scalars().all())


async def get_for_asset(
    db: AsyncSession, asset_id: UUID, *, include_ended: bool
) -> list[AssetSourceLink]:
    query = select(AssetSourceLink).where(AssetSourceLink.asset_id == asset_id)
    if not include_ended:
        query = query.where(AssetSourceLink.status == "active")
    result = await db.execute(
        query.order_by(AssetSourceLink.linked_at.desc(), AssetSourceLink.id.desc())
    )
    return list(result.scalars().all())


async def get_active_for_update(
    db: AsyncSession, asset_id: UUID, source: str
) -> AssetSourceLink | None:
    result = await db.execute(
        select(AssetSourceLink)
        .where(
            AssetSourceLink.asset_id == asset_id,
            AssetSourceLink.source == source,
            AssetSourceLink.status == "active",
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def find_active(
    db: AsyncSession, source: str, external_id: str
) -> tuple[AssetSourceLink, FixedAsset] | None:
    result = await db.execute(
        select(AssetSourceLink, FixedAsset)
        .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
        .where(
            AssetSourceLink.source == source,
            AssetSourceLink.external_id == external_id,
            AssetSourceLink.status == "active",
        )
    )
    return result.one_or_none()


async def add(db: AsyncSession, link: AssetSourceLink) -> None:
    db.add(link)
    await db.flush()


async def end(link: AssetSourceLink, *, at: datetime | None = None) -> None:
    link.status = "ended"
    link.unlinked_at = at or datetime.now(timezone.utc)
