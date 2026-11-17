"""The wagon ledger: WHICH wagon carried HOW MUCH, WHEN, behind WHICH locomotive, from WHICH quarry.

One row = one trip of one GTK carriage in one weighed train (`scale_train_carriages` x `scale_trains`). The tonnes of a trip, in order of
trust (`basis`):
  own       the car's own weighing, paired with it by GTK order (exact count only);
  train_avg the train's cargo shared equally among its cars (the train total comes from the weighed dump cars);
  estimated the same, but the train total itself is estimated (wagon rows were missing: «Вес» minus the learned offset);
  unknown   no cargo could be determined for the train.
A wagon is identified by its TOIR asset when the GTK carriage is linked, otherwise by the GTK carriage (name / inventory number), so
an unlinked wagon is still visible and becomes an asset trip the moment the link is made (the next re-match fills `asset_id`).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Text, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage
from app.models.scales import ScaleCargo, ScalePost, ScaleTrain, ScaleTrainCarriage
from app.schemas import scales as schemas

EXPORT_LIMIT = 200_000
TRIP_SORT = {"started_at": "started_at", "tonnes": "tonnes", "inv_number": "wagon"}
TOTAL_SORT = {"tonnes": "tonnes", "trips": "trips", "last_at": "last_at", "inv_number": "wagon"}


def local_range(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """Dates are the operators' local days (the scale PCs run on local time)."""
    tz = timezone(timedelta(hours=settings.scales_utc_offset_hours))
    lo = datetime.combine(date_from, time.min, tzinfo=tz) if date_from else None
    hi = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz) if date_to else None
    return lo, hi


def _parts():
    t, tc = ScaleTrain, ScaleTrainCarriage
    denominator = func.nullif(func.coalesce(func.nullif(t.dump_count, 0), func.nullif(t.carriages_total, 0)), 0)
    tonnes = func.coalesce(tc.net_t, t.net_total_t / denominator)
    basis = case(
        (tc.net_t.is_not(None), "own"),
        (tonnes.is_(None), "unknown"),
        (t.net_source == "estimated", "estimated"),
        else_="train_avg",
    )
    wagon = func.coalesce(FixedAsset.inv_number, GtkCarriage.inventory_number, GtkCarriage.name, cast(tc.carriage_gtk_id, Text))
    return t, tc, tonnes, basis, wagon


def _conditions(
    t, tc, *, asset_id: UUID | None, q: str | None, date_from: date | None, date_to: date | None, post: str | None,
    cargo_code: int | None, only_linked: bool, carriage_gtk_id: int | None = None, loco_asset_id: UUID | None = None,
) -> list[Any]:
    cond: list[Any] = [t.match_status == "ok"]
    if carriage_gtk_id is not None:
        cond.append(tc.carriage_gtk_id == carriage_gtk_id)
    if loco_asset_id is not None:
        cond.append(t.loco_asset_id == loco_asset_id)
    lo, hi = local_range(date_from, date_to)
    if lo is not None:
        cond.append(t.started_at >= lo)
    if hi is not None:
        cond.append(t.started_at < hi)
    if asset_id is not None:
        cond.append(tc.asset_id == asset_id)
    if only_linked:
        cond.append(tc.asset_id.is_not(None))
    if post:
        cond.append(ScalePost.code == post)
    if cargo_code is not None:
        cond.append(t.cargo_code == cargo_code)
    if q:
        needle = f"%{q.strip()}%".replace("\x00", "")
        cond.append(
            or_(
                FixedAsset.inv_number.ilike(needle), GtkCarriage.name.ilike(needle), GtkCarriage.inventory_number.ilike(needle),
                GtkCarriage.reg_number.ilike(needle),
            )
        )
    return cond


def _joined(stmt):
    return (
        stmt.select_from(ScaleTrainCarriage)
        .join(ScaleTrain, ScaleTrain.id == ScaleTrainCarriage.train_id)
        .join(ScalePost, ScalePost.id == ScaleTrain.post_id)
        .outerjoin(FixedAsset, FixedAsset.id == ScaleTrainCarriage.asset_id)
        .outerjoin(GtkCarriage, GtkCarriage.gtk_id == ScaleTrainCarriage.carriage_gtk_id)
    )


def _trip_select(**filters):
    t, tc, tonnes, basis, wagon = _parts()
    loco = aliased(FixedAsset)
    stmt = _joined(
        select(
            t.id.label("train_id"), t.started_at, ScalePost.code.label("post_code"), tc.asset_id, FixedAsset.inv_number,
            tc.carriage_gtk_id, GtkCarriage.name.label("gtk_name"), GtkCarriage.inventory_number.label("gtk_inventory_number"),
            tc.unit_position.label("position"), tonnes.label("tonnes"), basis.label("basis"), t.loco_number, t.loco_asset_id,
            loco.inv_number.label("loco_inv_number"), ScaleCargo.name.label("cargo_name"), t.excavator, t.net_total_t.label("train_total_t"),
            wagon.label("wagon"), ScalePost.capacity_norm_t.label("capacity"),
        )
    ).outerjoin(loco, loco.id == t.loco_asset_id).outerjoin(ScaleCargo, ScaleCargo.code == t.cargo_code)
    return stmt.where(*_conditions(t, tc, **filters)), tonnes, wagon


async def wagon_trips(
    db: AsyncSession, *, asset_id: UUID | None, q: str | None, date_from: date | None, date_to: date | None, post: str | None,
    cargo_code: int | None, only_linked: bool, sort_by: str, descending: bool, limit: int, offset: int,
) -> schemas.WagonTripPage:
    if sort_by not in TRIP_SORT:
        raise HTTPException(status_code=422, detail=f"Unknown sort field: {sort_by}")
    filters = dict(asset_id=asset_id, q=q, date_from=date_from, date_to=date_to, post=post, cargo_code=cargo_code, only_linked=only_linked)
    stmt, tonnes, wagon = _trip_select(**filters)
    key = {"started_at": ScaleTrain.started_at, "tonnes": tonnes, "wagon": wagon}[TRIP_SORT[sort_by]]
    order = key.desc().nullslast() if descending else key.asc().nullslast()
    rows = (await db.execute(stmt.order_by(order, ScaleTrain.id, ScaleTrainCarriage.carriage_gtk_id).limit(limit).offset(offset))).all()
    t, tc, tonnes_expr, _basis, _wagon = _parts()
    agg = _joined(select(func.count(), func.count(func.distinct(tc.carriage_gtk_id)), func.coalesce(func.sum(tonnes_expr), 0))).where(
        *_conditions(t, tc, **filters)
    )
    total, wagons, tonnes_total = (await db.execute(agg)).one()
    items = [schemas.WagonTripRead(**{k: v for k, v in r._mapping.items() if k != "wagon"}) for r in rows]
    return schemas.WagonTripPage(
        items=items, total=total, limit=limit, offset=offset, wagons_total=wagons, tonnes_total=Decimal(str(tonnes_total)).quantize(Decimal("0.01"))
    )


async def wagon_totals(
    db: AsyncSession, *, q: str | None, date_from: date | None, date_to: date | None, post: str | None, cargo_code: int | None,
    only_linked: bool, sort_by: str, descending: bool, limit: int, offset: int,
) -> schemas.WagonTotalPage:
    if sort_by not in TOTAL_SORT:
        raise HTTPException(status_code=422, detail=f"Unknown sort field: {sort_by}")
    t, tc, tonnes, _basis, wagon = _parts()
    cond = _conditions(t, tc, asset_id=None, q=q, date_from=date_from, date_to=date_to, post=post, cargo_code=cargo_code, only_linked=only_linked)
    sum_t = func.coalesce(func.sum(tonnes), 0)
    trips = func.count()
    last_at = func.max(t.started_at)
    groups = (
        _joined(
            select(
                tc.carriage_gtk_id, tc.asset_id, FixedAsset.inv_number, GtkCarriage.name.label("gtk_name"),
                GtkCarriage.inventory_number.label("gtk_inventory_number"), wagon.label("wagon"), trips.label("trips"),
                sum_t.label("tonnes"), func.count(tc.net_t).label("own_trips"), last_at.label("last_at"),
            )
        )
        .where(*cond)
        .group_by(tc.carriage_gtk_id, tc.asset_id, FixedAsset.inv_number, GtkCarriage.name, GtkCarriage.inventory_number, wagon)
    )
    sub = groups.subquery()
    total = (await db.execute(select(func.count()).select_from(sub))).scalar_one()
    sums = (await db.execute(select(func.coalesce(func.sum(sub.c.trips), 0), func.coalesce(func.sum(sub.c.tonnes), 0)))).one()
    column = {"tonnes": sub.c.tonnes, "trips": sub.c.trips, "last_at": sub.c.last_at, "wagon": sub.c.wagon}[TOTAL_SORT[sort_by]]
    order = column.desc().nullslast() if descending else column.asc().nullslast()
    rows = (await db.execute(select(sub).order_by(order, sub.c.carriage_gtk_id).limit(limit).offset(offset))).all()
    items = []
    for r in rows:
        tonnes_value = Decimal(str(r.tonnes)).quantize(Decimal("0.01"))
        items.append(
            schemas.WagonTotalRead(
                asset_id=r.asset_id, inv_number=r.inv_number, carriage_gtk_id=r.carriage_gtk_id,
                gtk_name=r.gtk_name, gtk_inventory_number=r.gtk_inventory_number, trips=r.trips, tonnes=tonnes_value,
                avg_tonnes=(tonnes_value / r.trips).quantize(Decimal("0.01")) if r.trips else None, own_trips=r.own_trips, last_at=r.last_at,
            )
        )
    return schemas.WagonTotalPage(
        items=items, total=total, limit=limit, offset=offset, trips_total=int(sums[0]), tonnes_total=Decimal(str(sums[1])).quantize(Decimal("0.01"))
    )


BASIS_RU = {"own": "взвешивание вагона", "train_avg": "доля состава", "estimated": "оценка по весу состава", "unknown": "неизвестно"}
CSV_HEADER = [
    "Дата и время", "Весы", "Вагон (инв. №)", "GTK вагон", "Позиция на весах", "Тонн", "Основание", "Локомотив №", "Локомотив ОС",
    "Груз", "Экскаватор", "Всего в составе, т",
]


async def wagon_trips_csv(db: AsyncSession, **filters: Any) -> str:
    """The ledger as a spreadsheet (UTF-8 with BOM and `;`, which Russian Excel opens directly)."""
    tz = timezone(timedelta(hours=settings.scales_utc_offset_hours))
    stmt, _tonnes, wagon = _trip_select(**filters)
    rows = (await db.execute(stmt.order_by(ScaleTrain.started_at.desc(), wagon).limit(EXPORT_LIMIT))).all()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(CSV_HEADER)
    for r in rows:
        when = r.started_at.astimezone(tz).strftime("%d.%m.%Y %H:%M") if r.started_at else ""
        writer.writerow(
            [
                when, r.post_code, r.inv_number or "", r.gtk_name or r.gtk_inventory_number or r.carriage_gtk_id, r.position or "",
                "" if r.tonnes is None else str(Decimal(str(r.tonnes)).quantize(Decimal("0.01"))).replace(".", ","), BASIS_RU[r.basis],
                r.loco_number or "", r.loco_inv_number or "", r.cargo_name or "", r.excavator or "",
                "" if r.train_total_t is None else str(r.train_total_t).replace(".", ","),
            ]
        )
    return "﻿" + out.getvalue()
