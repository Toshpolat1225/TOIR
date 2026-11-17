"""Position history: keep a thinned track of every placed asset so the map can answer «where was it, and when».

Rule (same for live syncs and the Wialon backfill): store a point when the asset moved at least `MIN_MOVE_M` metres from the last
stored point, or when `HEARTBEAT` has passed (a parked unit leaves a row per 20 minutes: proof that it stood there).
A failure here never breaks a sync: the callers wrap it.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage
from app.models.position_history import AssetPositionHistory
from app.repositories.asset_map import LOCOMOTIVE_TYPES

logger = logging.getLogger(__name__)

MIN_MOVE_M = 100.0
HEARTBEAT = timedelta(minutes=20)
INSERT_CHUNK = 3000


@dataclass(frozen=True)
class Fix:
    at: datetime
    lat: float
    lon: float
    speed: float | None = None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def valid_fix(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180 and not (lat == 0 and lon == 0)


def should_store(prev: Fix | None, fix: Fix) -> bool:
    if prev is None:
        return True
    if fix.at <= prev.at:
        return False
    return haversine_m(prev.lat, prev.lon, fix.lat, fix.lon) >= MIN_MOVE_M or fix.at - prev.at >= HEARTBEAT


def thin(fixes: Iterable[Fix], prev: Fix | None = None) -> list[Fix]:
    """The points worth keeping out of a dense track, in time order."""
    kept: list[Fix] = []
    last = prev
    for fix in sorted(fixes, key=lambda f: f.at):
        if not valid_fix(fix.lat, fix.lon):
            continue
        if should_store(last, fix):
            kept.append(fix)
            last = fix
    return kept


async def _last_fixes(db: AsyncSession, asset_ids: Sequence[UUID], source: str) -> dict[UUID, Fix]:
    if not asset_ids:
        return {}
    rows = await db.execute(
        select(AssetPositionHistory.asset_id, AssetPositionHistory.at, AssetPositionHistory.lat, AssetPositionHistory.lon)
        .where(AssetPositionHistory.asset_id.in_(list(asset_ids)), AssetPositionHistory.source == source)
        .distinct(AssetPositionHistory.asset_id)
        .order_by(AssetPositionHistory.asset_id, AssetPositionHistory.at.desc())
    )
    return {a: Fix(at, float(lat), float(lon)) for a, at, lat, lon in rows.all()}


async def store(db: AsyncSession, points: dict[UUID, list[Fix]], source: str) -> int:
    rows = [
        {"asset_id": asset, "at": f.at, "lat": Decimal(str(round(f.lat, 7))), "lon": Decimal(str(round(f.lon, 7))), "speed": None if f.speed is None else Decimal(str(round(f.speed, 2))), "source": source}
        for asset, fixes in points.items() for f in fixes
    ]
    for i in range(0, len(rows), INSERT_CHUNK):
        await db.execute(insert(AssetPositionHistory).values(rows[i : i + INSERT_CHUNK]).on_conflict_do_nothing(constraint="uq_asset_position_history_point"))
    return len(rows)


async def record_wialon(db: AsyncSession, units: Sequence, *, synced_at: datetime) -> int:
    """After a Wialon pull: one fix per linked unit, thinned against the last stored point."""
    with_fix = [u for u in units if valid_fix(None if u.lat is None else float(u.lat), None if u.lon is None else float(u.lon))]
    if not with_fix:
        return 0
    links = {
        external: asset
        for external, asset in (
            await db.execute(
                select(AssetSourceLink.external_id, AssetSourceLink.asset_id)
                .where(AssetSourceLink.source == "wialon", AssetSourceLink.status == "active", AssetSourceLink.external_id.in_([u.unit_id for u in with_fix]))
            )
        ).all()
    }
    last = await _last_fixes(db, list(links.values()), "wialon")
    points: dict[UUID, list[Fix]] = {}
    for u in with_fix:
        asset = links.get(u.unit_id)
        if asset is None:
            continue
        fix = Fix(u.position_at or u.last_message_at or synced_at, float(u.lat), float(u.lon), None if u.speed is None else float(u.speed))
        kept = thin([fix], last.get(asset))
        if kept:
            points[asset] = kept
    return await store(db, points, "wialon")


async def record_gtk(db: AsyncSession, *, synced_at: datetime) -> int:
    """After a GTK sync: the carriage coordinates GTK itself reports (wagons only; GTK has no time of the fix, the sync time is used)."""
    link_rows = (
        await db.execute(
            select(AssetSourceLink.asset_id, AssetSourceLink.external_id)
            .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
            .where(AssetSourceLink.source == "gtk", AssetSourceLink.status == "active", FixedAsset.asset_type.notin_(LOCOMOTIVE_TYPES))
        )
    ).all()
    asset_by_carriage = {int(ext): asset for asset, ext in link_rows if str(ext).isdigit()}
    if not asset_by_carriage:
        return 0
    carriages = (
        await db.execute(
            select(GtkCarriage.gtk_id, GtkCarriage.lat, GtkCarriage.lon)
            .where(GtkCarriage.gtk_id.in_(list(asset_by_carriage)), GtkCarriage.lat.is_not(None), GtkCarriage.lon.is_not(None))
        )
    ).all()
    last = await _last_fixes(db, list(asset_by_carriage.values()), "gtk")
    points: dict[UUID, list[Fix]] = {}
    for gtk_id, lat, lon in carriages:
        if not valid_fix(float(lat), float(lon)):
            continue
        asset = asset_by_carriage[gtk_id]
        kept = thin([Fix(synced_at, float(lat), float(lon))], last.get(asset))
        if kept:
            points[asset] = kept
    return await store(db, points, "gtk")


async def safe_record_wialon(db: AsyncSession, units: Sequence, *, synced_at: datetime) -> None:
    try:
        await record_wialon(db, units, synced_at=synced_at)  # committed with the sync's own next commit
    except Exception:  # the history must never break the sync
        await db.rollback()
        logger.exception("position history (wialon) failed")


async def safe_record_gtk(db: AsyncSession, *, synced_at: datetime) -> None:
    try:
        await record_gtk(db, synced_at=synced_at)
    except Exception:
        await db.rollback()
        logger.exception("position history (gtk) failed")


async def backfill_wialon_tracks(db: AsyncSession, client, *, days: int, unit_ids: Sequence[str] | None = None, progress=None) -> dict[str, int]:
    """Load the past track of every linked Wialon unit (a day at a time), thin it and store it. Safe to repeat."""
    now = datetime.now(timezone.utc)
    links = (
        await db.execute(
            select(AssetSourceLink.external_id, AssetSourceLink.asset_id).where(
                AssetSourceLink.source == "wialon", AssetSourceLink.status == "active",
                *([AssetSourceLink.external_id.in_(list(unit_ids))] if unit_ids else []),
            )
        )
    ).all()
    stats = {"units": 0, "stored": 0, "failed": 0}
    async for unit_id, fixes in client.fetch_tracks([u for u, _a in links], now - timedelta(days=days), now):
        asset = next((a for u, a in links if u == unit_id), None)
        if asset is None:
            continue
        stats["units"] += 1
        if fixes is None:
            stats["failed"] += 1
            continue
        kept = thin([Fix(at, lat, lon, speed) for at, lat, lon, speed in fixes])
        stats["stored"] += await store(db, {asset: kept}, "wialon")
        await db.commit()
        if progress:
            progress(unit_id, len(fixes), len(kept))
    return stats
