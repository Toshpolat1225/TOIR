from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset, MileageHistory
from app.models.work_orders import WorkOrder

ASSET_SORT_FIELDS = frozenset(
    {
        "inv_number",
        "name",
        "asset_type",
        "series",
        "depot",
        "section_id",
        "status",
        "comm_date",
        "year_built",
        "mileage",
        "last_maint_date",
        "next_maint_date",
        "initial_cost",
        "owner",
        "wialon_last_sync",
        "created_at",
        "updated_at",
    }
)


async def list_assets(
    db: AsyncSession,
    *,
    asset_type: str | None,
    status: str | None,
    section_id: UUID | None,
    depot: str | None,
    q: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[FixedAsset], int]:
    if sort_by not in ASSET_SORT_FIELDS:
        raise ValueError("Unsupported sort field")
    filters: list[Any] = []
    if asset_type is not None:
        filters.append(FixedAsset.asset_type == asset_type)
    if status is not None:
        filters.append(FixedAsset.status == status)
    if section_id is not None:
        filters.append(FixedAsset.section_id == section_id)
    if depot is not None:
        filters.append(FixedAsset.depot == depot)
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                FixedAsset.name.ilike(pattern),
                FixedAsset.inv_number.ilike(pattern),
                FixedAsset.series.ilike(pattern),
            )
        )

    count_query = select(func.count()).select_from(FixedAsset)
    rows_query: Select[tuple[FixedAsset]] = select(FixedAsset)
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)
    total = (await db.execute(count_query)).scalar_one()
    sort_column = getattr(FixedAsset, sort_by)
    order_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    result = await db.execute(
        rows_query.order_by(order_column, FixedAsset.id.asc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total


async def get_asset(
    db: AsyncSession, asset_id: UUID, *, master_section_id: UUID | None = None
) -> FixedAsset | None:
    query = select(FixedAsset).where(FixedAsset.id == asset_id)
    if master_section_id is not None:
        query = query.where(FixedAsset.section_id == master_section_id)
    return (await db.execute(query)).scalar_one_or_none()


async def asset_stats(
    db: AsyncSession, *, master_section_id: UUID | None
) -> tuple[int, dict[str, int], dict[str, int], list[str]]:
    filters = (
        [FixedAsset.section_id == master_section_id]
        if master_section_id is not None
        else []
    )
    total = (
        await db.execute(select(func.count()).select_from(FixedAsset).where(*filters))
    ).scalar_one()
    type_result = await db.execute(
        select(FixedAsset.asset_type, func.count(FixedAsset.id))
        .where(*filters)
        .group_by(FixedAsset.asset_type)
    )
    status_result = await db.execute(
        select(FixedAsset.status, func.count(FixedAsset.id))
        .where(*filters)
        .group_by(FixedAsset.status)
    )
    depot_result = await db.execute(
        select(FixedAsset.depot)
        .where(*filters, FixedAsset.depot.is_not(None))
        .distinct()
        .order_by(FixedAsset.depot.asc())
    )
    return (
        total,
        dict(type_result.all()),
        dict(status_result.all()),
        list(depot_result.scalars().all()),
    )


async def add_asset(db: AsyncSession, asset: FixedAsset) -> None:
    db.add(asset)


async def add_mileage_history(
    db: AsyncSession, asset_id: UUID, mileage: Decimal, source: str
) -> MileageHistory:
    history = MileageHistory(
        asset_id=asset_id,
        mileage=mileage,
        source=source,
    )
    db.add(history)
    return history


async def list_mileage_history(
    db: AsyncSession,
    asset_id: UUID,
    *,
    since: datetime,
    limit: int,
) -> tuple[list[MileageHistory], int]:
    filters: Sequence[Any] = (
        MileageHistory.asset_id == asset_id,
        MileageHistory.recorded_at >= since,
    )
    total = (
        await db.execute(
            select(func.count()).select_from(MileageHistory).where(*filters)
        )
    ).scalar_one()
    result = await db.execute(
        select(MileageHistory)
        .where(*filters)
        .order_by(MileageHistory.recorded_at.desc(), MileageHistory.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def find_asset_by_wialon_id(
    db: AsyncSession, wialon_id: str
) -> FixedAsset | None:
    result = await db.execute(
        select(FixedAsset).where(
            FixedAsset.wialon_id == wialon_id,
            FixedAsset.asset_type.in_(("locomotive", "diesel")),
        )
    )
    return result.scalar_one_or_none()


async def find_assets_by_name(db: AsyncSession, name: str) -> list[FixedAsset]:
    result = await db.execute(
        select(FixedAsset)
        .where(
            func.lower(FixedAsset.name) == name.strip().lower(),
            FixedAsset.asset_type.in_(("locomotive", "diesel")),
        )
        .order_by(FixedAsset.id.asc())
    )
    return list(result.scalars().all())


async def list_wialon_assets(db: AsyncSession) -> list[FixedAsset]:
    result = await db.execute(
        select(FixedAsset)
        .where(FixedAsset.asset_type.in_(("locomotive", "diesel")))
        .order_by(FixedAsset.id.asc())
    )
    return list(result.scalars().all())


async def count_asset_references(
    db: AsyncSession, asset_id: UUID
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.fixed_asset_id == asset_id)
    )
    return result.scalar_one()
