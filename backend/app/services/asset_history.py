"""Asset history: join the GTK train membership history, the position track and the scale weighings into one timeline.

Wagon: every membership of its carriage in a GTK train is a segment (behind which locomotive, how many cars); the wagon's position
during a segment is the locomotive's track; its own fixes (GTK carriage coordinates) and the weighings are added.
Locomotive: every train it headed is a segment, with the wagons it pulled and its own track.
What can be answered depends on what was stored: GTK compositions since the GTK mirror started, positions since the position
history started (plus the Wialon backfill); the response says from when (`gtk_history_from`, `track_from`).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.identity import User
from app.models.position_history import AssetPositionHistory
from app.models.scales import ScaleCargo, ScalePost, ScaleTrain
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.schemas import asset_history as h
from app.schemas import scales_insights as si
from app.services import position_history as ph
from app.services import scales_insights as insights
from app.services import scales_trips as trips

MOVING_KM = 0.3  # a segment is «moving» when its locomotive travelled at least this far
MAX_TRACK_POINTS = 4000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scope(user: User) -> UUID | None:
    if user.role != "master":
        return None
    if user.section_id is None:
        raise HTTPException(status_code=403, detail="Master user must be assigned to a section")
    return user.section_id


def _km(points: list[tuple[datetime, float, float, float | None]]) -> float | None:
    if len(points) < 2:
        return None
    return round(sum(ph.haversine_m(a[1], a[2], b[1], b[2]) for a, b in zip(points, points[1:])) / 1000, 2)


def _activity(km: float | None, n: int) -> str:
    if n == 0:
        return "unknown"
    return "moving" if (km or 0) >= MOVING_KM else "standing"


async def _loco_labels(db: AsyncSession, gtk_ids: set[int]) -> dict[int, tuple[UUID | None, str | None, str]]:
    """GTK locomotive id -> (TOIR asset, inventory number, human label)."""
    if not gtk_ids:
        return {}
    locos = {g.gtk_id: g for g in (await db.execute(select(GtkLocomotive).where(GtkLocomotive.gtk_id.in_(gtk_ids)))).scalars().all()}
    links = {
        int(ext): (asset, inv)
        for ext, asset, inv in (
            await db.execute(
                select(AssetSourceLink.external_id, AssetSourceLink.asset_id, FixedAsset.inv_number)
                .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
                .where(AssetSourceLink.source == "gtk", AssetSourceLink.status == "active", FixedAsset.asset_type.in_(LOCOMOTIVE_TYPES))
            )
        ).all()
        if str(ext).isdigit() and int(ext) in gtk_ids
    }
    out: dict[int, tuple[UUID | None, str | None, str]] = {}
    for gid in gtk_ids:
        g = locos.get(gid)
        asset, inv = links.get(gid, (None, None))
        label = (g.name if g and g.name else None) or (f"гар. {g.garage_number}" if g and g.garage_number else f"GTK {gid}")
        out[gid] = (asset, inv, label)
    return out


def _overlap(a_from: datetime, a_to: datetime, b_from: datetime, b_to: datetime) -> float:
    return max(0.0, (min(a_to, b_to) - max(a_from, b_from)).total_seconds())


async def asset_history(db: AsyncSession, user: User, *, asset_id: UUID | None, carriage_gtk_id: int | None, days: int) -> h.AssetHistory:
    if asset_id is None and carriage_gtk_id is None:
        raise HTTPException(status_code=422, detail="asset_id or carriage_gtk_id is required")
    scope = _scope(user)
    identity = await insights._identity(db, asset_id) if asset_id else None
    if asset_id and identity is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    if scope is not None and (identity is None or identity.section_id != scope):
        raise HTTPException(status_code=404, detail="Asset not found")  # another section's asset (or an unlinked one) is invisible to a master
    is_loco = identity is not None and identity.asset_type in LOCOMOTIVE_TYPES
    now = _now()
    lo = now - timedelta(days=days)
    history_from = (await db.execute(select(func.min(GtkTrainMember.observed_from)))).scalar_one()

    gtk_id: int | None = carriage_gtk_id
    if asset_id and gtk_id is None:
        link = (await db.execute(select(AssetSourceLink.external_id).where(AssetSourceLink.asset_id == asset_id, AssetSourceLink.source == "gtk", AssetSourceLink.status == "active"))).scalar_one_or_none()
        gtk_id = int(link) if link and str(link).isdigit() else None
    gtk_carriage = gtk_loco = None
    if not is_loco and gtk_id is not None:
        c = (await db.execute(select(GtkCarriage).where(GtkCarriage.gtk_id == gtk_id))).scalar_one_or_none()
        if c is not None:
            gtk_carriage = si.GtkCarriageInfo(
                carriage_gtk_id=c.gtk_id, name=c.name, reg_number=c.reg_number, inventory_number=c.inventory_number, model_name=c.model_name,
                is_active=c.is_active, is_loaded=c.is_loaded, lat=c.lat, lon=c.lon,
            )
    if is_loco and gtk_id is not None:
        g = (await db.execute(select(GtkLocomotive).where(GtkLocomotive.gtk_id == gtk_id))).scalar_one_or_none()
        if g is not None:
            gtk_loco = si.GtkLocoInfo(gtk_id=g.gtk_id, name=g.name, garage_number=g.garage_number, model_name=g.model_name, is_active=g.is_active)
    if identity is None and gtk_carriage is None:
        raise HTTPException(status_code=404, detail="Wagon not found")

    # ── segments from the GTK membership history ──
    seg_specs: list[dict] = []  # {train, from, to, loco_gtk, cars}
    member_kind = "locomotive" if is_loco else "carriage"
    if gtk_id is not None:
        member_filter = [GtkTrainMember.kind == member_kind, GtkTrainMember.object_gtk_id == gtk_id, GtkTrainMember.observed_from <= now, or_(GtkTrainMember.observed_to.is_(None), GtkTrainMember.observed_to >= lo)]
        if is_loco:
            member_filter.append(GtkTrainMember.is_main)
        mine = (await db.execute(select(GtkTrainMember).where(*member_filter).order_by(GtkTrainMember.observed_from))).scalars().all()
        train_ids = {m.train_gtk_id for m in mine}
        loco_members = defaultdict(list)
        car_members = defaultdict(list)
        if train_ids:
            for m in (await db.execute(select(GtkTrainMember).where(GtkTrainMember.train_gtk_id.in_(train_ids), or_(GtkTrainMember.observed_to.is_(None), GtkTrainMember.observed_to >= lo)))).scalars().all():
                if m.kind == "locomotive" and m.is_main:
                    loco_members[m.train_gtk_id].append(m)
                elif m.kind == "carriage":
                    car_members[m.train_gtk_id].append(m)
        for m in mine:
            start = max(m.observed_from, lo)
            end = m.observed_to or now
            if is_loco:
                loco_gtk = gtk_id
            else:
                best = max(loco_members.get(m.train_gtk_id, []), key=lambda x: _overlap(start, end, x.observed_from, x.observed_to or now), default=None)
                loco_gtk = best.object_gtk_id if best is not None and _overlap(start, end, best.observed_from, best.observed_to or now) > 0 else None
            cars_here = {c.object_gtk_id for c in car_members.get(m.train_gtk_id, []) if _overlap(start, end, c.observed_from, c.observed_to or now) > 0}
            seg_specs.append({"train": m.train_gtk_id, "from": start, "to": m.observed_to, "end": end, "loco_gtk": loco_gtk, "cars": cars_here})
    titles = {t.gtk_id: t.title or (f"№ {t.number}" if t.number else None) for t in (await db.execute(select(GtkTrain).where(GtkTrain.gtk_id.in_({s["train"] for s in seg_specs})))).scalars().all()} if seg_specs else {}
    labels = await _loco_labels(db, {s["loco_gtk"] for s in seg_specs if s["loco_gtk"] is not None})

    # ── track points: the asset's own, plus the locomotives' during the segments ──
    loco_assets = {labels[s["loco_gtk"]][0] for s in seg_specs if s["loco_gtk"] in labels and labels[s["loco_gtk"]][0]}
    wanted = set(loco_assets) | ({asset_id} if asset_id else set())
    # when the stored track of THESE assets begins (a global minimum would be an old stale fix of some silent unit)
    track_from = (await db.execute(select(func.min(AssetPositionHistory.at)).where(AssetPositionHistory.asset_id.in_(wanted)))).scalar_one() if wanted else None
    raw: dict[UUID, list[tuple[datetime, float, float, float | None]]] = defaultdict(list)
    if wanted:
        for a, at, lat, lon, speed in (
            await db.execute(select(AssetPositionHistory.asset_id, AssetPositionHistory.at, AssetPositionHistory.lat, AssetPositionHistory.lon, AssetPositionHistory.speed).where(AssetPositionHistory.asset_id.in_(wanted), AssetPositionHistory.at >= lo).order_by(AssetPositionHistory.at))
        ).all():
            raw[a].append((at, float(lat), float(lon), None if speed is None else float(speed)))

    # ── weighings (scale trips) ──
    stmt_rows = []
    if is_loco and asset_id:
        t = ScaleTrain
        stmt_rows = (
            await db.execute(
                select(t.id, t.started_at, ScalePost.code, t.net_total_t, t.net_source, t.loco_number, ScaleCargo.name, func.coalesce(func.nullif(t.dump_count, 0), func.nullif(t.carriages_total, 0)))
                .join(ScalePost, ScalePost.id == t.post_id).outerjoin(ScaleCargo, ScaleCargo.code == t.cargo_code)
                .where(t.loco_asset_id == asset_id, t.match_status.in_(("ok", "no_gtk_train")), t.started_at >= lo).order_by(t.started_at.desc())
            )
        ).all()
        trip_items = [h.HistoryTrip(train_id=r[0], started_at=r[1], post_code=r[2], tonnes=None if r[3] is None else Decimal(str(r[3])), basis=r[4], loco_number=r[5], cargo_name=r[6], cars=r[7]) for r in stmt_rows]
    else:
        stmt, _tonnes, _wagon = trips._trip_select(asset_id=asset_id, q=None, date_from=None, date_to=None, post=None, cargo_code=None, only_linked=False, carriage_gtk_id=None if asset_id else gtk_id)
        rows = (await db.execute(stmt.where(ScaleTrain.started_at >= lo).order_by(ScaleTrain.started_at.desc()))).all()
        trip_items = [h.HistoryTrip(train_id=r.train_id, started_at=r.started_at, post_code=r.post_code, tonnes=None if r.tonnes is None else Decimal(str(r.tonnes)), basis=r.basis, loco_number=r.loco_number, cargo_name=r.cargo_name, cars=None) for r in rows]

    # ── wagons pulled (locomotive history) ──
    pulled: dict[int, list[h.WagonRef]] = {}
    if is_loco and seg_specs:
        all_cars = {c for s in seg_specs for c in s["cars"]}
        names = {c.gtk_id: c.name for c in (await db.execute(select(GtkCarriage).where(GtkCarriage.gtk_id.in_(all_cars)))).scalars().all()} if all_cars else {}
        inv = {int(ext): (asset, i) for ext, asset, i in (await db.execute(select(AssetSourceLink.external_id, AssetSourceLink.asset_id, FixedAsset.inv_number).join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id).where(AssetSourceLink.source == "gtk", AssetSourceLink.status == "active", FixedAsset.asset_type.notin_(LOCOMOTIVE_TYPES)))).all() if str(ext).isdigit() and int(ext) in all_cars}
        for s in seg_specs:
            pulled[id(s)] = [h.WagonRef(carriage_gtk_id=c, asset_id=inv[c][0] if c in inv else None, label=inv[c][1] if c in inv else (names.get(c) or f"GTK {c}")) for c in sorted(s["cars"])][:30]

    segments: list[h.HistorySegment] = []
    track_rows: list[h.HistoryPoint] = []
    for s in seg_specs:
        loco_asset, loco_inv, loco_label = labels.get(s["loco_gtk"], (None, None, None)) if s["loco_gtk"] is not None else (None, None, None)
        source_asset = asset_id if is_loco else loco_asset
        pts = [p for p in raw.get(source_asset, []) if s["from"] <= p[0] <= s["end"]] if source_asset else []
        km = _km(pts)
        in_seg = [t for t in trip_items if t.started_at and s["from"] <= t.started_at <= s["end"]]
        segments.append(
            h.HistorySegment(
                from_at=s["from"], to_at=s["to"], is_open=s["to"] is None, train_gtk_id=s["train"], train_title=titles.get(s["train"]),
                loco_asset_id=loco_asset, loco_inv_number=loco_inv, loco_label=loco_label, cars=len(s["cars"]), km=km,
                max_speed=max((p[3] for p in pts if p[3] is not None), default=None), points=len(pts), activity=_activity(km, len(pts)),
                trips=len(in_seg), tonnes=sum((t.tonnes or Decimal(0) for t in in_seg), Decimal(0)).quantize(Decimal("0.01")), wagons=pulled.get(id(s), []),
            )
        )
        if not is_loco:
            track_rows += [h.HistoryPoint(at=p[0], lat=p[1], lon=p[2], speed=p[3], source="loco", label=loco_label) for p in pts]
    if is_loco and asset_id:
        track_rows = [h.HistoryPoint(at=p[0], lat=p[1], lon=p[2], speed=p[3], source="own") for p in raw.get(asset_id, [])]
    elif asset_id:
        track_rows += [h.HistoryPoint(at=p[0], lat=p[1], lon=p[2], speed=p[3], source="own") for p in raw.get(asset_id, [])]
    track_rows.sort(key=lambda p: p.at)
    if len(track_rows) > MAX_TRACK_POINTS:
        step = len(track_rows) // MAX_TRACK_POINTS + 1
        track_rows = track_rows[::step] + [track_rows[-1]]

    current = None
    if track_rows:
        last = track_rows[-1]
        open_seg = next((s for s in segments if s.is_open), None)
        current = h.HistoryCurrent(lat=last.lat, lon=last.lon, at=last.at, source=last.source, in_train=open_seg is not None, loco_label=open_seg.loco_label if open_seg else None, speed=last.speed)
    shares: dict[tuple[UUID | None, str], list[float]] = defaultdict(list)
    for s in segments:
        shares[(s.loco_asset_id, s.loco_label or "локомотив не определён")].append(((s.to_at or now) - s.from_at).total_seconds() / 3600)
    by_loco = sorted((h.LocoShare(loco_asset_id=k[0], label=k[1], hours=round(sum(v), 1), segments=len(v)) for k, v in shares.items()), key=lambda x: -x.hours)
    moved = [p.at for p, q in zip(track_rows, track_rows[1:]) if ph.haversine_m(p.lat, p.lon, q.lat, q.lon) >= ph.MIN_MOVE_M]
    partners = len({w.carriage_gtk_id for s in segments for w in s.wagons}) if is_loco else len({s.loco_asset_id or s.loco_label for s in segments if s.loco_label})
    return h.AssetHistory(
        kind="locomotive" if is_loco else "wagon", asset=identity, gtk_carriage=gtk_carriage, gtk_loco=gtk_loco, date_from=lo.date(), date_to=now.date(),
        days=days, gtk_history_from=history_from, track_from=track_from, current=current, segments=sorted(segments, key=lambda s: s.from_at, reverse=True), trips=trip_items[:100],
        track=track_rows, by_loco=by_loco,
        stats=h.HistoryStats(
            segments=len(segments), coupled_hours=round(sum(((s.to_at or now) - s.from_at).total_seconds() / 3600 for s in segments), 1), km=round(sum(s.km or 0 for s in segments), 1),
            distinct_partners=partners, trips=len(trip_items), tonnes=sum((t.tonnes or Decimal(0) for t in trip_items), Decimal(0)).quantize(Decimal("0.01")), last_move_at=moved[-1] if moved else None,
        ),
    )
