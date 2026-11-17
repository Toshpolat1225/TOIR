from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.asset_models import AssetModel
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.gtk import GtkCarriage, GtkTrain, GtkTrainMember
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
            gtk_link.external_id.label("gtk_external_id"),
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


async def list_train_positions(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """For every OPEN GTK train whose locomotive has a Wialon position: carriage gtk_id (as text) -> train + locomotive.

    The main locomotive wins (then the lowest order); a locomotive without a Wialon fix is skipped, so the next one
    can still place the train. Wagons themselves have no GPS: they are shown where their locomotive is.
    """
    loco_link = aliased(AssetSourceLink)
    wialon_link = aliased(AssetSourceLink)
    locomotives = (
        select(
            GtkTrainMember.train_gtk_id,
            GtkTrain.number.label("train_number"),
            FixedAsset.id.label("locomotive_asset_id"),
            FixedAsset.inv_number.label("locomotive_inv_number"),
            fixed_asset_name_expression().label("locomotive_name"),
            FixedAsset.section_id.label("locomotive_section_id"),
            WialonUnitRecord.lat.label("lat"),
            WialonUnitRecord.lon.label("lon"),
            WialonUnitRecord.position_at.label("position_at"),
            WialonUnitRecord.last_message_at.label("last_message_at"),
            WialonUnitRecord.speed.label("speed"),
        )
        .select_from(GtkTrainMember)
        .join(GtkTrain, GtkTrain.gtk_id == GtkTrainMember.train_gtk_id)
        .join(
            loco_link,
            (loco_link.source == "gtk")
            & (loco_link.status == "active")
            & (loco_link.external_id == cast(GtkTrainMember.object_gtk_id, String)),
        )
        .join(
            FixedAsset,
            (FixedAsset.id == loco_link.asset_id)
            & FixedAsset.asset_type.in_(LOCOMOTIVE_TYPES)
            & FixedAsset.decommissioned_at.is_(None),
        )
        .join(
            wialon_link,
            (wialon_link.asset_id == FixedAsset.id) & (wialon_link.source == "wialon") & (wialon_link.status == "active"),
        )
        .join(WialonUnitRecord, WialonUnitRecord.unit_id == wialon_link.external_id)
        .where(
            GtkTrainMember.observed_to.is_(None),
            GtkTrainMember.kind == "locomotive",
            GtkTrain.is_open.is_(True),
            WialonUnitRecord.lat.is_not(None),
            WialonUnitRecord.lon.is_not(None),
        )
        .order_by(GtkTrainMember.train_gtk_id, GtkTrainMember.is_main.desc(), GtkTrainMember.ord, FixedAsset.inv_number)
    )
    best: dict[int, dict[str, Any]] = {}
    for row in (await db.execute(locomotives)).mappings().all():
        lat, lon = row["lat"], row["lon"]
        if abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0):
            continue
        best.setdefault(row["train_gtk_id"], dict(row))
    if not best:
        return {}
    carriages = select(GtkTrainMember.train_gtk_id, GtkTrainMember.object_gtk_id).where(
        GtkTrainMember.observed_to.is_(None),
        GtkTrainMember.kind == "carriage",
        GtkTrainMember.train_gtk_id.in_(list(best)),
    )
    return {str(row.object_gtk_id): best[row.train_gtk_id] for row in (await db.execute(carriages)).all()}


def online_since() -> datetime:
    return datetime.now(timezone.utc) - ONLINE_WINDOW
