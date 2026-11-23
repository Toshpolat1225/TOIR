"""Average daily mileage norm per (section, equipment type) from GPS data.

Two-step selection of the "reference" units, then the mean of their last-7-day daily km:
  big list   = active units with   10% * max <= mileage <= max
  small list = units of the big list with 80% * max <= mileage <= max
Groups never mix: every (section, type) is computed on its own. No data -> no number (never a made-up value).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import today_local
from app.models.assets import FixedAsset
from app.models.localization import FixedAssetTypeTranslation
from app.models.maintenance import AssetMeterDaily
from app.models.mileage import WagonMileageLedger
from app.models.organization import Section

WINDOW_DAYS = 7
MIN_NORM_UNITS = 3  # a norm built on fewer units with GPS data is shown, but not used for forecasts
BIG_FRACTION = Decimal("0.10")
SMALL_FRACTION = Decimal("0.80")
ACTIVE_STATUS = "operational"
WAGON_TYPES = ("wagon", "tank_car", "platform")  # no own GPS: kilometres come from the wagon mileage ledger


@dataclass(frozen=True)
class Unit:
    asset_id: UUID
    mileage: Decimal


@dataclass(frozen=True)
class GroupResult:
    active_count: int
    max_mileage: Decimal | None
    big_count: int
    small_count: int
    with_data_count: int
    avg_daily_km: Decimal | None
    reason: str | None  # None = ok, otherwise why there is no number


def select_lists(units: list[Unit]) -> tuple[Decimal | None, list[Unit], list[Unit]]:
    """(max mileage, big list, small list). Max <= 0 means there is nothing to base the norm on."""
    if not units:
        return None, [], []
    top = max(u.mileage for u in units)
    if top <= 0:
        return top, [], []
    big = [u for u in units if top * BIG_FRACTION <= u.mileage <= top]
    big_top = max(u.mileage for u in big)  # the top of the big list, as the rule says
    small = [u for u in big if big_top * SMALL_FRACTION <= u.mileage <= big_top]
    return top, big, small


def daily_km_from_meter(readings: list[tuple[date, Decimal]]) -> Decimal | None:
    """End-of-day meter values -> km/day over the span. Needs two different days; a falling meter (reset) gives nothing."""
    pts = sorted((d, v) for d, v in readings if v is not None)
    if len(pts) < 2 or pts[-1][0] == pts[0][0]:
        return None
    delta = pts[-1][1] - pts[0][1]
    return None if delta < 0 else delta / (pts[-1][0] - pts[0][0]).days


def evaluate_group(units: list[Unit], daily: dict[UUID, Decimal | None]) -> GroupResult:
    top, big, small = select_lists(units)
    if top is None or top <= 0 or not small:
        return GroupResult(len(units), top, len(big), len(small), 0, None, "no_mileage")
    values = [daily[u.asset_id] for u in small if daily.get(u.asset_id) is not None]
    if not values:
        return GroupResult(len(units), top, len(big), len(small), 0, None, "no_gps_data")
    return GroupResult(len(units), top, len(big), len(small), len(values), (sum(values) / len(values)).quantize(Decimal("0.01")), None)


async def _daily_km(db: AsyncSession, units: list[tuple[UUID, str]], now: datetime) -> dict[UUID, Decimal | None]:
    """Last-7-day km/day per unit: locomotives from the daily meter, wagons from the active wagon mileage ledger."""
    since = now - timedelta(days=WINDOW_DAYS)
    out: dict[UUID, Decimal | None] = {}
    loco_ids = [a for a, t in units if t not in WAGON_TYPES]
    wagon_ids = [a for a, t in units if t in WAGON_TYPES]
    if loco_ids:
        rows = (await db.execute(
            select(AssetMeterDaily.asset_id, AssetMeterDaily.day, AssetMeterDaily.km)
            .where(AssetMeterDaily.asset_id.in_(loco_ids), AssetMeterDaily.day >= today_local(now) - timedelta(days=WINDOW_DAYS), AssetMeterDaily.km.is_not(None))
        )).all()
        series: dict[UUID, list[tuple[date, Decimal]]] = {}
        for a, d, km in rows:
            series.setdefault(a, []).append((d, km))
        out.update({a: daily_km_from_meter(s) for a, s in series.items()})
    if wagon_ids:
        rows = (await db.execute(
            select(WagonMileageLedger.wagon_asset_id, func.coalesce(func.sum(WagonMileageLedger.distance_km), 0), func.count())
            .where(
                WagonMileageLedger.wagon_asset_id.in_(wagon_ids), WagonMileageLedger.status == "active",
                WagonMileageLedger.calculation_eligible.is_(True), WagonMileageLedger.period_from >= since,
            )
            .group_by(WagonMileageLedger.wagon_asset_id)
        )).all()
        out.update({a: Decimal(total) / WINDOW_DAYS for a, total, n in rows if n > 0})
    return out


async def compute(db: AsyncSession, *, section_id: UUID | None = None, now: datetime | None = None) -> list[dict]:
    """One row per (section, type). `section_id` limits it to one section (master)."""
    now = now or datetime.now(timezone.utc)
    type_name = (
        select(FixedAssetTypeTranslation.name)
        .where(FixedAssetTypeTranslation.type_code == FixedAsset.asset_type, FixedAssetTypeTranslation.locale == "ru")
        .limit(1).correlate(FixedAsset).scalar_subquery()
    )
    stmt = (
        select(FixedAsset.id, FixedAsset.asset_type, type_name, FixedAsset.mileage, FixedAsset.section_id, Section.name)
        .join(Section, Section.id == FixedAsset.section_id)
        .where(FixedAsset.status == ACTIVE_STATUS, FixedAsset.decommissioned_at.is_(None))
    )
    if section_id is not None:
        stmt = stmt.where(FixedAsset.section_id == section_id)
    rows = (await db.execute(stmt)).all()
    groups: dict[tuple[UUID, str], dict] = {}
    for aid, atype, tname, mileage, sid, sname in rows:
        g = groups.setdefault((sid, atype), {"section_id": sid, "section_name": sname, "asset_type": atype, "asset_type_name": tname or atype, "units": []})
        g["units"].append(Unit(aid, Decimal(mileage or 0)))
    result: list[dict] = []
    for g in groups.values():
        _, _, small = select_lists(g["units"])
        daily = await _daily_km(db, [(u.asset_id, g["asset_type"]) for u in small], now) if small else {}
        r = evaluate_group(g["units"], daily)
        result.append({
            "section_id": g["section_id"], "section_name": g["section_name"], "asset_type": g["asset_type"], "asset_type_name": g["asset_type_name"],
            "active_count": r.active_count, "max_mileage": r.max_mileage, "big_count": r.big_count, "small_count": r.small_count,
            "with_data_count": r.with_data_count, "avg_daily_km": r.avg_daily_km, "reason": r.reason, "window_days": WINDOW_DAYS,
        })
    result.sort(key=lambda x: (x["section_name"] or "", x["asset_type_name"] or ""))
    return result


async def detail(db: AsyncSession, *, section_id: UUID, asset_type: str, now: datetime | None = None) -> dict | None:
    """Step-by-step breakdown of one group: every big-list unit, who is in the small list, and how each unit's km/day was obtained."""
    from app.models.assets import fixed_asset_name_expression

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    stmt = (
        select(FixedAsset.id, FixedAsset.inv_number, fixed_asset_name_expression(), FixedAsset.mileage, Section.name)
        .join(Section, Section.id == FixedAsset.section_id)
        .where(FixedAsset.status == ACTIVE_STATUS, FixedAsset.decommissioned_at.is_(None),
               FixedAsset.section_id == section_id, FixedAsset.asset_type == asset_type)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None
    meta = {r[0]: r for r in rows}
    units = [Unit(r[0], Decimal(r[3] or 0)) for r in rows]
    top, big, small = select_lists(units)
    small_ids = {u.asset_id for u in small}
    notes: dict[UUID, dict] = {}
    if small_ids and asset_type not in WAGON_TYPES:
        q = (await db.execute(
            select(AssetMeterDaily.asset_id, AssetMeterDaily.day, AssetMeterDaily.km)
            .where(AssetMeterDaily.asset_id.in_(small_ids), AssetMeterDaily.day >= today_local(now) - timedelta(days=WINDOW_DAYS), AssetMeterDaily.km.is_not(None))
        )).all()
        series: dict[UUID, list[tuple[date, Decimal]]] = {}
        for a, d, km in q:
            series.setdefault(a, []).append((d, km))
        for a, pts in series.items():
            pts.sort()
            notes[a] = {"daily": daily_km_from_meter(pts), "source": "meter", "first_day": pts[0][0], "first_km": pts[0][1],
                        "last_day": pts[-1][0], "last_km": pts[-1][1], "readings": len(pts)}
    elif small_ids:
        q = (await db.execute(
            select(WagonMileageLedger.wagon_asset_id, func.coalesce(func.sum(WagonMileageLedger.distance_km), 0), func.count())
            .where(WagonMileageLedger.wagon_asset_id.in_(small_ids), WagonMileageLedger.status == "active",
                   WagonMileageLedger.calculation_eligible.is_(True), WagonMileageLedger.period_from >= since)
            .group_by(WagonMileageLedger.wagon_asset_id)
        )).all()
        for a, total, n in q:
            if n > 0:
                notes[a] = {"daily": Decimal(total) / WINDOW_DAYS, "source": "ledger", "total_km": Decimal(total), "readings": n}
    values = [n["daily"] for n in notes.values() if n.get("daily") is not None]
    avg = (sum(values) / len(values)).quantize(Decimal("0.01")) if values else None
    out_units = []
    for u in sorted(big, key=lambda x: x.mileage, reverse=True):
        r = meta[u.asset_id]
        n = notes.get(u.asset_id, {})
        out_units.append({
            "asset_id": u.asset_id, "inv_number": r[1], "name": r[2], "mileage": u.mileage,
            "percent_of_max": (u.mileage / top * 100).quantize(Decimal("0.1")), "in_small": u.asset_id in small_ids,
            "daily_km": (n["daily"].quantize(Decimal("0.01")) if n.get("daily") is not None else None),
            "source": n.get("source"), "first_day": n.get("first_day"), "first_km": n.get("first_km"),
            "last_day": n.get("last_day"), "last_km": n.get("last_km"), "total_km": n.get("total_km"), "readings": n.get("readings"),
        })
    return {
        "section_id": section_id, "section_name": rows[0][4], "asset_type": asset_type, "active_count": len(units), "max_mileage": top,
        "big_low": (top * BIG_FRACTION) if top else None, "small_low": (top * SMALL_FRACTION) if top else None,
        "big_count": len(big), "small_count": len(small), "with_data_count": len(values), "avg_daily_km": avg,
        "window_days": WINDOW_DAYS, "units": out_units,
    }
