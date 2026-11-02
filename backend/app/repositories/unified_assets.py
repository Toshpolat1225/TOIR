from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.organization import Section
from app.models.wialon_units import WialonUnitRecord

UNIFIED_SORT_FIELDS = frozenset(
    {
        "source",
        "asset_id",
        "unit_id",
        "name",
        "asset_type",
        "series",
        "inv_number",
        "status",
        "section",
        "section_id",
        "mileage",
        "wialon_cnm",
        "wialon_cneh",
        "speed",
        "last_message_at",
        "is_online",
        "suspect_absolute",
    }
)


def _source_expression():
    return case(
        (
            FixedAsset.id.is_not(None) & WialonUnitRecord.unit_id.is_not(None),
            "both",
        ),
        (FixedAsset.id.is_not(None), "toir"),
        else_="wialon",
    )


def _online_expression(now: datetime):
    return (
        WialonUnitRecord.last_message_at.is_not(None)
        & (WialonUnitRecord.last_message_at >= now - timedelta(minutes=15))
    )


def _joined_from():
    return (
        FixedAsset.__table__
        .join(
            WialonUnitRecord.__table__,
            FixedAsset.wialon_id == WialonUnitRecord.unit_id,
            full=True,
        )
        .outerjoin(Section.__table__, FixedAsset.section_id == Section.id)
    )


def _sort_columns(now: datetime) -> dict[str, Any]:
    return {
        "source": _source_expression(),
        "asset_id": FixedAsset.id,
        "unit_id": WialonUnitRecord.unit_id,
        "name": func.coalesce(FixedAsset.name, WialonUnitRecord.name),
        "asset_type": FixedAsset.asset_type,
        "series": FixedAsset.series,
        "inv_number": FixedAsset.inv_number,
        "status": FixedAsset.status,
        "section": Section.name,
        "section_id": FixedAsset.section_id,
        "mileage": FixedAsset.mileage,
        "wialon_cnm": WialonUnitRecord.cnm,
        "wialon_cneh": WialonUnitRecord.cneh,
        "speed": WialonUnitRecord.speed,
        "last_message_at": WialonUnitRecord.last_message_at,
        "is_online": _online_expression(now),
        "suspect_absolute": WialonUnitRecord.suspect_absolute,
    }


async def list_unified_assets(
    db: AsyncSession,
    *,
    source: str | None,
    asset_type: str | None,
    status: str | None,
    section_id: UUID | None,
    master_section_id: UUID | None,
    q: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
    now: datetime,
):
    if sort_by not in UNIFIED_SORT_FIELDS:
        raise ValueError("Unsupported sort field")

    filters: list[Any] = []
    if source is not None:
        filters.append(_source_expression() == source)
    if asset_type is not None:
        filters.append(FixedAsset.asset_type == asset_type)
    if status is not None:
        filters.append(FixedAsset.status == status)
    effective_section_id = (
        master_section_id if master_section_id is not None else section_id
    )
    if effective_section_id is not None:
        filters.append(FixedAsset.section_id == effective_section_id)
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                FixedAsset.name.ilike(pattern),
                FixedAsset.inv_number.ilike(pattern),
                FixedAsset.series.ilike(pattern),
                WialonUnitRecord.name.ilike(pattern),
                WialonUnitRecord.unit_id.ilike(pattern),
            )
        )

    joined = _joined_from()
    count_query = select(func.count()).select_from(joined)
    rows_query = select(FixedAsset, WialonUnitRecord, Section).select_from(joined)
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)
    total = (await db.execute(count_query)).scalar_one()
    column = _sort_columns(now)[sort_by]
    ordering = column.desc() if sort_order == "desc" else column.asc()
    result = await db.execute(
        rows_query.order_by(
            ordering,
            WialonUnitRecord.unit_id.asc().nulls_last(),
            FixedAsset.id.asc().nulls_last(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.all()), total
