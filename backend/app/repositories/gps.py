"""Queries behind the GPS comparison page: both trackers' live positions, per-day figures and tracks of the locomotives."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import String, bindparam, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.asset_models import AssetModel
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.gtk_gps import GtkGpsDay, GtkGpsRun, GtkGpsUnit
from app.models.localization import FixedAssetTypeTranslation
from app.models.organization import Section
from app.models.position_history import AssetPositionHistory
from app.models.wialon_units import WialonUnitRecord
from app.repositories.asset_map import LOCOMOTIVE_TYPES


async def list_loco_positions(
    db: AsyncSession, *, section_id: UUID | None = None, q: str | None = None, asset_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Every active locomotive with BOTH live positions (Wialon unit and GTK unit)."""
    wl, gl = aliased(AssetSourceLink), aliased(AssetSourceLink)
    type_name = (
        select(FixedAssetTypeTranslation.name)
        .where(FixedAssetTypeTranslation.type_code == FixedAsset.asset_type, FixedAssetTypeTranslation.locale == "ru")
        .limit(1).correlate(FixedAsset).scalar_subquery()
    )
    statement = (
        select(
            FixedAsset.id.label("asset_id"), FixedAsset.inv_number, fixed_asset_name_expression().label("name"), FixedAsset.asset_type,
            type_name.label("asset_type_name"), AssetModel.name.label("model_name"), FixedAsset.section_id, Section.name.label("section_name"),
            wl.id.label("wialon_link_id"), gl.id.label("gtk_link_id"), GtkGpsUnit.gtk_id.label("gtk_id"),
            WialonUnitRecord.lat.label("w_lat"), WialonUnitRecord.lon.label("w_lon"), WialonUnitRecord.speed.label("w_speed"),
            func.coalesce(WialonUnitRecord.position_at, WialonUnitRecord.last_message_at).label("w_at"),
            GtkGpsUnit.lat.label("g_lat"), GtkGpsUnit.lon.label("g_lon"), GtkGpsUnit.speed.label("g_speed"), GtkGpsUnit.position_at.label("g_at"),
        )
        .select_from(FixedAsset)
        .outerjoin(Section, FixedAsset.section_id == Section.id)
        .outerjoin(AssetModel, FixedAsset.model_id == AssetModel.id)
        .outerjoin(wl, (wl.asset_id == FixedAsset.id) & (wl.source == "wialon") & (wl.status == "active"))
        .outerjoin(WialonUnitRecord, WialonUnitRecord.unit_id == wl.external_id)
        .outerjoin(gl, (gl.asset_id == FixedAsset.id) & (gl.source == "gtk") & (gl.status == "active"))
        .outerjoin(GtkGpsUnit, cast(GtkGpsUnit.gtk_id, String) == gl.external_id)
        .where(FixedAsset.decommissioned_at.is_(None), FixedAsset.asset_type.in_(LOCOMOTIVE_TYPES))
        .order_by(FixedAsset.inv_number, FixedAsset.id)
    )
    if asset_id is not None:
        statement = statement.where(FixedAsset.id == asset_id)
    if section_id is not None:
        statement = statement.where(FixedAsset.section_id == section_id)
    if q:
        pattern = f"%{q.strip().replace('%', '').replace('_', '')}%"
        statement = statement.where(or_(FixedAsset.inv_number.ilike(pattern), FixedAsset.serial_number.ilike(pattern)))
    return [dict(r) for r in (await db.execute(statement)).mappings().all()]


_DAY_SQL = text(
    """
    WITH w AS (
        SELECT asset_id, at, lat::float8 AS lat, lon::float8 AS lon,
               lag(lat::float8) OVER (PARTITION BY asset_id ORDER BY at) AS plat,
               lag(lon::float8) OVER (PARTITION BY asset_id ORDER BY at) AS plon
        FROM asset_position_history
        WHERE source = :source AND asset_id IN :ids AND at >= :lo AND at < :hi
    )
    SELECT asset_id, (at + make_interval(hours => :off))::date AS day, count(*) AS points,
           COALESCE(sum(CASE WHEN plat IS NULL THEN 0 ELSE
               2 * 6371000 * asin(sqrt(power(sin(radians(lat - plat) / 2), 2) + cos(radians(plat)) * cos(radians(lat)) * power(sin(radians(lon - plon) / 2), 2)))
           END), 0)::bigint AS metres
    FROM w GROUP BY asset_id, day
    """
).bindparams(bindparam("ids", expanding=True))


async def stored_day_distances(
    db: AsyncSession, asset_ids: list[UUID], source: str, lo: datetime, hi: datetime, offset_hours: int,
) -> dict[tuple[UUID, date], tuple[int, int]]:
    """(asset, local day) -> (metres along the STORED, movement-thinned track, stored points). Same method for both trackers."""
    if not asset_ids:
        return {}
    rows = await db.execute(_DAY_SQL, {"source": source, "ids": asset_ids, "lo": lo, "hi": hi, "off": offset_hours})
    return {(r.asset_id, r.day): (int(r.metres), int(r.points)) for r in rows}


async def gtk_days(db: AsyncSession, gtk_ids: list[int], day_from: date, day_to: date) -> dict[tuple[int, date], GtkGpsDay]:
    if not gtk_ids:
        return {}
    rows = await db.execute(select(GtkGpsDay).where(GtkGpsDay.gtk_id.in_(gtk_ids), GtkGpsDay.day >= day_from, GtkGpsDay.day <= day_to))
    return {(d.gtk_id, d.day): d for d in rows.scalars()}


async def track(db: AsyncSession, asset_id: UUID, source: str, lo: datetime, hi: datetime, limit: int = 20000) -> list[tuple[datetime, float, float, float | None]]:
    rows = await db.execute(
        select(AssetPositionHistory.at, AssetPositionHistory.lat, AssetPositionHistory.lon, AssetPositionHistory.speed)
        .where(AssetPositionHistory.asset_id == asset_id, AssetPositionHistory.source == source, AssetPositionHistory.at >= lo, AssetPositionHistory.at < hi)
        .order_by(AssetPositionHistory.at).limit(limit)
    )
    return [(at, float(lat), float(lon), None if speed is None else float(speed)) for at, lat, lon, speed in rows.all()]


async def feed_health(db: AsyncSession) -> dict[str, Any]:
    # a run that has not finished yet (placeholder status) is not a result: show the last FINISHED one and say that one is running
    run = (await db.execute(select(GtkGpsRun).where(GtkGpsRun.finished_at.is_not(None)).order_by(GtkGpsRun.started_at.desc()).limit(1))).scalar_one_or_none()
    running = (
        await db.execute(select(func.count()).select_from(GtkGpsRun).where(GtkGpsRun.finished_at.is_(None), GtkGpsRun.started_at > func.now() - text("interval '3 hours'")))
    ).scalar_one() > 0
    units_synced = (await db.execute(select(func.max(GtkGpsUnit.last_synced_at)))).scalar_one()
    wialon_synced = (await db.execute(select(func.max(WialonUnitRecord.last_synced_at)))).scalar_one()
    stats = (
        await db.execute(
            select(AssetPositionHistory.source, func.count(), func.min(AssetPositionHistory.at))
            .where(AssetPositionHistory.source.in_(("wialon", "gtk_gps"))).group_by(AssetPositionHistory.source)
        )
    ).all()
    by_source = {s: (n, first) for s, n, first in stats}
    return {"run": run, "running": running, "gtk_units_synced_at": units_synced, "wialon_units_synced_at": wialon_synced, "by_source": by_source}
