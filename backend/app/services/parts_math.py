"""Pure maths of the spare-part analytics (no database): repair forecast, parts demand and the stock-risk engine.

Rules (all documented in docs/PARTS_ANALYTICS_API.md):
- Horizons: quarter = 90 days, half = 180, year = 365 (counted from today, Tashkent).
- Age cohort of a unit: age = current year - (commissioning year, else year built). new <= 10 years, old >= 25, middle in between, unknown if no year.
- A plan row without a date is not forecast. An overdue plan row (date in the past) counts in every horizon (the repair is still owed).
- Repeat cycles (optional): after the planned date the same interval repeats every `period` days (interval_days, else interval_km / daily km of the
  section+type). A repeat that falls next to an occurrence of a higher-rank interval of the same unit is dropped (the bigger repair covers the smaller).
- Daily demand of a part = max(history monthly average / 30, planned demand of the next 90 days / 90).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

HORIZON_DAYS = {"quarter": 90, "half": 180, "year": 365}
DEFAULT_LEAD_DAYS = 30
DEFAULT_SAFETY_DAYS = 14
NEW_MAX_AGE = 10
OLD_MIN_AGE = 25
MAX_REPEATS = 400
HISTORY_MONTHS = 6
STATUS_ORDER = {"critical": 0, "order_now": 1, "no_data": 2, "ok": 3}


def asset_group(asset_type: str | None) -> str:
    """locomotive / diesel / wagon (every non-locomotive type is a wagon)."""
    return asset_type if asset_type in ("locomotive", "diesel") else "wagon"


def demand_department(asset_type: str | None, work_type_code: str | None) -> str:
    """The department whose norms apply (the same mapping the demo seed uses)."""
    if asset_type == "diesel":
        return "Участок ПТОЛ"
    if asset_type == "locomotive":
        return "Электровозное депо"
    return "Участок ВРП" if work_type_code in ("ДР", "КРВ") else "Участок ПТОВ"


def age_cohort(year: int | None, today: date) -> str:
    if not year or year < 1800:
        return "unknown"
    age = today.year - int(year)
    if age <= NEW_MAX_AGE:
        return "new"
    if age >= OLD_MIN_AGE:
        return "old"
    return "middle"


def period_days(interval_days: int | None, interval_km: Decimal | float | None, daily_km: Decimal | float | None) -> int | None:
    if interval_days and interval_days > 0:
        return int(interval_days)
    if interval_km and daily_km and float(daily_km) > 0 and float(interval_km) > 0:
        return max(1, round(float(interval_km) / float(daily_km)))
    return None


def occurrences(first: date | None, period: int | None, end: date, *, repeats: bool, cap: int = MAX_REPEATS) -> list[date]:
    """Planned date first, then (if repeats and a period is known) every `period` days up to `end`. An overdue date counts as `first` itself."""
    if first is None or first > end:
        return []
    out = [first]
    if repeats and period:
        nxt = first + timedelta(days=period)
        while nxt <= end and len(out) < cap:
            out.append(nxt)
            nxt += timedelta(days=period)
    return out


@dataclass
class PlanRow:
    plan_id: str
    asset_id: str
    inv_number: str
    asset_type: str
    section_id: Any
    year: int | None
    interval_code: str
    interval_name: str
    work_type_id: Any
    work_type_code: str | None
    rank: int | None
    interval_days: int | None
    interval_km: Decimal | None
    scheduled_date: date | None
    status: str = "scheduled"


@dataclass
class Occurrence:
    row: PlanRow
    on: date
    projected: bool


def expand_plan(rows: Iterable[PlanRow], today: date, end: date, daily_km: dict[tuple[Any, str], Decimal | None], *, repeats: bool, fallback_km: float) -> list[Occurrence]:
    """All occurrences up to `end` for every plan row, with the rank-covering filter applied to repeats."""
    by_asset: dict[str, list[PlanRow]] = {}
    for r in rows:
        by_asset.setdefault(r.asset_id, []).append(r)
    result: list[Occurrence] = []
    for asset_rows in by_asset.values():
        staged: list[tuple[PlanRow, int | None, list[date]]] = []
        for r in asset_rows:
            km = daily_km.get((r.section_id, r.asset_type)) or Decimal(str(fallback_km))
            per = period_days(r.interval_days, r.interval_km, km)
            staged.append((r, per, occurrences(r.scheduled_date, per, end, repeats=repeats)))
        for r, per, dates in staged:
            for i, d in enumerate(dates):
                if i > 0 and r.rank is not None and per:
                    covered = any(
                        o.rank is not None and o.rank > r.rank and any(abs((d - od).days) <= per / 2 for od in odates)
                        for o, _p, odates in staged if o is not r
                    )
                    if covered:
                        continue
                result.append(Occurrence(r, d, projected=i > 0))
    return result


def horizon_counts(occ: Iterable[Occurrence], today: date) -> dict[str, dict[str, int]]:
    """For every horizon: planned (own plan rows) and projected (repeat cycles) counts."""
    out = {h: {"planned": 0, "projected": 0, "overdue": 0} for h in HORIZON_DAYS}
    for o in occ:
        for h, days in HORIZON_DAYS.items():
            if o.on <= today + timedelta(days=days):
                out[h]["projected" if o.projected else "planned"] += 1
                if o.on < today and not o.projected:
                    out[h]["overdue"] += 1
    return out


# ---------------------------------------------------------------------------------------------------------------------------------- stock risk


@dataclass
class OpenOrder:
    qty_open: float
    expected_in_days: int | None  # None = no date given


@dataclass
class RiskInput:
    stock: float | None            # None = no 1C balance at all
    daily_hist: float              # history monthly average / 30
    planned: dict[str, float]      # planned demand per horizon (quarter/half/year)
    lead_time_days: int | None
    safety_days: int | None
    orders: list[OpenOrder] = field(default_factory=list)
    price: float = 0.0
    unit: str = ""


def daily_demand(hist_monthly_avg: float, planned_90: float) -> float:
    return max(float(hist_monthly_avg) / 30.0, float(planned_90) / 90.0)


def _fmt(x: float) -> str:
    s = f"{x:,.1f}".replace(",", " ").rstrip("0").rstrip(".") if x != int(x) else f"{int(x)}"
    return s


def assess(inp: RiskInput) -> dict[str, Any]:
    """The stock-risk verdict of one part. See the module docstring for the daily demand rule."""
    lead_unknown = inp.lead_time_days is None
    lead = inp.lead_time_days if inp.lead_time_days else DEFAULT_LEAD_DAYS
    safety = DEFAULT_SAFETY_DAYS if inp.safety_days is None else inp.safety_days
    daily = daily_demand(inp.daily_hist * 30.0, inp.planned.get("quarter", 0.0))
    unit = inp.unit or "шт."
    res: dict[str, Any] = {
        "daily_demand": round(daily, 4), "lead_time_days": lead, "lead_time_unknown": lead_unknown, "safety_days": safety,
        "runs_out_in_days": None, "runs_out_with_orders_in_days": None, "order_arrives_in_days": None, "need_by_days": None,
        "order_by_in_days": None, "open_orders_qty": round(sum(o.qty_open for o in inp.orders), 3),
    }
    # one order date per open order: no date -> assume it arrives after the usual lead time
    dated = sorted(((o.expected_in_days if o.expected_in_days is not None else lead), o.qty_open) for o in inp.orders if o.qty_open > 0)
    res["order_arrives_in_days"] = max(0, dated[0][0]) if dated else None

    if inp.stock is None:
        res.update(status="no_data", message="Нет данных об остатке из 1С: загрузите файл остатков.")
        _coverage(res, inp, daily)
        return res

    stock = float(inp.stock)
    if daily <= 0:
        res.update(status="ok", message=f"Остаток {_fmt(stock)} {unit}: расхода по плану и истории нет, запас не расходуется.")
        _coverage(res, inp, daily)
        return res

    runs_out = int(stock / daily)
    arrives = res["order_arrives_in_days"]
    incoming_in_time = sum(q for d, q in dated if d <= runs_out)
    with_orders = int((stock + incoming_in_time) / daily)
    # an order that lands before the stock is gone extends the cover; later orders do not
    res["runs_out_in_days"] = runs_out
    res["runs_out_with_orders_in_days"] = with_orders
    need_by = with_orders - safety
    res["need_by_days"] = need_by
    res["order_by_in_days"] = need_by - lead

    covered_by_order = arrives is not None and arrives <= runs_out
    if runs_out < lead and not covered_by_order:
        status = "critical"
    elif need_by <= lead:
        status = "order_now"
    else:
        status = "ok"
    res["status"] = status

    parts = [f"Остаток {_fmt(stock)} {unit} хватит на {runs_out} дн."]
    if arrives is not None:
        parts.append(f"заказ придёт через {arrives} дн." + ("" if covered_by_order else " (позже, чем закончится запас)"))
    else:
        parts.append("открытых заказов нет")
    parts.append(f"срок поставки {lead} дн." + (" (не задан, принят по умолчанию)" if lead_unknown else ""))
    if status == "critical":
        parts.append("запас закончится раньше, чем придёт поставка")
    elif status == "order_now":
        parts.append("заказывать нужно сейчас" if res["order_by_in_days"] <= 0 else f"нужно заказать через {res['order_by_in_days']} дн.")
    else:
        parts.append(f"нужно через {max(need_by, 0)} дн.")
    res["message"] = "; ".join(parts) + "."
    _coverage(res, inp, daily)
    return res


def _coverage(res: dict[str, Any], inp: RiskInput, daily: float) -> None:
    stock = float(inp.stock or 0)
    incoming = sum(o.qty_open for o in inp.orders)
    cov: dict[str, Any] = {}
    for h, days in HORIZON_DAYS.items():
        demand = max(float(inp.planned.get(h, 0.0)), (inp.daily_hist) * days)
        short = max(0.0, demand - stock - incoming)
        cov[h] = {"demand": round(demand, 3), "covers": short <= 1e-9 and inp.stock is not None, "shortfall_qty": round(short, 3), "shortfall_cost": round(short * inp.price, 2)}
    res["coverage"] = cov
    res["shortfall_cost_quarter"] = cov["quarter"]["shortfall_cost"]
    res["shortfall_cost_half"] = cov["half"]["shortfall_cost"]
    res["shortfall_cost_year"] = cov["year"]["shortfall_cost"]


def trend(series: list[float]) -> tuple[float | None, str | None]:
    """Last 3 complete months against the 3 before them: (percent change, 'up'|'down'|'flat'). Needs 6 values."""
    if len(series) < 6:
        return None, None
    last3, prev3 = sum(series[-3:]), sum(series[-6:-3])
    if prev3 <= 0:
        return (None, "up") if last3 > 0 else (None, "flat")
    pct = (last3 - prev3) / prev3 * 100.0
    return round(pct, 1), ("up" if pct > 10 else "down" if pct < -10 else "flat")
