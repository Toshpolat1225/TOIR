"""GTK's own GPS feed: live unit positions + one track fetch per linked locomotive and local day. Read-only towards GTK.

Per cycle (every `GTK_GPS_SYNC_INTERVAL_MINUTES`): one `get_vehicles` call (all units, upserted into `gtk_gps_units`) and, for every
locomotive linked to a GTK unit, the track of the CURRENT local day (distance + points) plus the previous day until it is final
(fetched once after midnight + grace). Points are movement-thinned like Wialon's and stored in `asset_position_history`
with source 'gtk_gps'; the day's figure lives in `gtk_gps_days`. Re-fetching a day is idempotent.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory
from app.integrations.gtk_client import GtkClientError, GtkLoginError
from app.integrations.gtk_gps_client import GpsPoint, GtkGpsClient, GtkTrack
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk_gps import GtkGpsDay, GtkGpsRun, GtkGpsUnit
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.services import position_history as ph

logger = logging.getLogger(__name__)

SOURCE = "gtk_gps"
FINAL_GRACE = timedelta(minutes=45)  # a day is final this long after local midnight (late messages still arrive)
PARALLEL = 2  # simultaneous track requests: GTK is a production system
PAUSE_S = 0.15
BATCH = 76  # tracks fetched and stored per step


@dataclass(frozen=True)
class DayWindow:
    day: date
    local_from: datetime  # naive local
    local_to: datetime


def local_now(now: datetime, offset_hours: int) -> datetime:
    """Naive local time of an aware instant."""
    return (now.astimezone(timezone.utc) + timedelta(hours=offset_hours)).replace(tzinfo=None)


def day_window(day: date, now: datetime, offset_hours: int) -> DayWindow:
    """The local day [00:00:00, 23:59:59]; for today it ends now (GTK refuses nothing, but the figure is then «so far»)."""
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(hours=23, minutes=59, seconds=59)
    current = local_now(now, offset_hours)
    return DayWindow(day, start, min(end, current) if current.date() == day else end)


def is_final_day(day: date, now: datetime, offset_hours: int) -> bool:
    return local_now(now, offset_hours) >= datetime(day.year, day.month, day.day) + timedelta(days=1) + FINAL_GRACE


def days_to_fetch(today: date, final_days: set[date], backfill_days: int = 0) -> list[date]:
    """Today always; yesterday until it is final; with a backfill every missing day back to `backfill_days` ago."""
    wanted = [today]
    yesterday = today - timedelta(days=1)
    if yesterday not in final_days:
        wanted.append(yesterday)
    for back in range(2, backfill_days + 1):
        d = today - timedelta(days=back)
        if d not in final_days:
            wanted.append(d)
    return wanted


async def linked_targets(db: AsyncSession) -> dict[int, UUID]:
    """GTK unit id -> locomotive asset, from the active GTK links (the same ids as the GTK train page)."""
    rows = await db.execute(
        select(AssetSourceLink.external_id, AssetSourceLink.asset_id)
        .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
        .where(
            AssetSourceLink.source == "gtk", AssetSourceLink.status == "active",
            FixedAsset.asset_type.in_(LOCOMOTIVE_TYPES), FixedAsset.decommissioned_at.is_(None),
        )
    )
    return {int(external): asset for external, asset in rows.all() if str(external).isdigit()}


async def upsert_units(db: AsyncSession, units: Sequence[dict], now: datetime) -> int:
    def dec(value: float | None, places: int) -> Decimal | None:
        return None if value is None else Decimal(str(round(value, places)))

    rows = [
        {
            "gtk_id": u["gtk_id"], "name": u["name"], "garage_number": u["garage_number"], "model_name": u["model_name"],
            "vehicle_type_id": u["vehicle_type_id"], "enterprise_id": u["enterprise_id"],
            "lat": dec(u["lat"], 7) if ph.valid_fix(u["lat"], u["lon"]) else None,
            "lon": dec(u["lon"], 7) if ph.valid_fix(u["lat"], u["lon"]) else None,
            "speed": dec(u["speed"], 2), "course": dec(u["course"], 2), "height": dec(u["height"], 2),
            "position_at": u["position_at"], "last_synced_at": now,
        }
        for u in units
    ]
    for i in range(0, len(rows), 500):
        stmt = insert(GtkGpsUnit).values(rows[i : i + 500])
        update = {c: getattr(stmt.excluded, c) for c in rows[0] if c != "gtk_id"}
        await db.execute(stmt.on_conflict_do_update(index_elements=["gtk_id"], set_=update))
    return len(rows)


def _fixes(points: Sequence[GpsPoint]) -> list[ph.Fix]:
    return ph.thin([ph.Fix(p.at, p.lat, p.lon, p.speed) for p in points])


async def store_day(
    db: AsyncSession, *, gtk_id: int, asset_id: UUID, day: date, track: GtkTrack, final: bool, now: datetime,
) -> int:
    """Upsert the day's figure and store its thinned points; returns the number of points offered for storage."""
    kept = _fixes(track.points)
    stored = await ph.store(db, {asset_id: kept}, SOURCE) if kept else 0
    values = {
        "gtk_id": gtk_id, "day": day, "distance_m": track.distance_m, "points": len(track.points),
        "first_at": track.points[0].at if track.points else None, "last_at": track.points[-1].at if track.points else None,
        "events": track.events or None, "is_final": final, "fetched_at": now,
    }
    stmt = insert(GtkGpsDay).values(values)
    await db.execute(stmt.on_conflict_do_update(index_elements=["gtk_id", "day"], set_={k: getattr(stmt.excluded, k) for k in values if k not in ("gtk_id", "day")}))
    return stored


async def _final_days(db: AsyncSession, gtk_ids: Sequence[int], since: date) -> dict[int, set[date]]:
    rows = await db.execute(select(GtkGpsDay.gtk_id, GtkGpsDay.day).where(GtkGpsDay.gtk_id.in_(list(gtk_ids)), GtkGpsDay.is_final.is_(True), GtkGpsDay.day >= since))
    out: dict[int, set[date]] = {}
    for gtk_id, day in rows.all():
        out.setdefault(gtk_id, set()).add(day)
    return out


async def _fetch_all(client: GtkGpsClient, jobs: list[tuple[int, date, DayWindow]]) -> list[tuple[int, date, GtkTrack | None, str | None]]:
    """Fetch the tracks with a little parallelism; one failed unit never stops the others."""
    gate = asyncio.Semaphore(PARALLEL)

    async def one(job: tuple[int, date, DayWindow]) -> tuple[int, date, GtkTrack | None, str | None]:
        gtk_id, day, window = job
        async with gate:
            try:
                track = await client.track(gtk_id, window.local_from, window.local_to)
                await asyncio.sleep(PAUSE_S)
                return gtk_id, day, track, None
            except GtkLoginError:
                raise
            except GtkClientError as exc:
                return gtk_id, day, None, type(exc).__name__

    return list(await asyncio.gather(*(one(j) for j in jobs)))


STALE_RUN = timedelta(minutes=15)  # a run that has not committed a batch for this long is dead (its process was killed)


async def close_stale_runs(db: AsyncSession, now: datetime) -> int:
    """Finish the rows of runs whose process died (a restart, a kill): otherwise they look «running» for ever."""
    result = await db.execute(
        update(GtkGpsRun)
        .where(GtkGpsRun.finished_at.is_(None), func.coalesce(GtkGpsRun.heartbeat_at, GtkGpsRun.started_at) < now - STALE_RUN)
        .values(finished_at=now, status="failed", error_code="interrupted")
    )
    return result.rowcount or 0


async def sync_gtk_gps(
    db: AsyncSession, *, now: datetime | None = None, backfill_days: int = 0, progress: Callable[[str], None] | None = None,
) -> GtkGpsRun:
    """One cycle. Never raises for a GTK problem: the run row says what happened."""
    now = now or datetime.now(timezone.utc)
    await close_stale_runs(db, now)
    run = GtkGpsRun(status="failed", started_at=now, heartbeat_at=now)
    db.add(run)
    await db.flush()
    offset = settings.gtk_utc_offset_hours
    try:
        async with GtkGpsClient(settings.gtk_host, settings.gtk_user, settings.gtk_password, offset_hours=offset) as client:
            units = await client.vehicles()
            run.units = await upsert_units(db, units, now)
            await db.commit()  # the live positions are the most valuable part: keep them whatever happens to the tracks
            targets = await linked_targets(db)
            present = {u["gtk_id"] for u in units}
            targets = {g: a for g, a in targets.items() if g in present}
            today = local_now(now, offset).date()
            finals = await _final_days(db, list(targets), today - timedelta(days=max(3, backfill_days + 1)))
            jobs: list[tuple[int, date, DayWindow]] = []
            for gtk_id in targets:
                for day in days_to_fetch(today, finals.get(gtk_id, set()), backfill_days):
                    jobs.append((gtk_id, day, day_window(day, now, offset)))
            # a day shows up only while it is the CURRENT or a missing one; a final day is skipped by days_to_fetch
            # in batches: a 30-day backfill must not hold thousands of tracks in memory, and every batch is committed
            for start in range(0, len(jobs), BATCH):
                for gtk_id, day, track, error in await _fetch_all(client, jobs[start : start + BATCH]):
                    if track is None:
                        run.tracks_failed += 1
                        run.error_code = run.error_code or error
                        continue
                    run.points_stored += await store_day(
                        db, gtk_id=gtk_id, asset_id=targets[gtk_id], day=day, track=track, final=is_final_day(day, now, offset), now=now,
                    )
                    run.tracks_ok += 1
                run.heartbeat_at = datetime.now(timezone.utc)
                await db.commit()
                if progress:
                    progress(f"{min(start + BATCH, len(jobs))}/{len(jobs)} tracks, points={run.points_stored}, failed={run.tracks_failed}")
            run.status = "success" if run.tracks_failed == 0 else ("partial" if run.tracks_ok else "failed")
            if progress:
                progress(f"units={run.units} tracks_ok={run.tracks_ok} failed={run.tracks_failed} points={run.points_stored}")
    except GtkClientError as exc:
        run.status = "failed" if run.units == 0 else "partial"
        run.error_code = type(exc).__name__
        logger.error("GTK GPS synchronization failed (%s)", type(exc).__name__)
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    return run


async def _analytics_cycle() -> None:
    """After a GTK GPS cycle: refresh the per-day assessments and the wagon segments. Never breaks the sync loop."""
    from app.services import gps_assessment, wagon_gps  # local import: these import this module

    try:
        async with SessionFactory() as db:
            await gps_assessment.assess_recent(db)
        async with SessionFactory() as db:
            await wagon_gps.compute_segments(db, back_days=3)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("GPS analytics refresh failed (%s)", type(exc).__name__)


async def run_periodic_gtk_gps_sync() -> None:
    while True:
        if settings.gtk_gps_pull_enabled:
            try:
                async with SessionFactory() as db:
                    await sync_gtk_gps(db)
                await _analytics_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Background GTK GPS synchronization failed (%s)", type(exc).__name__)
        await asyncio.sleep(settings.gtk_gps_sync_interval_minutes * 60)
