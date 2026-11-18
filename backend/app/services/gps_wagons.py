"""Wagons on the GPS page: no own GPS anywhere, so position and kilometres are derived from the locomotive of the train (GTK membership)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_models import AssetModel  # noqa: F401  (keeps the mapper registry complete)
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.gtk import GtkCarriage, GtkTrain, GtkTrainMember
from app.models.gtk_gps import GpsWagonSegment
from app.models.identity import User
from app.models.localization import FixedAssetTypeTranslation
from app.models.organization import Section
from app.repositories import gps as gps_repository
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.schemas.gps import GpsFix, GpsWagonDetail, GpsWagonPage, GpsWagonRow, GpsWagonSummary, WagonSegment
from app.services import gps_analytics as ga
from app.services import gps_compare as cmp
from app.services import gtk_gps
from app.services.gps_overview import _fix, _scope

SORT_FIELDS = {"inv_number", "km_period", "confidence", "since", "train_number"}
FLAGS = ("two_trains", "stale_membership", "loco_silent", "no_loco", "no_history")
_CONF_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
STALE_MEMBERSHIP_DAYS = 3
STALE_MEMBERSHIP_KM = 0.5


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def confidence_of(in_train: bool, loco_fix: GpsFix | None, verdict: str | None) -> str:
    """How far the position/km of a wagon can be trusted: it is only as good as the locomotive's fixes."""
    if not in_train or loco_fix is None:
        return "none"
    if not loco_fix.fresh or verdict in ("diverged", "both_stale_apart"):
        return "low"
    return "high" if verdict == "confirmed" else "medium"


async def _loco_fixes(db: AsyncSession, now: datetime) -> dict[int, dict]:
    """GTK locomotive id -> {asset, fix, source, verdict, section}: the best fix of each locomotive and how well the two trackers agree on it."""
    out: dict[int, dict] = {}
    inverse = {asset: gid for gid, asset in (await gtk_gps.linked_targets(db)).items()}
    for b in await gps_repository.list_loco_positions(db):
        gid = inverse.get(b["asset_id"])
        if gid is None:
            continue
        wialon = _fix(b["w_lat"], b["w_lon"], b["w_at"], b["w_speed"], now)
        gtk = _fix(b["g_lat"], b["g_lon"], b["g_at"], b["g_speed"], now)
        check = cmp.position_check(
            cmp.SourceFix(wialon.lat, wialon.lon, wialon.at, wialon.speed) if wialon else None,
            cmp.SourceFix(gtk.lat, gtk.lon, gtk.at, gtk.speed) if gtk else None,
            now,
        )
        fix = gtk if (check.best == "gtk" and gtk) else wialon
        out[gid] = {"asset_id": b["asset_id"], "inv": b["inv_number"], "name": b["name"], "section_id": b["section_id"], "fix": fix, "source": check.best, "verdict": check.verdict}
    return out


async def list_wagons(
    db: AsyncSession, user: User, *, q: str | None = None, section_id: UUID | None = None, train: str | None = None, loco: str | None = None,
    confidence: list[str] | None = None, flag: list[str] | None = None, in_train: bool | None = None, asset_type: str | None = None, days: int = 14,
    sort_by: str = "inv_number", sort_dir: str = "asc", limit: int = 200, offset: int = 0, now: datetime | None = None,
) -> GpsWagonPage:
    if sort_by not in SORT_FIELDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sort_by must be one of: " + ", ".join(sorted(SORT_FIELDS)))
    scope = _scope(user)
    now = now or datetime.now(timezone.utc)
    days = max(1, min(days, 31))
    since_window = now - timedelta(days=days)
    type_name = (
        select(FixedAssetTypeTranslation.name)
        .where(FixedAssetTypeTranslation.type_code == FixedAsset.asset_type, FixedAssetTypeTranslation.locale == "ru")
        .limit(1).correlate(FixedAsset).scalar_subquery()
    )
    link = AssetSourceLink
    statement = (
        select(
            GtkCarriage.gtk_id, GtkCarriage.name.label("gtk_name"), GtkCarriage.reg_number, GtkCarriage.inventory_number,
            FixedAsset.id.label("asset_id"), FixedAsset.inv_number, fixed_asset_name_expression().label("asset_name"), FixedAsset.asset_type,
            type_name.label("asset_type_name"), FixedAsset.section_id, Section.name.label("section_name"),
        )
        .select_from(GtkCarriage)
        .outerjoin(link, (link.source == "gtk") & (link.status == "active") & (link.external_id == cast(GtkCarriage.gtk_id, String)))
        .outerjoin(FixedAsset, (FixedAsset.id == link.asset_id) & FixedAsset.asset_type.not_in(LOCOMOTIVE_TYPES) & FixedAsset.decommissioned_at.is_(None))
        .outerjoin(Section, FixedAsset.section_id == Section.id)
        .where(GtkCarriage.is_active.is_(True))
    )
    carriages = (await db.execute(statement)).mappings().all()
    if scope is not None:
        carriages = [c for c in carriages if c["asset_id"] is not None and c["section_id"] == scope]  # a master never sees unassigned GTK carriages
    members = (await db.execute(select(GtkTrainMember).where(GtkTrainMember.observed_to.is_(None)))).scalars().all()
    trains = {t.gtk_id: t for t in (await db.execute(select(GtkTrain))).scalars().all()}
    carriage_members: dict[int, list[GtkTrainMember]] = defaultdict(list)
    loco_members: dict[int, list[GtkTrainMember]] = defaultdict(list)
    for m in members:
        (loco_members if m.kind == "locomotive" else carriage_members)[m.train_gtk_id if m.kind == "locomotive" else m.object_gtk_id].append(m)
    locos = await _loco_fixes(db, now)
    history_from = (await db.execute(select(func.min(GtkTrainMember.observed_from)))).scalar_one()
    ever = {r[0] for r in (await db.execute(select(GtkTrainMember.object_gtk_id).where(GtkTrainMember.kind == "carriage").distinct())).all()}
    agg = await db.execute(
        select(GpsWagonSegment.carriage_gtk_id, GpsWagonSegment.basis, func.coalesce(func.sum(GpsWagonSegment.selected_km), 0), func.count())
        .where(GpsWagonSegment.period_to >= since_window).group_by(GpsWagonSegment.carriage_gtk_id, GpsWagonSegment.basis)
    )
    km: dict[int, float] = defaultdict(float)
    n_seg: dict[int, int] = defaultdict(int)
    basis: dict[int, Counter] = defaultdict(Counter)
    for cid, b, total, n in agg.all():
        km[cid] += float(total)
        n_seg[cid] += n
        basis[cid][b] += n
    recent = await db.execute(
        select(GpsWagonSegment.carriage_gtk_id, func.coalesce(func.sum(GpsWagonSegment.selected_km), 0))
        .where(GpsWagonSegment.period_to >= now - timedelta(days=STALE_MEMBERSHIP_DAYS)).group_by(GpsWagonSegment.carriage_gtk_id)
    )
    km_recent = {cid: float(v) for cid, v in recent.all()}

    rows: list[GpsWagonRow] = []
    for c in carriages:
        cid = c["gtk_id"]
        mine = carriage_members.get(cid, [])
        current = max(mine, key=lambda m: _aware(m.observed_from)) if mine else None
        in_t = current is not None
        train_row = trains.get(current.train_gtk_id) if current else None
        loco_m = None
        if current is not None:
            live = loco_members.get(current.train_gtk_id, [])
            loco_m = min(live, key=lambda m: (not m.is_main, m.ord, m.object_gtk_id)) if live else None
        info = locos.get(loco_m.object_gtk_id) if loco_m is not None else None
        visible_loco = info is not None and (scope is None or info["section_id"] == scope)
        fix = info["fix"] if info else None
        flags: list[str] = []
        if len(mine) > 1:
            flags.append("two_trains")
        if in_t and info is None:
            flags.append("no_loco")
        if in_t and fix is not None and not fix.fresh:
            flags.append("loco_silent")
        if in_t and current is not None and (now - _aware(current.observed_from)) > timedelta(days=STALE_MEMBERSHIP_DAYS) and km_recent.get(cid, 0.0) < STALE_MEMBERSHIP_KM:
            flags.append("stale_membership")
        if c["asset_id"] is not None and cid not in ever:
            flags.append("no_history")
        conf = confidence_of(in_t, fix, info["verdict"] if info else None)
        rows.append(
            GpsWagonRow(
                asset_id=c["asset_id"], carriage_gtk_id=cid, inv_number=c["inv_number"] or c["inventory_number"], name=c["asset_name"] or c["gtk_name"] or f"GTK {cid}",
                asset_type=c["asset_type"], asset_type_name=c["asset_type_name"], section_id=c["section_id"], section_name=c["section_name"], in_train=in_t,
                train_gtk_id=current.train_gtk_id if current else None, train_number=train_row.number if train_row else None,
                since=current.observed_from if current else None, loco_asset_id=info["asset_id"] if visible_loco else None,
                loco_inv_number=info["inv"] if visible_loco else None, loco_name=info["name"] if visible_loco else None, position=fix,
                position_source=("gtk_gps" if info and info["source"] == "gtk" else "wialon") if fix else None, position_verdict=info["verdict"] if info else None,
                confidence=conf, flags=flags, km_period=round(km.get(cid, 0.0), 1), segments_n=n_seg.get(cid, 0), basis_counts=dict(basis.get(cid, {})),
            )
        )
    summary = GpsWagonSummary(wagons=len(rows), in_train=sum(1 for r in rows if r.in_train), history_from=history_from)
    for r in rows:
        summary.confidence_counts[r.confidence] = summary.confidence_counts.get(r.confidence, 0) + 1
        for f in r.flags:
            summary.flag_counts[f] = summary.flag_counts.get(f, 0) + 1
        summary.km_period += r.km_period
    summary.km_period = round(summary.km_period, 1)

    needle = (q or "").strip().lower()
    loco_needle = (loco or "").strip().lower()
    train_needle = (train or "").strip().lower()

    def keep(r: GpsWagonRow) -> bool:
        if needle and needle not in " ".join(str(x or "") for x in (r.inv_number, r.name, r.carriage_gtk_id)).lower():
            return False
        if section_id is not None and r.section_id != section_id:
            return False
        if train_needle and train_needle not in (str(r.train_number or "").lower(), str(r.train_gtk_id or "")):
            return False
        if loco_needle and loco_needle not in (r.loco_inv_number or "").lower():
            return False
        return (
            (not confidence or r.confidence in confidence) and (not flag or any(f in r.flags for f in flag))
            and (in_train is None or r.in_train == in_train) and (asset_type is None or r.asset_type == asset_type)
        )

    shown = [r for r in rows if keep(r)]
    keys = {
        "inv_number": lambda r: (r.inv_number or "~", r.name),
        "km_period": lambda r: r.km_period,
        "confidence": lambda r: (_CONF_ORDER[r.confidence], r.inv_number or "~"),
        "since": lambda r: _aware(r.since).timestamp() if r.since else 0.0,
        "train_number": lambda r: (str(r.train_number or "~"), r.inv_number or "~"),
    }
    shown.sort(key=keys[sort_by], reverse=(sort_dir == "desc"))
    return GpsWagonPage(items=shown[offset : offset + limit], total=len(shown), limit=limit, offset=offset, summary=summary, days=days)


def explain(row: GpsWagonRow, segments: list[WagonSegment]) -> str:
    if not row.in_train:
        return "Вагон сейчас не числится ни в одном составе GTK: собственных GPS у вагона нет, поэтому положение неизвестно."
    parts = [f"Вагон в составе № {row.train_number or row.train_gtk_id}"]
    if row.loco_inv_number:
        parts[0] += f" за локомотивом {row.loco_inv_number}"
    parts[0] += ": положение берётся от локомотива."
    if row.confidence == "high":
        parts.append("Оба трекера локомотива подтверждают его положение.")
    elif row.confidence == "medium":
        parts.append("Положение локомотива подтверждено одним трекером.")
    elif row.confidence == "low":
        parts.append("Данные локомотива устарели или трекеры расходятся: положение ненадёжно.")
    if segments:
        s = next((x for x in segments if x.selected_km is not None), None)
        if s is not None:
            parts.append(f"Пробег последнего участка выбран методом «{s.basis}» ({s.selected_km:.1f} км, уверенность: {s.confidence}).")
    return " ".join(parts)


async def wagon_detail(db: AsyncSession, user: User, key: str, *, days: int = 31, now: datetime | None = None) -> GpsWagonDetail:
    scope = _scope(user)
    now = now or datetime.now(timezone.utc)
    carriage_id: int | None = None
    if key.startswith("gtk-") and key[4:].isdigit():
        if scope is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wagon not found")  # a master never sees unassigned carriages
        carriage_id = int(key[4:])
    else:
        try:
            asset = UUID(key)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wagon not found") from exc
        stmt = (
            select(AssetSourceLink.external_id).join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
            .where(AssetSourceLink.asset_id == asset, AssetSourceLink.source == "gtk", AssetSourceLink.status == "active", FixedAsset.asset_type.not_in(LOCOMOTIVE_TYPES))
        )
        if scope is not None:
            stmt = stmt.where(FixedAsset.section_id == scope)
        ext = (await db.execute(stmt)).scalar_one_or_none()
        if ext is None or not str(ext).isdigit():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wagon not found")
        carriage_id = int(ext)
    page = await list_wagons(db, user, q=str(carriage_id), limit=500, now=now, days=days)
    row = next((r for r in page.items if r.carriage_gtk_id == carriage_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wagon not found")
    segs = (
        await db.execute(
            select(GpsWagonSegment).where(GpsWagonSegment.carriage_gtk_id == carriage_id, GpsWagonSegment.period_to >= now - timedelta(days=max(1, min(days, 31))))
            .order_by(GpsWagonSegment.period_from.desc())
        )
    ).scalars().all()
    trains = {t.gtk_id: t.number for t in (await db.execute(select(GtkTrain).where(GtkTrain.gtk_id.in_({s.train_gtk_id for s in segs})))).scalars().all()} if segs else {}
    loco_ids = {s.loco_asset_id for s in segs if s.loco_asset_id}
    loco_info: dict[UUID, tuple[str, UUID | None]] = {}
    if loco_ids:
        for a in (await db.execute(select(FixedAsset.id, FixedAsset.inv_number, FixedAsset.section_id).where(FixedAsset.id.in_(loco_ids)))).all():
            loco_info[a.id] = (a.inv_number, a.section_id)
    f = lambda v: None if v is None else float(v)  # noqa: E731
    out: list[WagonSegment] = []
    for s in segs:
        info = loco_info.get(s.loco_asset_id) if s.loco_asset_id else None
        visible = info is not None and (scope is None or info[1] == scope)
        out.append(
            WagonSegment(
                train_gtk_id=s.train_gtk_id, train_number=trains.get(s.train_gtk_id), loco_asset_id=s.loco_asset_id if visible else None,
                loco_inv_number=info[0] if visible else None, period_from=s.period_from, period_to=s.period_to, open=s.is_open,
                km_odometer=f(s.km_odometer), km_wialon=f(s.km_wialon), km_gtk=f(s.km_gtk), km_fused=f(s.km_fused), selected_km=f(s.selected_km),
                basis=s.basis, confidence=s.confidence, coverage=f(s.coverage), flags=list(s.flags or []),
            )
        )
    return GpsWagonDetail(row=row, segments=out, explanation=explain(row, out))
