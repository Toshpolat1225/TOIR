"""Weighing-scale feed: ingest from the Windows collector, dynamic matching to GTK / TOIR assets, corrections and work metrics.

Architecture (docs/SCALES_ARCHITECTURE.md): the raw rows are stored as received; EVERYTHING derived (unit kinds, cargo tonnes,
locomotive, GTK train, carriages, assets, flags) is recomputed by `rematch` from raw rows + GTK history + operator corrections.
So a corrected link, a new GTK link or a new alias reaches the past data on the next pass, nothing is edited in place.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, bindparam, delete, func, insert, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkLocomotive, GtkTrainMember
from app.models.identity import User
from app.models.scales import (
    ScaleCargo,
    ScaleCorrection,
    ScalePost,
    ScaleTrain,
    ScaleTrainCarriage,
    ScaleWeighing,
)
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.schemas import scales as schemas
from app.services import scales_matching as matching

REMATCH_BATCH = 400
OPEN_WINDOW_DAYS = 30
GTK_CATCHUP_DAYS = 2
OFFSET_WINDOW_DAYS = 60
BIND_CHUNK = 10000  # ids per IN (...) statement
UPSERT_CHUNK = 1000  # 1000 rows x ~13 columns stays far below the driver's bind-parameter limit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    """The scale PCs store local time without a zone (see `scales_utc_offset_hours`)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone(timedelta(hours=settings.scales_utc_offset_hours)))
    return value.astimezone(timezone.utc)


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, 2)))


def _train_hash(t: schemas.ScaleTrainIn) -> str:
    raw = json.dumps(t.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ───────────────────────── ingest ─────────────────────────

async def _get_or_create_post(db: AsyncSession, payload: schemas.ScalesIngestIn) -> ScalePost:
    post = (await db.execute(select(ScalePost).where(ScalePost.code == payload.post))).scalar_one_or_none()
    if post is None:
        await db.execute(
            pg_insert(ScalePost).values(code=payload.post, name=f"Весы {payload.post}").on_conflict_do_nothing(index_elements=["code"])
        )
        post = (await db.execute(select(ScalePost).where(ScalePost.code == payload.post))).scalar_one()
    return post


async def ingest(db: AsyncSession, payload: schemas.ScalesIngestIn) -> schemas.ScalesIngestResult:
    """Idempotent upsert keyed by (post, scale row id); an unchanged row is not touched, a changed row is re-matched."""
    post = await _get_or_create_post(db, payload)
    changed_trains: set[UUID] = set()

    if payload.cargo:
        stmt = pg_insert(ScaleCargo).values([{"code": c.code, "name": c.name} for c in payload.cargo])
        await db.execute(stmt.on_conflict_do_update(index_elements=["code"], set_={"name": stmt.excluded.name}))

    trains_changed = 0
    if payload.trains:
        rows = [
            {
                "post_id": post.id, "src_id": t.src_id, "registered_on": t.registered_on,
                "loco_number": matching.normalize_loco_number(t.loco_number), "declared_wagons": t.declared_wagons,
                "reported_weight_t": _dec(t.reported_weight_t), "doc_weight_t": _dec(t.doc_weight_t),
                "started_at": _utc(t.started_at), "finished_at": _utc(t.finished_at), "cargo_code": t.cargo_code,
                "excavator": t.excavator, "operator_code": t.operator_code, "row_hash": _train_hash(t),
            }
            for t in payload.trains
        ]
        rows = list({r["src_id"]: r for r in rows}.values())  # one row per key in a single upsert statement
        raw_cols = [c for c in rows[0] if c not in ("post_id", "src_id")]
        for i in range(0, len(rows), UPSERT_CHUNK):
            stmt = pg_insert(ScaleTrain).values(rows[i : i + UPSERT_CHUNK])
            upsert = stmt.on_conflict_do_update(
                constraint="uq_scale_trains_post_src",
                set_={**{c: getattr(stmt.excluded, c) for c in raw_cols}, "updated_at": func.now(), "match_status": "pending"},
                where=ScaleTrain.row_hash != stmt.excluded.row_hash,
            ).returning(ScaleTrain.id)
            changed = (await db.execute(upsert)).scalars().all()
            changed_trains.update(changed)
            trains_changed += len(changed)

    weighings_changed = orphaned = 0
    if payload.weighings:
        wanted = {w.train_src_id for w in payload.weighings}
        id_by_src = {
            src: tid
            for tid, src in (
                await db.execute(select(ScaleTrain.id, ScaleTrain.src_id).where(ScaleTrain.post_id == post.id, ScaleTrain.src_id.in_(wanted)))
            ).all()
        }
        rows = []
        for w in payload.weighings:
            train_id = id_by_src.get(w.train_src_id)
            if train_id is None:
                orphaned += 1
                continue
            rows.append(
                {
                    "train_id": train_id, "src_id": w.src_id, "position": w.position, "unit_label": w.unit_label,
                    "gross_t": _dec(w.gross_t), "tare_t": _dec(w.tare_t), "net_t": _dec(w.net_t), "capacity_t": _dec(w.capacity_t),
                    "overload_t": _dec(w.overload_t), "speed_kmh": _dec(w.speed_kmh), "axles": w.axles, "weighed_at": _utc(w.weighed_at),
                }
            )
        rows = list({(r["train_id"], r["src_id"]): r for r in rows}.values())
        for i in range(0, len(rows), UPSERT_CHUNK):
            stmt = pg_insert(ScaleWeighing).values(rows[i : i + UPSERT_CHUNK])
            cols = [c for c in rows[0] if c not in ("train_id", "src_id")]
            differs = or_(*[getattr(ScaleWeighing, c).is_distinct_from(getattr(stmt.excluded, c)) for c in cols])
            upsert = stmt.on_conflict_do_update(
                constraint="uq_scale_weighings_train_src", set_={c: getattr(stmt.excluded, c) for c in cols}, where=differs
            ).returning(ScaleWeighing.train_id)
            touched = (await db.execute(upsert)).scalars().all()
            weighings_changed += len(touched)
            changed_trains.update(touched)

    # post bookkeeping: the silent-scale alarm reads these
    seen = [t.finished_at or t.started_at for t in payload.trains] + [w.weighed_at for w in payload.weighings]
    last_seen = max((x for x in (_utc(v) for v in seen) if x is not None), default=None)
    values: dict[str, Any] = {"last_pull_at": _now(), "updated_at": _now()}
    if last_seen is not None and (post.last_weighing_at is None or last_seen > post.last_weighing_at):
        values["last_weighing_at"] = last_seen
    if payload.trains:
        values["last_src_train_id"] = max(max(t.src_id for t in payload.trains), post.last_src_train_id or 0)
    if payload.weighings:
        values["last_src_weighing_id"] = max(max(w.src_id for w in payload.weighings), post.last_src_weighing_id or 0)
    if payload.tare_default_t is not None:
        values["tare_default_t"] = _dec(payload.tare_default_t)
    if payload.capacity_norm_t is not None:
        values["capacity_norm_t"] = _dec(payload.capacity_norm_t)
    await db.execute(update(ScalePost).where(ScalePost.id == post.id).values(**values))

    post_code = post.code  # read before commit/expire: no lazy loading in async code
    rematched = await rematch(db, train_ids=changed_trains, include_open=payload.mode == "live")
    await db.commit()
    return schemas.ScalesIngestResult(
        post=post_code, trains_received=len(payload.trains), trains_changed=trains_changed,
        weighings_received=len(payload.weighings), weighings_changed=weighings_changed, weighings_orphaned=orphaned, rematched=rematched,
    )


# ───────────────────────── rematch (all derived data) ─────────────────────────

async def _context(db: AsyncSession) -> dict[str, Any]:
    garage: dict[str, list[int]] = defaultdict(list)
    loco_meta: dict[int, tuple[str | None, str | None]] = {}
    for gtk_id, number, name in (await db.execute(select(GtkLocomotive.gtk_id, GtkLocomotive.garage_number, GtkLocomotive.name))).all():
        loco_meta[gtk_id] = (number, name)
        key = matching.normalize_loco_number(number)
        if key:
            garage[key].append(gtk_id)
    members = [
        matching.Member(m.train_gtk_id, m.kind, m.object_gtk_id, m.is_main, m.ord, m.observed_from, m.observed_to)
        for m in (await db.execute(select(GtkTrainMember))).scalars().all()
    ]
    asset_by_loco: dict[int, UUID] = {}
    asset_by_carriage: dict[int, UUID] = {}
    link_rows = await db.execute(
        select(AssetSourceLink.external_id, AssetSourceLink.asset_id, FixedAsset.asset_type)
        .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
        .where(AssetSourceLink.source == "gtk", AssetSourceLink.status == "active")
    )
    for external_id, asset_id, asset_type in link_rows.all():
        try:
            gtk_id = int(external_id)
        except (TypeError, ValueError):
            continue
        # GTK locomotive and carriage ids are different spaces: the asset type says which one a link is
        (asset_by_loco if asset_type in LOCOMOTIVE_TYPES else asset_by_carriage)[gtk_id] = asset_id
    aliases: dict[str, UUID] = {}
    excluded: set[UUID] = set()
    forced: dict[UUID, int] = {}
    for c in (await db.execute(select(ScaleCorrection).where(ScaleCorrection.is_active))).scalars().all():
        if c.kind == "loco_alias" and c.loco_number:
            aliases[matching.normalize_loco_number(c.loco_number) or c.loco_number] = c.asset_id
        elif c.kind == "train_exclude":
            excluded.add(c.train_id)
        elif c.kind == "train_gtk" and c.gtk_train_id is not None:
            forced[c.train_id] = c.gtk_train_id
    return {
        "garage": garage, "loco_meta": loco_meta, "members": members, "asset_by_loco": asset_by_loco,
        "asset_by_carriage": asset_by_carriage, "aliases": aliases, "excluded": excluded, "forced": forced,
        "loco_gtk_by_asset": {asset: gtk for gtk, asset in asset_by_loco.items()},
    }


async def _offsets(db: AsyncSession) -> dict[UUID, Decimal | None]:
    """Per post: median («Вес» − real net) of complete trains, used to estimate the cargo of trains with missing wagon rows."""
    since = _now() - timedelta(days=OFFSET_WINDOW_DAYS)
    rows = await db.execute(
        select(
            ScaleTrain.post_id,
            func.count(),
            func.percentile_cont(0.5).within_group(ScaleTrain.reported_weight_t - ScaleTrain.net_total_t),
        )
        .where(
            ScaleTrain.net_source == "weighings", ScaleTrain.match_status != "excluded", ScaleTrain.started_at >= since,
            ScaleTrain.reported_weight_t.is_not(None), ScaleTrain.net_total_t.is_not(None),
        )
        .group_by(ScaleTrain.post_id)
    )
    result: dict[UUID, Decimal | None] = {}
    for post_id, n, median in rows.all():
        result[post_id] = Decimal(str(round(float(median), 2))) if median is not None and n >= matching.MIN_OFFSET_SAMPLES else None
    return result


async def rematch(
    db: AsyncSession, *, train_ids: set[UUID] | None = None, include_open: bool = True, everything: bool = False, _second_pass: bool = False
) -> int:
    """Recompute the derived columns for the given trains, plus (by default) every recent unresolved train, or all of them.

    "Unresolved" = not matched yet, or the cargo is still unknown although wagons were declared (the offset that estimates it
    is learned from other trains, so it can appear later: the next pass then fills the gap by itself).
    """
    chosen: set[UUID] = set(train_ids or ())  # explicit ids need no query (and no huge IN (...) list)
    cond = []
    if include_open and not everything:
        since = _now() - timedelta(days=OPEN_WINDOW_DAYS)
        cond.append(and_(ScaleTrain.match_status.in_(("pending", "no_loco")), ScaleTrain.started_at >= since))
        # GTK catches up within hours; older "no GTK train" rows stay as they are until a correction or a full re-match touches them
        cond.append(and_(ScaleTrain.match_status == "no_gtk_train", ScaleTrain.started_at >= _now() - timedelta(days=GTK_CATCHUP_DAYS)))
        cond.append(
            and_(
                ScaleTrain.net_total_t.is_(None), ScaleTrain.declared_wagons > 0, ScaleTrain.match_status != "excluded",
                ScaleTrain.started_at >= since,
            )
        )
    if everything or cond:
        stmt = select(ScaleTrain.id)
        if cond:
            stmt = stmt.where(or_(*cond))
        chosen.update((await db.execute(stmt)).scalars().all())
    if not chosen:
        return 0
    ids = list(chosen)
    ctx = await _context(db)
    offsets = await _offsets(db)
    posts = {p.id: p for p in (await db.execute(select(ScalePost))).scalars().all()}
    tol = timedelta(minutes=settings.scales_gtk_tolerance_min)
    tare_min = settings.scales_traction_tare_min_t
    for start in range(0, len(ids), REMATCH_BATCH):
        batch = ids[start : start + REMATCH_BATCH]
        trains = (await db.execute(select(ScaleTrain).where(ScaleTrain.id.in_(batch)))).scalars().all()
        wrows = (
            await db.execute(
                select(
                    ScaleWeighing.id, ScaleWeighing.train_id, ScaleWeighing.position, ScaleWeighing.gross_t, ScaleWeighing.tare_t,
                    ScaleWeighing.net_t, ScaleWeighing.capacity_t,
                )
                .where(ScaleWeighing.train_id.in_(batch))
            )
        ).all()
        units: dict[UUID, list[matching.Unit]] = defaultdict(list)
        for wid, train_id, position, gross, tare, net, capacity in wrows:
            units[train_id].append(matching.Unit(gross, tare, net, capacity, position, wid))
        for train_units in units.values():  # a stable order: by position, then by id
            train_units.sort(key=lambda u: (u.position if u.position is not None else 10**6, u.ref))
        kind_of: dict[Any, str] = {}
        updates: list[dict[str, Any]] = []
        carriage_rows: list[dict[str, Any]] = []
        for t in trains:
            post = posts.get(t.post_id)
            train_units = units.get(t.id, [])

            def summarize(hint: int | None = None, _t=t, _u=train_units, _p=post) -> matching.TrainSummary:
                return matching.summarize_train(
                    _u, tare_min=tare_min, tare_default=_p.tare_default_t if _p else None, declared_wagons=_t.declared_wagons,
                    reported_weight_t=_t.reported_weight_t, offset_t=offsets.get(_t.post_id), traction_hint=hint,
                )

            summary = summarize()
            result = matching.match_train(
                number=t.loco_number, started_at=t.started_at, finished_at=t.finished_at, dump_count=summary.dump_count,
                excluded=t.id in ctx["excluded"], forced_gtk_train=ctx["forced"].get(t.id), tolerance=tol, members=ctx["members"],
                aliases=ctx["aliases"], garage_index=ctx["garage"], asset_by_loco_gtk=ctx["asset_by_loco"],
                loco_gtk_by_asset=ctx["loco_gtk_by_asset"],
            )
            if result.status == "ok" and train_units and not {"no_wagon_rows", "partial_wagon_rows"} & set(summary.flags):
                # GTK is the truth about how many cars the train has: the other weighed units are the traction aggregate
                extra = len(train_units) - len(result.carriages)
                if 1 <= extra <= 3 and extra != summary.traction_count:
                    summary = summarize(extra)
            flags = set(summary.flags) | set(result.flags)
            if result.status == "ok":
                flags.discard("count_mismatch")  # recomputed against the final dump count
                if summary.dump_count and summary.dump_count != len(result.carriages):
                    flags.add("count_mismatch")
            for unit, kind in zip(train_units, summary.kinds):
                kind_of[unit.ref] = kind
            dump_units = [u for u, k in zip(train_units, summary.kinds) if k == "dump"]
            paired = {
                c.object_gtk_id: u
                for c, u in matching.assign_units_to_carriages(
                    dump_units if "partial_wagon_rows" not in summary.flags else [], result.carriages, order=settings.scales_carriage_order
                )
            }
            linked = 0
            for m in result.carriages:
                asset = ctx["asset_by_carriage"].get(m.object_gtk_id)
                linked += asset is not None
                unit = paired.get(m.object_gtk_id)
                carriage_rows.append(
                    {
                        "train_id": t.id, "carriage_gtk_id": m.object_gtk_id, "asset_id": asset, "ord": m.ord,
                        "unit_position": unit.position if unit else None, "net_t": unit.net if unit else None,
                    }
                )
            updates.append(
                {
                    "b_id": t.id, "wagon_rows": len(units.get(t.id, [])), "dump_count": summary.dump_count,
                    "traction_count": summary.traction_count, "net_total_t": summary.net_total_t, "net_source": summary.net_source,
                    "loco_asset_id": result.loco_asset_id, "loco_gtk_id": result.loco_gtk_id, "gtk_train_id": result.gtk_train_id,
                    "carriages_total": len(result.carriages), "carriages_linked": linked, "match_status": result.status,
                    "match_method": result.method, "flags": sorted(flags), "matched_at": _now(),
                }
            )
        for kind in ("traction", "dump"):  # write the final unit kinds back in two statements
            ids_of_kind = [ref for ref, k in kind_of.items() if k == kind]
            if ids_of_kind:
                await db.execute(update(ScaleWeighing.__table__).where(ScaleWeighing.__table__.c.id.in_(ids_of_kind)).values(unit_kind=kind))
        await db.execute(delete(ScaleTrainCarriage).where(ScaleTrainCarriage.train_id.in_(batch)))
        if carriage_rows:
            await db.execute(insert(ScaleTrainCarriage.__table__), carriage_rows)
        await db.execute(update(ScaleTrain.__table__).where(ScaleTrain.__table__.c.id == bindparam("b_id")), updates)
    db.expire_all()  # the derived columns were written with Core statements: drop stale ORM copies
    if not _second_pass:
        # trains of this very batch taught the offset: estimate what could not be estimated a moment ago
        learned = await _offsets(db)
        if any(v is not None for v in learned.values()):
            late: set[UUID] = set()
            learned_posts = [k for k, v in learned.items() if v is not None]
            for i in range(0, len(ids), BIND_CHUNK):  # never one IN (...) over every id: the driver allows 32767 parameters
                found = await db.execute(
                    select(ScaleTrain.id).where(
                        ScaleTrain.id.in_(ids[i : i + BIND_CHUNK]), ScaleTrain.net_total_t.is_(None), ScaleTrain.declared_wagons > 0,
                        ScaleTrain.match_status != "excluded", ScaleTrain.post_id.in_(learned_posts),
                    )
                )
                late.update(found.scalars().all())
            if late:
                await rematch(db, train_ids=late, include_open=False, _second_pass=True)
    return len(ids)


async def rematch_all(db: AsyncSession) -> int:
    count = await rematch(db, everything=True)
    await db.commit()
    return count


# ───────────────────────── reads ─────────────────────────

def _health(silent_hours: float | None) -> str:
    if silent_hours is None:
        return "unknown"
    if silent_hours >= settings.scales_silent_alert_hours:
        return "alert"
    if silent_hours >= settings.scales_silent_warn_hours:
        return "warn"
    return "ok"


async def _gtk_history_start(db: AsyncSession) -> datetime | None:
    """GTK keeps the train composition history only from when TOIR started to mirror it; older weighings cannot be matched at all."""
    return (await db.execute(select(func.min(GtkTrainMember.observed_from)))).scalar_one()


def _needs_attention(history_start: datetime | None):
    """Trains an operator can still do something about: no locomotive, or no GTK train although GTK history covers that time."""
    waiting = ScaleTrain.match_status.in_(("pending", "no_loco"))
    if history_start is None:
        return waiting
    return or_(waiting, and_(ScaleTrain.match_status == "no_gtk_train", ScaleTrain.started_at >= history_start))


async def get_status(db: AsyncSession) -> schemas.ScalesStatus:
    now = _now()
    history_start = await _gtk_history_start(db)
    attention = _needs_attention(history_start)
    day, week = now - timedelta(hours=24), now - timedelta(days=7)
    posts = (await db.execute(select(ScalePost).order_by(ScalePost.code))).scalars().all()
    live = ScaleTrain.match_status != "excluded"
    stats = {
        row[0]: row
        for row in (
            await db.execute(
                select(
                    ScaleTrain.post_id,
                    func.count().filter(ScaleTrain.started_at >= day, live),
                    func.coalesce(func.sum(ScaleTrain.net_total_t).filter(ScaleTrain.started_at >= day, live), 0),
                    func.count().filter(ScaleTrain.started_at >= week, live),
                    func.count().filter(ScaleTrain.started_at >= week, ScaleTrain.match_status == "ok"),
                    func.count().filter(attention),
                ).group_by(ScaleTrain.post_id)
            )
        ).all()
    }
    items: list[schemas.PostStatus] = []
    for p in posts:
        s = stats.get(p.id)
        silent = (now - p.last_weighing_at).total_seconds() / 3600 if p.last_weighing_at else None
        pull_age = (now - p.last_pull_at).total_seconds() / 60 if p.last_pull_at else None
        items.append(
            schemas.PostStatus(
                code=p.code, name=p.name, last_weighing_at=p.last_weighing_at, last_pull_at=p.last_pull_at,
                silent_hours=None if silent is None else round(silent, 1), health=_health(silent),  # type: ignore[arg-type]
                collector="never" if pull_age is None else ("ok" if pull_age <= 10 else "stale"),
                trains_24h=s[1] if s else 0, tonnes_24h=Decimal(str(s[2] if s else 0)), trains_7d=s[3] if s else 0,
                match_rate_7d=round(s[4] / s[3], 3) if s and s[3] else None, unmatched=s[5] if s else 0,
            )
        )
    old_filter = (ScaleTrain.match_status == "no_gtk_train", ScaleTrain.started_at < history_start) if history_start else (ScaleTrain.id.is_(None),)
    total, unmatched, before, first, last = (
        await db.execute(
            select(
                func.count(), func.count().filter(attention), func.count().filter(*old_filter),
                func.min(ScaleTrain.started_at), func.max(ScaleTrain.started_at),
            )
        )
    ).one()
    return schemas.ScalesStatus(
        posts=items, trains_total=total, unmatched_total=unmatched, before_gtk_history=before, gtk_history_from=history_start,
        first_train_at=first, last_train_at=last,
    )


TRAIN_SORT = {
    "started_at": ScaleTrain.started_at, "loco_number": ScaleTrain.loco_number, "net_total_t": ScaleTrain.net_total_t,
    "match_status": ScaleTrain.match_status,
}


def _train_read(row: Any, cargo: dict[int, str]) -> dict[str, Any]:
    t, post_code, inv = row
    return {
        "id": t.id, "post_code": post_code, "src_id": t.src_id, "started_at": t.started_at, "finished_at": t.finished_at,
        "loco_number": t.loco_number, "loco_asset_id": t.loco_asset_id, "loco_inv_number": inv, "gtk_train_id": t.gtk_train_id,
        "declared_wagons": t.declared_wagons, "wagon_rows": t.wagon_rows, "dump_count": t.dump_count,
        "traction_count": t.traction_count, "carriages_total": t.carriages_total, "carriages_linked": t.carriages_linked,
        "reported_weight_t": t.reported_weight_t, "net_total_t": t.net_total_t, "net_source": t.net_source,
        "cargo_name": cargo.get(t.cargo_code) if t.cargo_code is not None else None, "excavator": t.excavator,
        "match_status": t.match_status, "match_method": t.match_method, "flags": list(t.flags or []),
    }


def _train_select():
    return (
        select(ScaleTrain, ScalePost.code, FixedAsset.inv_number)
        .join(ScalePost, ScalePost.id == ScaleTrain.post_id)
        .outerjoin(FixedAsset, FixedAsset.id == ScaleTrain.loco_asset_id)
    )


async def _cargo_names(db: AsyncSession) -> dict[int, str]:
    return {c: n for c, n in (await db.execute(select(ScaleCargo.code, ScaleCargo.name))).all()}


async def list_trains(
    db: AsyncSession, *, post: str | None, match_status: str | None, flag: str | None, q: str | None,
    date_from: date | None, date_to: date | None, sort_by: str, descending: bool, limit: int, offset: int,
) -> schemas.ScaleTrainPage:
    if sort_by not in TRAIN_SORT:
        raise HTTPException(status_code=422, detail=f"Unknown sort field: {sort_by}")
    cond = []
    if post:
        cond.append(ScalePost.code == post)
    if match_status:
        cond.append(ScaleTrain.match_status == match_status)
    if flag:
        cond.append(ScaleTrain.flags.any(flag))
    if q:
        cond.append(ScaleTrain.loco_number.ilike(f"%{q.strip()}%".replace("\x00", "")))
    if date_from:
        cond.append(ScaleTrain.started_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        cond.append(ScaleTrain.started_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    total = (
        await db.execute(select(func.count()).select_from(ScaleTrain).join(ScalePost, ScalePost.id == ScaleTrain.post_id).where(*cond))
    ).scalar_one()
    column = TRAIN_SORT[sort_by]
    order = column.desc().nullslast() if descending else column.asc().nullslast()
    rows = (await db.execute(_train_select().where(*cond).order_by(order, ScaleTrain.id).limit(limit).offset(offset))).all()
    cargo = await _cargo_names(db)
    return schemas.ScaleTrainPage(items=[schemas.ScaleTrainRead(**_train_read(r, cargo)) for r in rows], total=total, limit=limit, offset=offset)


async def list_unmatched(db: AsyncSession, *, limit: int, offset: int) -> schemas.UnmatchedPage:
    """Trains the system could not place, with GTK locomotives that were working at that time as suggested aliases."""
    attention = and_(_needs_attention(await _gtk_history_start(db)), ScaleTrain.match_status != "pending")
    total = (await db.execute(select(func.count()).select_from(ScaleTrain).where(attention))).scalar_one()
    rows = (await db.execute(_train_select().where(attention).order_by(ScaleTrain.started_at.desc().nullslast()).limit(limit).offset(offset))).all()
    cargo = await _cargo_names(db)
    ctx = await _context(db)
    tol = timedelta(minutes=settings.scales_gtk_tolerance_min)
    items: list[schemas.UnmatchedTrain] = []
    for row in rows:
        t = row[0]
        win = matching.window(t.started_at, t.finished_at, tol)
        candidates = []
        for loco_gtk, _train, seconds in matching.suggest_locos(ctx["members"], win):
            number, name = ctx["loco_meta"].get(loco_gtk, (None, None))
            asset = ctx["asset_by_loco"].get(loco_gtk)
            inv = None
            if asset is not None:
                inv = (await db.execute(select(FixedAsset.inv_number).where(FixedAsset.id == asset))).scalar_one_or_none()
            candidates.append(
                schemas.LocoCandidate(
                    loco_gtk_id=loco_gtk, garage_number=number, name=name, asset_id=asset, asset_inv_number=inv, overlap_min=round(seconds / 60, 1)
                )
            )
        items.append(schemas.UnmatchedTrain(**_train_read(row, cargo), candidates=candidates))
    return schemas.UnmatchedPage(items=items, total=total, limit=limit, offset=offset)


# ───────────────────────── corrections ─────────────────────────

async def list_corrections(db: AsyncSession, *, active_only: bool = True) -> list[schemas.CorrectionRead]:
    stmt = select(ScaleCorrection, FixedAsset.inv_number).outerjoin(FixedAsset, FixedAsset.id == ScaleCorrection.asset_id)
    if active_only:
        stmt = stmt.where(ScaleCorrection.is_active)
    rows = (await db.execute(stmt.order_by(ScaleCorrection.created_at.desc()))).all()
    result = []
    for c, inv in rows:
        item = schemas.CorrectionRead.model_validate(c)
        item.asset_inv_number = inv
        result.append(item)
    return result


async def create_correction(db: AsyncSession, user: User, payload: schemas.CorrectionCreate) -> schemas.CorrectionRead:
    """Corrections are re-applied by every later pass; creating one re-matches only what it can change."""
    affected: set[UUID] = set()
    if payload.kind == "loco_alias":
        number = matching.normalize_loco_number(payload.loco_number)
        if number is None or payload.asset_id is None:
            raise HTTPException(status_code=422, detail="loco_alias needs loco_number and asset_id")
        asset_type = (await db.execute(select(FixedAsset.asset_type).where(FixedAsset.id == payload.asset_id))).scalar_one_or_none()
        if asset_type is None:
            raise HTTPException(status_code=422, detail="Fixed asset does not exist")
        if asset_type not in LOCOMOTIVE_TYPES:
            raise HTTPException(status_code=422, detail="The alias target must be a locomotive")
        values = {"kind": "loco_alias", "loco_number": number, "asset_id": payload.asset_id}
        affected = set((await db.execute(select(ScaleTrain.id).where(ScaleTrain.loco_number.in_(matching.loco_keys(number))))).scalars().all())
    else:
        if payload.train_id is None or (await db.execute(select(ScaleTrain.id).where(ScaleTrain.id == payload.train_id))).scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Train not found")
        if payload.kind == "train_gtk" and payload.gtk_train_id is None:
            raise HTTPException(status_code=422, detail="train_gtk needs gtk_train_id")
        values = {"kind": payload.kind, "train_id": payload.train_id, "gtk_train_id": payload.gtk_train_id if payload.kind == "train_gtk" else None}
        affected = {payload.train_id}
    # one active correction per key: the new one replaces the old
    key = (
        and_(ScaleCorrection.kind == "loco_alias", ScaleCorrection.loco_number == values["loco_number"])
        if payload.kind == "loco_alias"
        else and_(ScaleCorrection.kind == payload.kind, ScaleCorrection.train_id == payload.train_id)
    )
    await db.execute(update(ScaleCorrection).where(key, ScaleCorrection.is_active).values(is_active=False, ended_at=_now()))
    correction = ScaleCorrection(**values, note=payload.note, created_by=user.id)
    db.add(correction)
    await db.flush()
    correction_id = correction.id  # read before commit/expire: no lazy loading in async code
    await rematch(db, train_ids=affected, include_open=False)
    await db.commit()
    return await _correction_read(db, correction_id)


async def _correction_read(db: AsyncSession, correction_id: UUID) -> schemas.CorrectionRead:
    for item in await list_corrections(db, active_only=False):
        if item.id == correction_id:
            return item
    raise HTTPException(status_code=404, detail="Correction not found")


async def end_correction(db: AsyncSession, correction_id: UUID) -> None:
    c = (await db.execute(select(ScaleCorrection).where(ScaleCorrection.id == correction_id, ScaleCorrection.is_active))).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Correction not found")
    c.is_active = False
    c.ended_at = _now()
    affected: set[UUID] = set()
    if c.kind == "loco_alias" and c.loco_number:
        affected = set((await db.execute(select(ScaleTrain.id).where(ScaleTrain.loco_number.in_(matching.loco_keys(c.loco_number))))).scalars().all())
    elif c.train_id is not None:
        affected = {c.train_id}
    await db.flush()
    await rematch(db, train_ids=affected, include_open=False)
    await db.commit()


# ───────────────────────── work metrics ─────────────────────────

async def asset_work(db: AsyncSession, asset_id: UUID, date_from: date, date_to: date) -> schemas.AssetWorkRead:
    asset_type = (await db.execute(select(FixedAsset.asset_type).where(FixedAsset.id == asset_id))).scalar_one_or_none()
    if asset_type is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    lo = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
    hi = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    day = func.date_trunc("day", ScaleTrain.started_at + timedelta(hours=settings.scales_utc_offset_hours))
    if asset_type in LOCOMOTIVE_TYPES:
        kind = "locomotive"
        base = select(ScaleTrain.started_at, ScaleTrain.net_total_t.label("tonnes"), ScaleTrain.net_source, day.label("day"), literal(None).label("own")).where(
            ScaleTrain.loco_asset_id == asset_id, ScaleTrain.match_status.in_(("ok", "no_gtk_train")), ScaleTrain.started_at >= lo, ScaleTrain.started_at < hi
        )
    else:
        kind = "wagon"
        # the car's own weighing when it was paired by GTK order, otherwise the train average
        per_car = func.coalesce(
            ScaleTrainCarriage.net_t,
            ScaleTrain.net_total_t / func.nullif(func.coalesce(func.nullif(ScaleTrain.dump_count, 0), func.nullif(ScaleTrain.carriages_total, 0)), 0),
        )
        base = (
            select(ScaleTrain.started_at, per_car.label("tonnes"), ScaleTrain.net_source, day.label("day"), ScaleTrainCarriage.net_t.label("own"))
            .join(ScaleTrainCarriage, ScaleTrainCarriage.train_id == ScaleTrain.id)
            .where(ScaleTrainCarriage.asset_id == asset_id, ScaleTrain.match_status == "ok", ScaleTrain.started_at >= lo, ScaleTrain.started_at < hi)
        )
    rows = (await db.execute(base)).all()
    trips = len(rows)
    tonnes = sum((Decimal(str(r.tonnes)) for r in rows if r.tonnes is not None), Decimal(0)).quantize(Decimal("0.01"))
    per_day: dict[date, list[Any]] = defaultdict(list)
    for r in rows:
        per_day[r.day.date()].append(r)
    daily = [
        schemas.WorkDay(day=d, trips=len(v), tonnes=sum((Decimal(str(r.tonnes)) for r in v if r.tonnes is not None), Decimal(0)).quantize(Decimal("0.01")))
        for d, v in sorted(per_day.items())
    ]
    estimated = sum(1 for r in rows if r.net_source == "estimated")
    times = [r.started_at for r in rows if r.started_at]
    return schemas.AssetWorkRead(
        asset_id=asset_id, kind=kind, date_from=date_from, date_to=date_to, trips=trips, tonnes=tonnes,  # type: ignore[arg-type]
        avg_tonnes_per_trip=(tonnes / trips).quantize(Decimal("0.01")) if trips else None,
        estimated_share=round(estimated / trips, 3) if trips else None,
        exact_share=round(sum(1 for r in rows if r.own is not None) / trips, 3) if trips and kind == "wagon" else None, first_at=min(times, default=None), last_at=max(times, default=None), daily=daily,
    )


async def daily_summary(db: AsyncSession, days: int) -> list[schemas.DaySummary]:
    since = _now() - timedelta(days=days)
    day = func.date_trunc("day", ScaleTrain.started_at + timedelta(hours=settings.scales_utc_offset_hours))
    rows = await db.execute(
        select(day, ScalePost.code, func.count(), func.coalesce(func.sum(ScaleTrain.net_total_t), 0))
        .join(ScalePost, ScalePost.id == ScaleTrain.post_id)
        .where(ScaleTrain.started_at >= since, ScaleTrain.match_status != "excluded", ScaleTrain.dump_count > 0)
        .group_by(day, ScalePost.code)
        .order_by(day, ScalePost.code)
    )
    return [schemas.DaySummary(day=d.date(), post_code=code, trains=n, tonnes=Decimal(str(t))) for d, code, n, t in rows.all()]
