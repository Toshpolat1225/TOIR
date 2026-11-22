"""One compact row per fixed asset that gathers the key facts of the other modules (GPS verdict, GTK train, scales, last repair).

It only READS what those modules already store and uses their own rules (the map service decides the GPS verdict), so the
asset directory can never disagree with them. A master only gets assets of their own section and no GTK / scales facts
(those modules are closed to that role).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.services import asset_map as asset_map_service

MAX_IDS = 200


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def build_overview(db: AsyncSession, user: User, asset_ids: list[UUID]) -> dict[str, dict[str, Any]]:
    ids = list(dict.fromkeys(asset_ids))[:MAX_IDS]
    if not ids:
        return {}
    is_master = user.role == "master"
    scope = user.section_id if is_master else None
    rows = (
        await db.execute(
            text(
                "SELECT id, asset_type, last_maint_date, next_maint_date FROM fixed_assets "
                "WHERE id = ANY(:ids) AND (CAST(:scope AS uuid) IS NULL OR section_id = CAST(:scope AS uuid))"
            ),
            {"ids": ids, "scope": scope},
        )
    ).mappings().all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[str(row["id"])] = {
            "gps": None,
            "gtk": None,
            "scales": None,
            "maintenance": {
                "last_maint_date": row["last_maint_date"].isoformat() if row["last_maint_date"] else None,
                "next_maint_date": row["next_maint_date"].isoformat() if row["next_maint_date"] else None,
                "last_order_at": None,
                "last_order_status": None,
                "open_orders": 0,
            },
        }
    if not out:
        return out
    allowed = [UUID(key) for key in out]
    types = {str(row["id"]): row["asset_type"] for row in rows}

    # --- GPS / map: the very same decision as the Map and GPS pages ---------------------------------------------
    points = (await asset_map_service.get_asset_map(db, user)).points
    for point in points:
        key = str(point.asset_id)
        if key in out:
            out[key]["gps"] = {
                "verdict": point.gps_verdict,
                "source": point.source,
                "position_at": _iso(point.position_at),
                "online": point.online,
                "speed": float(point.speed) if point.speed is not None else None,
                "lat": point.lat,
                "lon": point.lon,
                "train_number": point.train_number,
                "diff_m": point.gps_diff_m,
            }

    # --- maintenance: the latest finished work order and the number of open ones ---------------------------------
    orders = (
        await db.execute(
            text(
                "SELECT fixed_asset_id AS asset_id, "
                "max(COALESCE(closed_at, actual_end)) FILTER (WHERE status = 'completed') AS last_at, "
                "count(*) FILTER (WHERE status IN ('pending','in_progress')) AS open_count, "
                "(array_agg(status ORDER BY created_at DESC))[1] AS last_status "
                "FROM work_orders WHERE fixed_asset_id = ANY(:ids) GROUP BY fixed_asset_id"
            ),
            {"ids": allowed},
        )
    ).mappings().all()
    for row in orders:
        item = out[str(row["asset_id"])]["maintenance"]
        item["last_order_at"] = _iso(row["last_at"])
        item["last_order_status"] = row["last_status"]
        item["open_orders"] = int(row["open_count"] or 0)
    baselines = (
        await db.execute(
            text("SELECT asset_id, max(done_at) AS done_at FROM asset_maintenance_baseline WHERE asset_id = ANY(:ids) GROUP BY asset_id"),
            {"ids": allowed},
        )
    ).mappings().all()
    for row in baselines:
        if row["done_at"]:
            item = out[str(row["asset_id"])]["maintenance"]
            if not item["last_maint_date"] or row["done_at"].isoformat() > item["last_maint_date"]:
                item["last_maint_date"] = row["done_at"].isoformat()

    if is_master:
        return out

    # --- GTK: the open train the asset is in right now --------------------------------------------------------------
    loco_types = list(LOCOMOTIVE_TYPES)
    members = (
        await db.execute(
            text(
                "SELECT l.asset_id, m.train_gtk_id, m.is_main, m.ord, t.number, t.title, t.begin_time, "
                "(SELECT count(*) FROM gtk_train_members x WHERE x.train_gtk_id = m.train_gtk_id AND x.observed_to IS NULL AND x.kind = 'carriage') AS carriages "
                "FROM asset_source_links l "
                "JOIN fixed_assets a ON a.id = l.asset_id "
                "JOIN gtk_train_members m ON m.observed_to IS NULL "
                "  AND m.kind = CASE WHEN a.asset_type = ANY(:loco) THEN 'locomotive' ELSE 'carriage' END "
                "  AND m.object_gtk_id = CASE WHEN l.external_id ~ '^[0-9]+$' THEN CAST(l.external_id AS integer) ELSE NULL END "
                "JOIN gtk_trains t ON t.gtk_id = m.train_gtk_id AND t.is_open "
                "WHERE l.source = 'gtk' AND l.status = 'active' AND l.asset_id = ANY(:ids)"
            ),
            {"ids": allowed, "loco": loco_types},
        )
    ).mappings().all()
    for row in members:
        out[str(row["asset_id"])]["gtk"] = {
            "train_gtk_id": row["train_gtk_id"],
            "train_number": row["number"],
            "train_title": row["title"],
            "is_main": bool(row["is_main"]),
            "order": row["ord"],
            "carriages": int(row["carriages"] or 0),
            "since": _iso(row["begin_time"]),
        }

    # --- scales: the latest weighing the asset took part in --------------------------------------------------------
    loco_ids = [i for i in allowed if types[str(i)] in LOCOMOTIVE_TYPES]
    wagon_ids = [i for i in allowed if types[str(i)] not in LOCOMOTIVE_TYPES]
    if loco_ids:
        for row in (
            await db.execute(
                text(
                    "SELECT DISTINCT ON (loco_asset_id) loco_asset_id AS asset_id, started_at, net_total_t, wagon_rows, match_status, "
                    "(SELECT count(*) FROM scale_trains y WHERE y.loco_asset_id = t.loco_asset_id AND y.started_at > now() - interval '30 days') AS trains_30d "
                    "FROM scale_trains t WHERE loco_asset_id = ANY(:ids) AND started_at IS NOT NULL "
                    "ORDER BY loco_asset_id, started_at DESC"
                ),
                {"ids": loco_ids},
            )
        ).mappings().all():
            out[str(row["asset_id"])]["scales"] = {
                "last_at": _iso(row["started_at"]),
                "net_t": float(row["net_total_t"]) if row["net_total_t"] is not None else None,
                "units": row["wagon_rows"],
                "trains_30d": int(row["trains_30d"] or 0),
                "match": row["match_status"],
            }
    if wagon_ids:
        for row in (
            await db.execute(
                text(
                    "SELECT DISTINCT ON (c.asset_id) c.asset_id, t.started_at, c.net_t, "
                    "(SELECT count(*) FROM scale_train_carriages z JOIN scale_trains y ON y.id = z.train_id "
                    "  WHERE z.asset_id = c.asset_id AND y.started_at > now() - interval '30 days') AS trains_30d "
                    "FROM scale_train_carriages c JOIN scale_trains t ON t.id = c.train_id "
                    "WHERE c.asset_id = ANY(:ids) AND t.started_at IS NOT NULL "
                    "ORDER BY c.asset_id, t.started_at DESC"
                ),
                {"ids": wagon_ids},
            )
        ).mappings().all():
            out[str(row["asset_id"])]["scales"] = {
                "last_at": _iso(row["started_at"]),
                "net_t": float(row["net_t"]) if row["net_t"] is not None else None,
                "units": None,
                "trains_30d": int(row["trains_30d"] or 0),
                "match": None,
            }
    return out
