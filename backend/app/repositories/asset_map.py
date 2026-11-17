from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.asset_models import AssetModel
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.gtk import GtkCarriage
from app.models.localization import FixedAssetStatusTranslation, FixedAssetTypeTranslation
from app.models.organization import Section
from app.models.wialon_units import WialonUnitRecord

# GTK keeps locomotives and carriages in different tables with separate id spaces: a carriage row may only be
# joined for assets that are not locomotives.
LOCOMOTIVE_TYPES = ("locomotive", "diesel", "special_self_propelled")
ONLINE_WINDOW = timedelta(minutes=15)


async def list_asset_positions(
    db: AsyncSession,
    *,
    asset_type: str | None,
    section_id: UUID | None,
    q: str | None,
) -> list[dict[str, Any]]:
    """Every active (not decommissioned) asset in scope with its Wialon and GTK position candidates."""
    wialon_link = aliased(AssetSourceLink)
    gtk_link = aliased(AssetSourceLink)
    type_name = (
        select(FixedAssetTypeTranslation.name)
        .where(FixedAssetTypeTranslation.type_code == FixedAsset.asset_type, FixedAssetTypeTranslation.locale == "ru")
        .limit(1)
        .correlate(FixedAsset)
        .scalar_subquery()
    )
    status_name = (
        select(FixedAssetStatusTranslation.name)
        .where(FixedAssetStatusTranslation.status_code == FixedAsset.status, FixedAssetStatusTranslation.locale == "ru")
        .limit(1)
        .correlate(FixedAsset)
        .scalar_subquery()
    )
    statement = (
        select(
            FixedAsset.id.label("asset_id"),
            FixedAsset.inv_number,
            fixed_asset_name_expression().label("name"),
            FixedAsset.asset_type,
            type_name.label("asset_type_name"),
            FixedAsset.status,
            status_name.label("status_name"),
            FixedAsset.section_id,
            Section.name.label("section_name"),
            AssetModel.name.label("model_name"),
            wialon_link.id.label("wialon_link_id"),
            WialonUnitRecord.lat.label("wialon_lat"),
            WialonUnitRecord.lon.label("wialon_lon"),
            WialonUnitRecord.position_at.label("wialon_position_at"),
            WialonUnitRecord.last_message_at.label("wialon_last_message_at"),
            WialonUnitRecord.speed.label("wialon_speed"),
            gtk_link.id.label("gtk_link_id"),
            GtkCarriage.lat.label("gtk_lat"),
            GtkCarriage.lon.label("gtk_lon"),
            GtkCarriage.last_synced_at.label("gtk_synced_at"),
        )
        .select_from(FixedAsset)
        .outerjoin(Section, FixedAsset.section_id == Section.id)
        .outerjoin(AssetModel, FixedAsset.model_id == AssetModel.id)
        .outerjoin(
            wialon_link,
            (wialon_link.asset_id == FixedAsset.id) & (wialon_link.source == "wialon") & (wialon_link.status == "active"),
        )
        .outerjoin(WialonUnitRecord, WialonUnitRecord.unit_id == wialon_link.external_id)
        .outerjoin(
            gtk_link,
            (gtk_link.asset_id == FixedAsset.id) & (gtk_link.source == "gtk") & (gtk_link.status == "active"),
        )
        .outerjoin(
            GtkCarriage,
            (cast(GtkCarriage.gtk_id, String) == gtk_link.external_id) & FixedAsset.asset_type.not_in(LOCOMOTIVE_TYPES),
        )
        .where(FixedAsset.decommissioned_at.is_(None))
        .order_by(FixedAsset.inv_number, FixedAsset.id)
    )
    if asset_type:
        statement = statement.where(FixedAsset.asset_type == asset_type)
    if section_id is not None:
        statement = statement.where(FixedAsset.section_id == section_id)
    if q:
        pattern = f"%{q.strip().replace('%', '').replace('_', '')}%"
        statement = statement.where(or_(FixedAsset.inv_number.ilike(pattern), FixedAsset.serial_number.ilike(pattern)))
    rows = (await db.execute(statement)).mappings().all()
    return [dict(row) for row in rows]


def online_since() -> datetime:
    return datetime.now(timezone.utc) - ONLINE_WINDOW
