from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_models import AssetModel
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.asset_source_links import AssetSourceLink
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
        "org_unit_id",
        "mileage",
        "wialon_cnm",
        "wialon_cneh",
        "speed",
        "last_message_at",
        "is_online",
        "suspect_absolute",
    }
)


def _wialon_links():
    return (
        select(
            AssetSourceLink.asset_id.label("asset_id"),
            *WialonUnitRecord.__table__.columns,
        )
        .join(
            WialonUnitRecord,
            WialonUnitRecord.unit_id == AssetSourceLink.external_id,
        )
        .where(
            AssetSourceLink.source == "wialon",
            AssetSourceLink.status == "active",
        )
        .subquery()
    )


def _gtk_linked_expression():
    return (
        select(AssetSourceLink.id)
        .where(
            AssetSourceLink.asset_id == FixedAsset.id,
            AssetSourceLink.source == "gtk",
            AssetSourceLink.status == "active",
        )
        .exists()
    )


def _source_expression(unit):
    """Which systems know the asset: TOIR is the base, Wialon and GTK are links."""
    has_gtk = _gtk_linked_expression()
    has_unit = unit.unit_id.is_not(None)
    return case(
        (FixedAsset.id.is_(None), "wialon"),
        (has_unit & has_gtk, "toir_wialon_gtk"),
        (has_unit, "both"),
        (has_gtk, "toir_gtk"),
        else_="toir",
    )


def _online_expression(now: datetime):
    return (
        WialonUnitRecord.last_message_at.is_not(None)
        & (WialonUnitRecord.last_message_at >= now - timedelta(minutes=15))
    )


def _joined_from(unit_links):
    return (
        FixedAsset.__table__
        .join(
            unit_links,
            FixedAsset.id == unit_links.c.asset_id,
            full=True,
        )
        .outerjoin(Section.__table__, FixedAsset.section_id == Section.id)
        .outerjoin(AssetModel.__table__, FixedAsset.model_id == AssetModel.id)
    )


def _sort_columns(now: datetime, unit) -> dict[str, Any]:
    return {
        "source": _source_expression(unit),
        "asset_id": FixedAsset.id,
        "unit_id": unit.unit_id,
        "name": func.coalesce(fixed_asset_name_expression(), unit.name),
        "asset_type": FixedAsset.asset_type,
        "series": AssetModel.series,
        "inv_number": FixedAsset.inv_number,
        "status": FixedAsset.status,
        "section": Section.name,
        "section_id": FixedAsset.section_id,
        "org_unit_id": FixedAsset.section_id,
        "mileage": FixedAsset.mileage,
        "wialon_cnm": unit.cnm,
        "wialon_cneh": unit.cneh,
        "speed": unit.speed,
        "last_message_at": unit.last_message_at,
        "is_online": unit.last_message_at.is_not(None)
        & (unit.last_message_at >= now - timedelta(minutes=15)),
        "suspect_absolute": unit.suspect_absolute,
    }


async def list_unified_assets(
    db: AsyncSession,
    *,
    source: str | None,
    asset_type: str | None,
    status: str | None,
    section_id: UUID | None,
    without_org_unit: bool = False,
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
    if source == "gtk":
        return await _list_gtk_only(
            db,
            asset_type=asset_type,
            status=status,
            section_id=section_id,
            without_org_unit=without_org_unit,
            master_section_id=master_section_id,
            q=q,
            limit=limit,
            offset=offset,
            descending=sort_order == "desc",
        )

    filters: list[Any] = []
    unit_links = _wialon_links()
    unit = aliased(WialonUnitRecord, unit_links)
    if source is not None:
        filters.append(_source_expression(unit) == source)
    if asset_type is not None:
        filters.append(FixedAsset.asset_type == asset_type)
    if status is not None:
        filters.append(FixedAsset.status == status)
    effective_section_id = (
        master_section_id if master_section_id is not None else section_id
    )
    if effective_section_id is not None:
        filters.append(FixedAsset.section_id == effective_section_id)
    if without_org_unit:
        filters.extend((FixedAsset.id.is_not(None), FixedAsset.section_id.is_(None)))
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                fixed_asset_name_expression().ilike(pattern),
                FixedAsset.inv_number.ilike(pattern),
                AssetModel.series.ilike(pattern),
                unit.name.ilike(pattern),
                unit.unit_id.ilike(pattern),
            )
        )

    joined = _joined_from(unit_links)
    count_query = select(func.count()).select_from(joined)
    rows_query = select(
        FixedAsset,
        unit,
        Section,
        fixed_asset_name_expression(),
        AssetModel.series,
        _gtk_linked_expression().label("has_gtk"),
    ).select_from(joined)
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)
    total = (await db.execute(count_query)).scalar_one()
    column = _sort_columns(now, unit)[sort_by]
    ordering = column.desc() if sort_order == "desc" else column.asc()
    result = await db.execute(
        rows_query.order_by(
            ordering,
            unit.unit_id.asc().nulls_last(),
            FixedAsset.id.asc().nulls_last(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.all()), total


_GTK_ONLY_FROM = """
FROM (
    SELECT 'carriage' AS kind, c.gtk_id, coalesce(c.name, c.reg_number, c.gtk_id::text) AS name,
           c.inventory_number AS inventory_number, c.reg_number AS extra
    FROM gtk_carriages c
    UNION ALL
    SELECT 'locomotive', l.gtk_id, coalesce(l.name, l.garage_number, l.gtk_id::text),
           l.inventory_number, l.garage_number
    FROM gtk_locomotives l
) g
WHERE NOT EXISTS (
    SELECT 1 FROM asset_source_links s
    WHERE s.source = 'gtk' AND s.status = 'active'
      AND s.external_id = g.gtk_id::text
)
"""
_GTK_KIND_BY_TYPE = {"wagon": "carriage", "locomotive": "locomotive"}


def _like_pattern(value: str) -> str:
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _list_gtk_only(
    db: AsyncSession,
    *,
    asset_type: str | None,
    status: str | None,
    section_id: UUID | None,
    without_org_unit: bool,
    master_section_id: UUID | None,
    q: str | None,
    limit: int,
    offset: int,
    descending: bool,
):
    """GTK objects that have no TOIR asset yet. They carry no TOIR status or section,
    so any filter on those (or a master's section scope) leaves nothing to show."""
    if (
        status is not None
        or section_id is not None
        or without_org_unit
        or master_section_id is not None
        or (asset_type is not None and asset_type not in _GTK_KIND_BY_TYPE)
    ):
        return [], 0
    where = ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if asset_type is not None:
        where += " AND g.kind = :kind"
        params["kind"] = _GTK_KIND_BY_TYPE[asset_type]
    if q:
        where += (
            " AND (g.name ILIKE :q ESCAPE '\\' OR g.inventory_number ILIKE :q ESCAPE '\\'"
            " OR g.extra ILIKE :q ESCAPE '\\')"
        )
        params["q"] = _like_pattern(q)
    total = (
        await db.execute(text(f"SELECT count(*) {_GTK_ONLY_FROM} {where}"), params)
    ).scalar_one()
    direction = "DESC" if descending else "ASC"
    rows = await db.execute(
        text(
            f"SELECT g.kind, g.gtk_id, g.name, g.inventory_number {_GTK_ONLY_FROM} {where} "
            f"ORDER BY g.name {direction}, g.gtk_id LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return [dict(row._mapping) for row in rows.all()], total
