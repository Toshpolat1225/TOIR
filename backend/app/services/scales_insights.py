"""Command-center payloads: one request = one screen, with the joins done here (assets, sections, models, maintenance, work orders, GTK, Wialon).

Rules shared with the ledger (`scales_trips.py`): a train counts when it is not excluded; a wagon trip needs the train to be matched
to a GTK train (`ok`); the cargo of a trip is the car's own weighing, else the train's share, else unknown.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, cast, func, or_, select, Text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset_models import AssetModel
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain
from app.models.localization import FixedAssetStatusTranslation, FixedAssetTypeTranslation
from app.models.maintenance import AssetMaintenanceBaseline, MaintenanceInterval, MaintenancePlan
from app.models.organization import Section
from app.models.scales import ScaleCargo, ScaleCorrection, ScalePost, ScaleTrain, ScaleTrainCarriage, ScaleWeighing
from app.models.wialon_units import WialonUnitRecord
from app.models.work_orders import WorkOrder
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.schemas import scales_insights as s
from app.services import scales_trips as trips

D0 = Decimal(0)
OPEN_PLAN_STATUSES = ("scheduled", "in_progress", "blocked")


def _q2(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _opt(value: Any) -> Decimal | None:
    return None if value is None else _q2(value)


def _tz() -> timezone:
    return timezone(timedelta(hours=settings.scales_utc_offset_hours))


def _today() -> date:
    return datetime.now(_tz()).date()


def _per_car():
    t = ScaleTrain
    return t.net_total_t / func.nullif(func.coalesce(func.nullif(t.dump_count, 0), func.nullif(t.carriages_total, 0)), 0)


# ───────────────────────── overview ─────────────────────────

async def _kpi(db: AsyncSession, lo: datetime, hi: datetime) -> s.Kpi:
    t = ScaleTrain
    live = and_(t.match_status != "excluded", t.started_at >= lo, t.started_at < hi)
    cars = func.coalesce(func.nullif(t.dump_count, 0), func.nullif(t.carriages_total, 0))
    row = (
        await db.execute(
            select(
                func.count(), func.coalesce(func.sum(t.net_total_t), 0),
                func.avg(t.net_total_t),
                func.sum(t.net_total_t).filter(t.net_total_t.is_not(None), cars.is_not(None)),
                func.sum(cars).filter(t.net_total_t.is_not(None)),
                func.count().filter(t.flags.any("overload")), func.count().filter(t.match_status == "ok"),
                func.count().filter(t.net_source == "estimated"), func.count(func.distinct(t.loco_asset_id)),
            ).where(live)
        )
    ).one()
    trains_n, tonnes, avg_train, sum_net, sum_cars, overload, ok, estimated, locos = row
    tc, tr = ScaleTrainCarriage, t
    wagon_row = (
        await db.execute(
            select(func.count(), func.count(func.distinct(tc.carriage_gtk_id)))
            .select_from(tc).join(tr, tr.id == tc.train_id)
            .where(tr.match_status == "ok", tr.started_at >= lo, tr.started_at < hi)
        )
    ).one()
    return s.Kpi(
        trains=trains_n, wagon_trips=wagon_row[0], tonnes=_q2(tonnes), avg_train_t=_opt(avg_train),
        avg_car_t=_opt(Decimal(str(sum_net)) / Decimal(str(sum_cars))) if sum_net and sum_cars else None,
        overload_share=round(overload / trains_n, 3) if trains_n else None, matched_share=round(ok / trains_n, 3) if trains_n else None,
        estimated_share=round(estimated / trains_n, 3) if trains_n else None, active_wagons=wagon_row[1], active_locos=locos,
    )


async def overview(db: AsyncSession, days: int) -> s.Overview:
    end = _today()
    start = end - timedelta(days=days - 1)
    lo, hi = trips.local_range(start, end)
    plo, phi = trips.local_range(start - timedelta(days=days), start - timedelta(days=1))
    assert lo is not None and hi is not None and plo is not None and phi is not None
    t = ScaleTrain
    live = and_(t.match_status != "excluded", t.started_at >= lo, t.started_at < hi)
    offset = timedelta(hours=settings.scales_utc_offset_hours)
    local = t.started_at + offset
    day = func.date_trunc("day", local)
    hour = func.extract("hour", local)

    daily = [
        s.DayPoint(day=d.date(), post_code=code, trains=n, tonnes=_q2(tn))
        for d, code, n, tn in (
            await db.execute(
                select(day, ScalePost.code, func.count(), func.coalesce(func.sum(t.net_total_t), 0))
                .join(ScalePost, ScalePost.id == t.post_id).where(live).group_by(day, ScalePost.code).order_by(day, ScalePost.code)
            )
        ).all()
    ]
    hourly = [
        s.HourPoint(hour=int(h), post_code=code, trains=n, tonnes=_q2(tn))
        for h, code, n, tn in (
            await db.execute(
                select(hour, ScalePost.code, func.count(), func.coalesce(func.sum(t.net_total_t), 0))
                .join(ScalePost, ScalePost.id == t.post_id).where(live).group_by(hour, ScalePost.code).order_by(hour)
            )
        ).all()
    ]
    cargo_names = {c: n for c, n in (await db.execute(select(ScaleCargo.code, ScaleCargo.name))).all()}
    by_cargo = [
        s.NamedTotal(key=str(c), label=cargo_names.get(c, f"Груз {c}") if c else "Не указан", trains=n, tonnes=_q2(tn))
        for c, n, tn in (
            await db.execute(select(t.cargo_code, func.count(), func.coalesce(func.sum(t.net_total_t), 0)).where(live).group_by(t.cargo_code).order_by(func.sum(t.net_total_t).desc().nullslast()))
        ).all()
    ]
    by_excavator = [
        s.NamedTotal(key=str(e), label=f"Экскаватор {e}", trains=n, tonnes=_q2(tn))
        for e, n, tn in (
            await db.execute(
                select(t.excavator, func.count(), func.coalesce(func.sum(t.net_total_t), 0))
                .where(live, t.excavator.is_not(None), t.excavator > 0).group_by(t.excavator).order_by(func.sum(t.net_total_t).desc().nullslast()).limit(12)
            )
        ).all()
    ]
    loco_group = case_group = func.coalesce(cast(t.loco_asset_id, Text), t.loco_number)
    loco_rows = (
        await db.execute(
            select(
                func.max(cast(t.loco_asset_id, Text)), func.max(t.loco_number), func.count(), func.coalesce(func.sum(t.net_total_t), 0), func.avg(t.net_total_t),
            ).where(live, case_group.is_not(None)).group_by(loco_group).order_by(func.sum(t.net_total_t).desc().nullslast()).limit(8)
        )
    ).all()
    top_locos: list[s.LocoTop] = []
    for asset_text, number, n, tn, avg in loco_rows:
        asset_id = UUID(asset_text) if asset_text else None
        inv = model = None
        if asset_id:
            ident = (await db.execute(select(FixedAsset.inv_number, AssetModel.name).outerjoin(AssetModel, AssetModel.id == FixedAsset.model_id).where(FixedAsset.id == asset_id))).one_or_none()
            if ident:
                inv, model = ident
        top_locos.append(s.LocoTop(asset_id=asset_id, loco_number=number, inv_number=inv, model_name=model, trains=n, tonnes=_q2(tn), avg_train_t=_opt(avg)))

    totals_page = await trips.wagon_totals(
        db, q=None, date_from=start, date_to=end, post=None, cargo_code=None, only_linked=False, sort_by="tonnes", descending=True, limit=8, offset=0
    )
    top_wagons = [
        s.WagonTop(asset_id=w.asset_id, carriage_gtk_id=w.carriage_gtk_id, label=w.inv_number or w.gtk_inventory_number or w.gtk_name or f"GTK {w.carriage_gtk_id}", trips=w.trips, tonnes=w.tonnes)
        for w in totals_page.items
    ]

    tlo, thi = trips.local_range(end, end)
    today_rows = (
        await db.execute(
            select(t.id, ScalePost.code, t.started_at, t.finished_at, t.net_total_t, t.match_status, t.loco_number)
            .join(ScalePost, ScalePost.id == t.post_id).where(t.started_at >= tlo, t.started_at < thi, t.match_status != "excluded").order_by(t.started_at).limit(400)
        )
    ).all()
    today = [s.LaneTrain(id=i, post_code=c, started_at=a, finished_at=b, tonnes=_opt(tn), match_status=m, loco_number=ln) for i, c, a, b, tn, m, ln in today_rows]

    statuses = {k: n for k, n in (await db.execute(select(t.match_status, func.count()).where(live).group_by(t.match_status))).all()}
    flag_rows = await db.execute(select(func.unnest(t.flags).label("f"), func.count()).where(live).group_by("f"))
    from app.services import scales as base  # the same "before GTK history" notion as the status header

    history_start = await base._gtk_history_start(db)
    before = 0
    if history_start is not None:
        before = (await db.execute(select(func.count()).where(live, t.match_status == "no_gtk_train", t.started_at < history_start))).scalar_one()
    return s.Overview(
        date_from=start, date_to=end, days=days, kpi=await _kpi(db, lo, hi), previous=await _kpi(db, plo, phi), daily=daily, hourly=hourly,
        by_cargo=by_cargo, by_excavator=by_excavator, top_locomotives=top_locos, top_wagons=top_wagons, today=today,
        quality=s.Quality(by_status=statuses, flags={f: n for f, n in flag_rows.all()}, before_gtk_history=before),
    )


# ───────────────────────── shared joins ─────────────────────────

async def _identity(db: AsyncSession, asset_id: UUID) -> s.AssetIdentity | None:
    type_name = (
        select(FixedAssetTypeTranslation.name).where(FixedAssetTypeTranslation.type_code == FixedAsset.asset_type, FixedAssetTypeTranslation.locale == "ru")
        .limit(1).correlate(FixedAsset).scalar_subquery()
    )
    status_name = (
        select(FixedAssetStatusTranslation.name).where(FixedAssetStatusTranslation.status_code == FixedAsset.status, FixedAssetStatusTranslation.locale == "ru")
        .limit(1).correlate(FixedAsset).scalar_subquery()
    )
    row = (
        await db.execute(
            select(
                FixedAsset, fixed_asset_name_expression().label("name"), type_name.label("type_name"), status_name.label("status_name"),
                Section.name.label("section_name"), AssetModel.name.label("model_name"),
            )
            .outerjoin(Section, Section.id == FixedAsset.section_id).outerjoin(AssetModel, AssetModel.id == FixedAsset.model_id)
            .where(FixedAsset.id == asset_id)
        )
    ).one_or_none()
    if row is None:
        return None
    a = row.FixedAsset
    return s.AssetIdentity(
        asset_id=a.id, inv_number=a.inv_number, name=row.name, asset_type=a.asset_type, asset_type_name=row.type_name, status=a.status,
        status_name=row.status_name, section_id=a.section_id, section_name=row.section_name, model_name=row.model_name, owner=a.owner,
        year_built=a.year_built, mileage=_opt(a.mileage), last_maint_date=a.last_maint_date, next_maint_date=a.next_maint_date,
    )


async def _maintenance(db: AsyncSession, asset_id: UUID, kind: str) -> s.Maintenance:
    """What the asset's maintenance says, and how much work (trips, tonnes) the scales saw since its last service."""
    candidates: list[tuple[date, str]] = []
    closed = (
        await db.execute(select(func.max(WorkOrder.closed_at)).where(WorkOrder.fixed_asset_id == asset_id, WorkOrder.status == "completed"))
    ).scalar_one()
    if closed is not None:
        candidates.append((closed.astimezone(_tz()).date(), "завершённый наряд"))
    baseline = (await db.execute(select(func.max(AssetMaintenanceBaseline.done_at)).where(AssetMaintenanceBaseline.asset_id == asset_id))).scalar_one()
    if baseline is not None:
        candidates.append((baseline, "введённая база ТО"))
    own = (await db.execute(select(FixedAsset.last_maint_date).where(FixedAsset.id == asset_id))).scalar_one()
    if own is not None:
        candidates.append((own, "дата в карточке ОС"))
    last_date, source = max(candidates, key=lambda c: c[0]) if candidates else (None, None)

    trips_since, tonnes_since = 0, D0
    if last_date is not None:
        since = datetime.combine(last_date, datetime.min.time(), tzinfo=_tz())
        if kind == "wagon":
            stmt, _tonnes, _wagon = trips._trip_select(asset_id=asset_id, q=None, date_from=None, date_to=None, post=None, cargo_code=None, only_linked=False)
            rows = (await db.execute(stmt.where(ScaleTrain.started_at >= since))).all()
            trips_since, tonnes_since = len(rows), sum((Decimal(str(r.tonnes)) for r in rows if r.tonnes is not None), D0)
        else:
            row = (
                await db.execute(
                    select(func.count(), func.coalesce(func.sum(ScaleTrain.net_total_t), 0)).where(
                        ScaleTrain.loco_asset_id == asset_id, ScaleTrain.match_status.in_(("ok", "no_gtk_train")), ScaleTrain.started_at >= since
                    )
                )
            ).one()
            trips_since, tonnes_since = row[0], Decimal(str(row[1]))
    plans = [
        s.PlanItem(plan_id=p.id, interval_code=code, interval_name=name, status=p.status, scheduled_date=p.scheduled_date, trigger_mileage=_opt(p.trigger_mileage))
        for p, code, name in (
            await db.execute(
                select(MaintenancePlan, MaintenanceInterval.code, MaintenanceInterval.name)
                .join(MaintenanceInterval, MaintenanceInterval.id == MaintenancePlan.interval_id)
                .where(MaintenancePlan.asset_id == asset_id, MaintenancePlan.status.in_(OPEN_PLAN_STATUSES))
                .order_by(MaintenancePlan.scheduled_date.asc().nullslast()).limit(6)
            )
        ).all()
    ]
    orders = (
        await db.execute(select(WorkOrder).where(WorkOrder.fixed_asset_id == asset_id).order_by(WorkOrder.created_at.desc()).limit(5))
    ).scalars().all()
    total_orders = (await db.execute(select(func.count()).where(WorkOrder.fixed_asset_id == asset_id))).scalar_one()
    return s.Maintenance(
        last_service_at=last_date, last_service_source=source, trips_since=trips_since, tonnes_since=_q2(tonnes_since), plans=plans,
        work_orders=[s.WorkOrderItem(id=o.id, number=o.number, status=o.status, order_kind=o.order_kind, description=o.description, date_start=o.date_start, closed_at=o.closed_at) for o in orders],
        work_orders_total=total_orders,
    )


def _totals(rows: list[Any]) -> s.Totals:
    tonnes = sum((Decimal(str(r.tonnes)) for r in rows if r.tonnes is not None), D0)
    times = [r.started_at for r in rows if r.started_at]
    own = [r for r in rows if getattr(r, "basis", None) == "own"]
    over = [r for r in own if r.capacity is not None and r.tonnes is not None and r.tonnes > r.capacity]
    return s.Totals(
        trips=len(rows), tonnes=_q2(tonnes), avg_tonnes=_q2(tonnes / len(rows)) if rows else None, own_trips=len(own), overload_trips=len(over),
        first_at=min(times, default=None), last_at=max(times, default=None),
    )


def _daily(rows: list[Any]) -> list[s.WorkDayPoint]:
    per: dict[date, list[Any]] = defaultdict(list)
    for r in rows:
        if r.started_at:
            per[r.started_at.astimezone(_tz()).date()].append(r)
    return [
        s.WorkDayPoint(day=d, trips=len(v), tonnes=_q2(sum((Decimal(str(r.tonnes)) for r in v if r.tonnes is not None), D0)))
        for d, v in sorted(per.items())
    ]


def _split(rows: list[Any], key, label, limit: int = 8) -> list[s.Split]:
    acc: dict[Any, list[Any]] = defaultdict(list)
    for r in rows:
        acc[key(r)].append(r)
    out = [
        s.Split(key=str(k), label=label(k), trips=len(v), tonnes=_q2(sum((Decimal(str(r.tonnes)) for r in v if r.tonnes is not None), D0)))
        for k, v in acc.items()
    ]
    return sorted(out, key=lambda x: (x.tonnes, x.trips), reverse=True)[:limit]


def _within(rows: list[Any], lo: datetime, hi: datetime) -> list[Any]:
    return [r for r in rows if r.started_at and lo <= r.started_at < hi]


# ───────────────────────── wagon card ─────────────────────────

async def wagon_card(db: AsyncSession, *, asset_id: UUID | None, carriage_gtk_id: int | None, days: int) -> s.WagonCard:
    if asset_id is None and carriage_gtk_id is None:
        raise HTTPException(status_code=422, detail="asset_id or carriage_gtk_id is required")
    identity = await _identity(db, asset_id) if asset_id else None
    if asset_id and identity is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    if asset_id and identity and identity.asset_type in LOCOMOTIVE_TYPES:
        raise HTTPException(status_code=422, detail="This is a locomotive: use the locomotive card")
    stmt, _tonnes, _wagon = trips._trip_select(asset_id=asset_id, q=None, date_from=None, date_to=None, post=None, cargo_code=None, only_linked=False, carriage_gtk_id=carriage_gtk_id)
    rows = (await db.execute(stmt.order_by(ScaleTrain.started_at.desc()))).all()
    gtk_id = carriage_gtk_id
    if gtk_id is None and rows:
        gtk_id = rows[0].carriage_gtk_id
    if gtk_id is None and asset_id:
        link = (await db.execute(select(AssetSourceLink.external_id).where(AssetSourceLink.asset_id == asset_id, AssetSourceLink.source == "gtk", AssetSourceLink.status == "active"))).scalar_one_or_none()
        gtk_id = int(link) if link and str(link).isdigit() else None
    gtk = None
    if gtk_id is not None:
        c = (await db.execute(select(GtkCarriage).where(GtkCarriage.gtk_id == gtk_id))).scalar_one_or_none()
        if c is not None:
            gtk = s.GtkCarriageInfo(
                carriage_gtk_id=c.gtk_id, name=c.name, reg_number=c.reg_number, inventory_number=c.inventory_number, model_name=c.model_name,
                is_active=c.is_active, is_loaded=c.is_loaded, lat=c.lat, lon=c.lon,
            )
    if identity is None and gtk is None and not rows:
        raise HTTPException(status_code=404, detail="Wagon not found")
    end = _today()
    start = end - timedelta(days=days - 1)
    lo, hi = trips.local_range(start, end)
    assert lo is not None and hi is not None
    period_rows = _within(rows, lo, hi)
    loco_label = lambda k: k if k != "None" else "Не указан"  # noqa: E731
    maintenance = await _maintenance(db, asset_id, "wagon") if asset_id else None
    return s.WagonCard(
        asset=identity, gtk=gtk, date_from=start, date_to=end, period=_totals(period_rows), all_time=_totals(rows), daily=_daily(period_rows),
        by_cargo=_split(period_rows, lambda r: r.cargo_name, lambda k: k or "Не указан"),
        by_loco=_split(period_rows, lambda r: r.loco_number, loco_label),
        by_excavator=_split([r for r in period_rows if r.excavator], lambda r: r.excavator, lambda k: f"Экскаватор {k}"),
        recent=[
            s.WagonTripBrief(train_id=r.train_id, started_at=r.started_at, post_code=r.post_code, tonnes=_opt(r.tonnes), basis=r.basis, position=r.position, loco_number=r.loco_number, cargo_name=r.cargo_name)
            for r in rows[:15]
        ],
        maintenance=maintenance,
    )


# ───────────────────────── locomotive card ─────────────────────────

async def loco_card(db: AsyncSession, asset_id: UUID, days: int) -> s.LocoCard:
    identity = await _identity(db, asset_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    if identity.asset_type not in LOCOMOTIVE_TYPES:
        raise HTTPException(status_code=422, detail="This is not a locomotive: use the wagon card")
    t = ScaleTrain
    where = and_(t.loco_asset_id == asset_id, t.match_status.in_(("ok", "no_gtk_train")))
    rows = (
        await db.execute(
            select(
                t.id, t.started_at, t.net_total_t.label("tonnes"), t.net_source, t.loco_number, t.flags, t.match_status, t.excavator,
                func.coalesce(func.nullif(t.dump_count, 0), func.nullif(t.carriages_total, 0)).label("cars"), ScaleCargo.name.label("cargo_name"),
                ScalePost.code.label("post_code"), ScalePost.capacity_norm_t.label("capacity"),
            )
            .join(ScalePost, ScalePost.id == t.post_id).outerjoin(ScaleCargo, ScaleCargo.code == t.cargo_code).where(where).order_by(t.started_at.desc())
        )
    ).all()
    end = _today()
    start = end - timedelta(days=days - 1)
    lo, hi = trips.local_range(start, end)
    assert lo is not None and hi is not None
    period = _within(rows, lo, hi)
    cars = [r.cars for r in period if r.cars]
    numbers: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.loco_number:
            numbers[r.loco_number] += 1

    # wagons this locomotive pulled in the period (joined through the matched carriages)
    stmt, _tonnes, _wagon = trips._trip_select(asset_id=None, q=None, date_from=start, date_to=end, post=None, cargo_code=None, only_linked=False, loco_asset_id=asset_id)
    pulled = (await db.execute(stmt)).all()
    grouped: dict[int, list[Any]] = defaultdict(list)
    for r in pulled:
        grouped[r.carriage_gtk_id].append(r)
    top_wagons = sorted(
        (
            s.WagonTop(
                asset_id=v[0].asset_id, carriage_gtk_id=k, label=v[0].inv_number or v[0].gtk_inventory_number or v[0].gtk_name or f"GTK {k}",
                trips=len(v), tonnes=_q2(sum((Decimal(str(x.tonnes)) for x in v if x.tonnes is not None), D0)),
            )
            for k, v in grouped.items()
        ),
        key=lambda w: (w.tonnes, w.trips), reverse=True,
    )[:10]

    gtk_link = (await db.execute(select(AssetSourceLink.external_id).where(AssetSourceLink.asset_id == asset_id, AssetSourceLink.source == "gtk", AssetSourceLink.status == "active"))).scalar_one_or_none()
    gtk = None
    if gtk_link and str(gtk_link).isdigit():
        g = (await db.execute(select(GtkLocomotive).where(GtkLocomotive.gtk_id == int(gtk_link)))).scalar_one_or_none()
        if g is not None:
            gtk = s.GtkLocoInfo(gtk_id=g.gtk_id, name=g.name, garage_number=g.garage_number, model_name=g.model_name, is_active=g.is_active)
    wialon = None
    unit_id = (await db.execute(select(AssetSourceLink.external_id).where(AssetSourceLink.asset_id == asset_id, AssetSourceLink.source == "wialon", AssetSourceLink.status == "active"))).scalar_one_or_none()
    if unit_id:
        u = (await db.execute(select(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit_id))).scalar_one_or_none()
        if u is not None:
            wialon = s.WialonInfo(unit_id=u.unit_id, name=u.name, last_message_at=u.last_message_at, speed=u.speed, lat=u.lat, lon=u.lon)
    return s.LocoCard(
        asset=identity, gtk=gtk, wialon=wialon, numbers_used=[n for n, _c in sorted(numbers.items(), key=lambda kv: -kv[1])][:6],
        date_from=start, date_to=end, period=_totals(period), all_time=_totals(rows),
        avg_cars=_q2(Decimal(sum(cars)) / len(cars)) if cars else None, daily=_daily(period),
        by_cargo=_split(period, lambda r: r.cargo_name, lambda k: k or "Не указан"),
        by_excavator=_split([r for r in period if r.excavator], lambda r: r.excavator, lambda k: f"Экскаватор {k}"),
        top_wagons=top_wagons,
        recent=[
            s.TrainBrief(id=r.id, started_at=r.started_at, post_code=r.post_code, tonnes=_opt(r.tonnes), net_source=r.net_source, cars=r.cars or 0, cargo_name=r.cargo_name, match_status=r.match_status, flags=list(r.flags or []))
            for r in rows[:15]
        ],
        maintenance=await _maintenance(db, asset_id, "locomotive"),
    )


# ───────────────────────── train card ─────────────────────────

async def train_card(db: AsyncSession, train_id: UUID) -> s.TrainCard:
    t = ScaleTrain
    row = (
        await db.execute(
            select(t, ScalePost.code, ScalePost.name, ScaleCargo.name).join(ScalePost, ScalePost.id == t.post_id).outerjoin(ScaleCargo, ScaleCargo.code == t.cargo_code).where(t.id == train_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Train not found")
    train, post_code, post_name, cargo_name = row
    weighings = (await db.execute(select(ScaleWeighing).where(ScaleWeighing.train_id == train_id).order_by(ScaleWeighing.position.asc().nullslast(), ScaleWeighing.id))).scalars().all()
    car_rows = (
        await db.execute(
            select(ScaleTrainCarriage, GtkCarriage.name, GtkCarriage.model_name, FixedAsset.inv_number)
            .outerjoin(GtkCarriage, GtkCarriage.gtk_id == ScaleTrainCarriage.carriage_gtk_id)
            .outerjoin(FixedAsset, FixedAsset.id == ScaleTrainCarriage.asset_id)
            .where(ScaleTrainCarriage.train_id == train_id).order_by(ScaleTrainCarriage.ord)
        )
    ).all()
    by_position = {c.unit_position: (c, name, inv) for c, name, _model, inv in car_rows if c.unit_position is not None}
    units = []
    for w in weighings:
        paired = by_position.get(w.position) if w.unit_kind == "dump" else None
        units.append(
            s.UnitRow(
                position=w.position, kind=w.unit_kind, gross_t=w.gross_t, tare_t=w.tare_t, net_t=w.net_t, capacity_t=w.capacity_t, overload_t=w.overload_t,
                speed_kmh=w.speed_kmh, axles=w.axles, weighed_at=w.weighed_at, carriage_gtk_id=paired[0].carriage_gtk_id if paired else None,
                carriage_name=paired[1] if paired else None, asset_id=paired[0].asset_id if paired else None, inv_number=paired[2] if paired else None,
            )
        )
    carriages = [
        s.CarriageRow(ord=c.ord, carriage_gtk_id=c.carriage_gtk_id, gtk_name=name, model_name=model, asset_id=c.asset_id, inv_number=inv, unit_position=c.unit_position, net_t=c.net_t)
        for c, name, model, inv in car_rows
    ]
    loco = await _identity(db, train.loco_asset_id) if train.loco_asset_id else None
    gtk_loco = None
    if train.loco_gtk_id is not None:
        g = (await db.execute(select(GtkLocomotive).where(GtkLocomotive.gtk_id == train.loco_gtk_id))).scalar_one_or_none()
        if g is not None:
            gtk_loco = s.GtkLocoInfo(gtk_id=g.gtk_id, name=g.name, garage_number=g.garage_number, model_name=g.model_name, is_active=g.is_active)
    gtk_train = None
    if train.gtk_train_id is not None:
        gt = (await db.execute(select(GtkTrain).where(GtkTrain.gtk_id == train.gtk_train_id))).scalar_one_or_none()
        gtk_train = s.TrainGtkInfo(gtk_train_id=train.gtk_train_id, number=gt.number if gt else None, title=gt.title if gt else None, begin_time=gt.begin_time if gt else None, is_open=gt.is_open if gt else None)
    neighbour = lambda cmp, order: select(t.id).where(t.post_id == train.post_id, t.started_at.is_not(None), cmp(t.started_at, train.started_at)).order_by(order).limit(1)  # noqa: E731
    prev_id = next_id = None
    if train.started_at is not None:
        prev_id = (await db.execute(neighbour(lambda a, b: a < b, t.started_at.desc()))).scalar_one_or_none()
        next_id = (await db.execute(neighbour(lambda a, b: a > b, t.started_at.asc()))).scalar_one_or_none()
    corrections = (
        await db.execute(
            select(ScaleCorrection).where(
                ScaleCorrection.is_active,
                or_(ScaleCorrection.train_id == train_id, and_(ScaleCorrection.kind == "loco_alias", ScaleCorrection.loco_number == train.loco_number)),
            ).order_by(ScaleCorrection.created_at.desc())
        )
    ).scalars().all()
    offset = (train.reported_weight_t - train.net_total_t) if train.reported_weight_t is not None and train.net_total_t is not None else None
    cars = train.dump_count or train.carriages_total
    return s.TrainCard(
        id=train.id, post_code=post_code, post_name=post_name, src_id=train.src_id, started_at=train.started_at, finished_at=train.finished_at,
        registered_on=train.registered_on, loco_number=train.loco_number, cargo_name=cargo_name, excavator=train.excavator, operator_code=train.operator_code,
        declared_wagons=train.declared_wagons, wagon_rows=train.wagon_rows, dump_count=train.dump_count, traction_count=train.traction_count,
        reported_weight_t=train.reported_weight_t, doc_weight_t=train.doc_weight_t, net_total_t=train.net_total_t, net_source=train.net_source,
        offset_t=_opt(offset), avg_car_t=_opt(Decimal(str(train.net_total_t)) / cars) if train.net_total_t is not None and cars else None,
        match_status=train.match_status, match_method=train.match_method, flags=list(train.flags or []), loco=loco, gtk_loco=gtk_loco,
        gtk_train=gtk_train, units=units, carriages=carriages, prev_id=prev_id, next_id=next_id,
        corrections=[s.CorrectionBrief(id=c.id, kind=c.kind, loco_number=c.loco_number, note=c.note, created_at=c.created_at) for c in corrections],
    )
