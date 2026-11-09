from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_models import AssetModel
from app.models.assets import (
    FixedAsset,
    MileageHistory,
    fixed_asset_name_expression,
)
from app.models.asset_source_links import AssetSourceLink
from app.models.localization import (
    FixedAssetStatus,
    FixedAssetType,
    FixedAssetTypeTranslation,
)
from app.models.organization import Section
from app.models.work_orders import WorkOrder

ASSET_SORT_FIELDS = frozenset(
    {
        "inv_number",
        "name",
        "asset_type",
        "series",
        "depot",
        "number",
        "serial_number",
        "model_id",
        "accounting_inv_number",
        "org_unit_id",
        "commissioned_at",
        "decommissioned_at",
        "section_id",
        "status",
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


def _asset_filters(
    *, asset_type: str | None, status: str | None, status_behavior: str | None,
    section_id: UUID | None, depot: str | None, q: str | None,
    omit: frozenset[str] = frozenset(),
) -> list[Any]:
    filters: list[Any] = []
    if section_id is not None and "section_id" not in omit:
        filters.append(FixedAsset.section_id == section_id)
    if asset_type is not None and "asset_type" not in omit:
        filters.append(FixedAsset.asset_type == asset_type)
    if status is not None and "status" not in omit:
        filters.append(FixedAsset.status == status)
    if status_behavior is not None and "status_behavior" not in omit:
        filters.append(FixedAsset.status.in_(
            select(FixedAssetStatus.code).where(FixedAssetStatus.behavior == status_behavior)
        ))
    if depot is not None and "depot" not in omit:
        filters.append(Section.name == depot)
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                fixed_asset_name_expression().ilike(pattern),
                FixedAsset.inv_number.ilike(pattern),
                FixedAsset.serial_number.ilike(pattern),
                AssetModel.series.ilike(pattern),
            )
        )
    return filters


async def active_catalog_value_exists(db: AsyncSession, *, kind: str, code: str) -> bool:
    model = FixedAssetType if kind == "types" else FixedAssetStatus
    return (await db.execute(select(model.code).where(model.code == code, model.is_active.is_(True)))).scalar_one_or_none() is not None


async def list_assets(
    db: AsyncSession,
    *,
    asset_type: str | None,
    status: str | None,
    status_behavior: str | None,
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
    filters = _asset_filters(asset_type=asset_type, status=status, status_behavior=status_behavior,
                             section_id=section_id, depot=depot, q=q)

    asset_source = (
        FixedAsset.__table__
        .outerjoin(Section.__table__, FixedAsset.section_id == Section.id)
        .outerjoin(AssetModel.__table__, FixedAsset.model_id == AssetModel.id)
        .outerjoin(
            FixedAssetTypeTranslation.__table__,
            (FixedAssetTypeTranslation.type_code == FixedAsset.asset_type)
            & (FixedAssetTypeTranslation.locale == "ru"),
        )
    )
    count_query = select(func.count()).select_from(asset_source)
    rows_query: Select[tuple[FixedAsset]] = select(FixedAsset).select_from(asset_source)
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)
    total = (await db.execute(count_query)).scalar_one()
    sort_column = {
        "name": fixed_asset_name_expression(),
        "series": AssetModel.series,
        "depot": Section.name,
        "number": FixedAsset.serial_number,
        "org_unit_id": FixedAsset.section_id,
        **{
            field: getattr(FixedAsset, field)
            for field in ASSET_SORT_FIELDS
            if field
            not in {
                "name",
                "series",
                "depot",
                "number",
                "org_unit_id",
            }
        },
    }[sort_by]
    order_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    result = await db.execute(
        rows_query.order_by(order_column, FixedAsset.id.asc()).limit(limit).offset(offset)
    )
    assets = list(result.scalars().all())
    await enrich_asset_display_data(db, assets)
    return assets, total


async def get_asset(
    db: AsyncSession, asset_id: UUID, *, master_section_id: UUID | None = None
) -> FixedAsset | None:
    query = select(FixedAsset).where(FixedAsset.id == asset_id)
    if master_section_id is not None:
        query = query.where(FixedAsset.section_id == master_section_id)
    asset = (await db.execute(query)).scalar_one_or_none()
    if asset is not None:
        await enrich_asset_display_data(db, [asset])
    return asset


async def get_asset_for_update(
    db: AsyncSession, asset_id: UUID, *, master_section_id: UUID | None = None
) -> FixedAsset | None:
    query = select(FixedAsset).where(FixedAsset.id == asset_id)
    if master_section_id is not None:
        query = query.where(FixedAsset.section_id == master_section_id)
    asset = (await db.execute(query.with_for_update())).scalar_one_or_none()
    if asset is not None:
        await enrich_asset_display_data(db, [asset])
    return asset


async def get_assets_for_update(
    db: AsyncSession, asset_ids: Sequence[UUID]
) -> list[FixedAsset]:
    result = await db.execute(
        select(FixedAsset)
        .where(FixedAsset.id.in_(asset_ids))
        .order_by(FixedAsset.id.asc())
        .with_for_update()
    )
    assets = list(result.scalars().all())
    await enrich_asset_display_data(db, assets)
    return assets


async def enrich_asset_display_data(
    db: AsyncSession, assets: Sequence[FixedAsset]
) -> None:
    asset_ids = [asset.id for asset in assets]
    if not asset_ids:
        return
    result = await db.execute(
        select(
            FixedAsset.id,
            FixedAssetTypeTranslation.name,
            AssetModel.series,
            Section.name,
        )
        .outerjoin(
            FixedAssetTypeTranslation,
            (FixedAssetTypeTranslation.type_code == FixedAsset.asset_type)
            & (FixedAssetTypeTranslation.locale == "ru"),
        )
        .outerjoin(AssetModel, AssetModel.id == FixedAsset.model_id)
        .outerjoin(Section, Section.id == FixedAsset.section_id)
        .where(FixedAsset.id.in_(asset_ids))
    )
    display_data = {
        asset_id: (type_name, series, section_name)
        for asset_id, type_name, series, section_name in result.all()
    }
    for asset in assets:
        type_name, series, section_name = display_data[asset.id]
        asset._asset_type_name = type_name
        asset.series = series
        asset.depot = section_name


async def list_asset_names(db: AsyncSession) -> list[tuple[UUID, str]]:
    result = await db.execute(
        select(FixedAsset.id, fixed_asset_name_expression()).order_by(FixedAsset.id.asc())
    )
    return list(result.all())


async def count_fixed_assets(db: AsyncSession) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(FixedAsset)
            )
        ).scalar_one()
    )


async def list_active_sections(db: AsyncSession):
    from app.models.organization import Section

    result = await db.execute(
        select(Section)
        .where(Section.is_archived.is_(False), Section.is_active.is_(True))
        .order_by(Section.name.asc(), Section.id.asc())
    )
    return list(result.scalars().all())


async def find_inventory_records(
    db: AsyncSession, *, inventory_numbers: Sequence[str], accounting_numbers: Sequence[str]
) -> list[tuple[UUID, str, str | None]]:
    filters = []
    if inventory_numbers:
        filters.append(FixedAsset.inv_number.in_(inventory_numbers))
    if accounting_numbers:
        filters.append(FixedAsset.accounting_inv_number.in_(accounting_numbers))
    if not filters:
        return []
    result = await db.execute(
        select(
            FixedAsset.id,
            FixedAsset.inv_number,
            FixedAsset.accounting_inv_number,
        ).where(or_(*filters))
    )
    return list(result.all())


async def asset_stats(
    db: AsyncSession, *, master_section_id: UUID | None, asset_type: str | None = None,
    status: str | None = None, status_behavior: str | None = None,
    section_id: UUID | None = None, depot: str | None = None, q: str | None = None,
) -> tuple[int, dict[str, int], dict[str, int], dict[str, int], dict[str, int], list[str]]:
    scoped_section_id = master_section_id if master_section_id is not None else section_id
    common = dict(asset_type=asset_type, status=status, status_behavior=status_behavior,
                  section_id=scoped_section_id, depot=depot, q=q)
    filters = _asset_filters(**common)
    asset_source = (
        FixedAsset.__table__
        .outerjoin(Section.__table__, FixedAsset.section_id == Section.id)
        .outerjoin(AssetModel.__table__, FixedAsset.model_id == AssetModel.id)
    )
    total = (
        await db.execute(select(func.count()).select_from(asset_source).where(*filters))
    ).scalar_one()
    type_result = await db.execute(
        select(FixedAsset.asset_type, func.count(FixedAsset.id))
        .select_from(asset_source)
        .where(*_asset_filters(**common, omit=frozenset({"asset_type"})))
        .group_by(FixedAsset.asset_type)
    )
    status_result = await db.execute(
        select(FixedAsset.status, func.count(FixedAsset.id))
        .select_from(asset_source)
        .where(*_asset_filters(**common, omit=frozenset({"status", "status_behavior"})))
        .group_by(FixedAsset.status)
    )
    behavior_result = await db.execute(
        select(FixedAssetStatus.behavior, func.count(FixedAsset.id))
        .join(FixedAsset, FixedAsset.status == FixedAssetStatus.code)
        .outerjoin(Section, FixedAsset.section_id == Section.id)
        .outerjoin(AssetModel, FixedAsset.model_id == AssetModel.id)
        .where(*_asset_filters(**common, omit=frozenset({"status", "status_behavior"})))
        .group_by(FixedAssetStatus.behavior)
    )
    section_result = await db.execute(
        select(FixedAsset.section_id, func.count(FixedAsset.id))
        .select_from(asset_source)
        .where(*_asset_filters(**common, omit=frozenset({"section_id"})), FixedAsset.section_id.is_not(None))
        .group_by(FixedAsset.section_id)
    )
    depot_result = await db.execute(
        select(Section.name)
        .select_from(FixedAsset)
        .join(Section, Section.id == FixedAsset.section_id)
        .outerjoin(AssetModel, AssetModel.id == FixedAsset.model_id)
        .where(*_asset_filters(**common, omit=frozenset({"depot"})))
        .distinct()
        .order_by(Section.name.asc())
    )
    return (
        total,
        dict(type_result.all()),
        dict(status_result.all()),
        dict(behavior_result.all()),
        {str(section_id): count for section_id, count in section_result.all()},
        list(depot_result.scalars().all()),
    )


async def add_asset(db: AsyncSession, asset: FixedAsset) -> None:
    db.add(asset)


async def list_passport_report_data(db: AsyncSession):
    from app.repositories.asset_models import list_report_data

    assets, sections = await list_report_data(db)
    await enrich_asset_display_data(db, assets)
    return assets, sections


async def list_assets_unlinked_from_source(
    db: AsyncSession, source: str
) -> list[FixedAsset]:
    has_link = (
        select(AssetSourceLink.id)
        .where(
            AssetSourceLink.asset_id == FixedAsset.id,
            AssetSourceLink.source == source,
            AssetSourceLink.status == "active",
        )
        .exists()
    )
    result = await db.execute(
        select(FixedAsset)
        .where(~has_link)
        .order_by(fixed_asset_name_expression().asc(), FixedAsset.id.asc())
    )
    assets = list(result.scalars().all())
    await enrich_asset_display_data(db, assets)
    return assets


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
        select(FixedAsset)
        .join(AssetSourceLink, AssetSourceLink.asset_id == FixedAsset.id)
        .where(
            AssetSourceLink.source == "wialon",
            AssetSourceLink.external_id == wialon_id,
            AssetSourceLink.status == "active",
            FixedAsset.asset_type.in_(("locomotive", "diesel")),
        )
    )
    return result.scalar_one_or_none()


async def find_assets_by_name(db: AsyncSession, name: str) -> list[FixedAsset]:
    result = await db.execute(
        select(FixedAsset)
        .where(
            func.lower(fixed_asset_name_expression()) == name.strip().lower(),
            FixedAsset.asset_type.in_(("locomotive", "diesel")),
        )
        .order_by(FixedAsset.id.asc())
    )
    assets = list(result.scalars().all())
    await enrich_asset_display_data(db, assets)
    return assets


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
