"""Spare-part analytics: repair forecast, parts demand, actual consumption and the stock risk. See services/parts_math.py for the rules."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timeutil import today_local
from app.models.identity import User
from app.repositories import parts_analytics as repo
from app.services import avg_daily_mileage
from app.services import parts_math as pm

RISK_SORT = {"status", "name", "stock", "runs_out_in_days", "need_by_days", "shortfall_cost_year", "daily_demand"}
RISK_STATUSES = {"critical", "order_now", "ok", "no_data"}


def _f(x: Any) -> float:
    return float(x) if x is not None else 0.0


def effective_section(user: User, section_id: UUID | None) -> UUID | None:
    """A master gets his own section; another section is 404 (before anything else)."""
    if user.role == "master":
        if user.section_id is None:
            raise HTTPException(status_code=403, detail="Master user must be assigned to a section")
        if section_id is not None and section_id != user.section_id:
            raise HTTPException(status_code=404, detail="Analytics data not found")
        return user.section_id
    return section_id


async def _daily_km(db: AsyncSession, section_id: UUID | None) -> dict[tuple[Any, str], Decimal | None]:
    out: dict[tuple[Any, str], Decimal | None] = {}
    for row in await avg_daily_mileage.compute(db, section_id=section_id):
        if row["avg_daily_km"] is not None and row["with_data_count"] >= avg_daily_mileage.MIN_NORM_UNITS:
            out[(row["section_id"], row["asset_type"])] = row["avg_daily_km"]
    return out


async def _occurrences(db: AsyncSession, section_id: UUID | None, today: date, end: date, repeats: bool) -> list[pm.Occurrence]:
    rows = await repo.plan_rows(db, end=end, section_id=section_id)
    plan = [pm.PlanRow(
        plan_id=r["plan_id"], asset_id=r["asset_id"], inv_number=r["inv_number"], asset_type=r["asset_type"], section_id=r["section_id"], year=r["year"],
        interval_code=r["interval_code"], interval_name=r["interval_name"], work_type_id=r["work_type_id"], work_type_code=r["work_type_code"], rank=r["rank"],
        interval_days=r["interval_days"], interval_km=r["interval_km"], scheduled_date=r["scheduled_date"], status=r["status"]) for r in rows]
    km = await _daily_km(db, section_id) if repeats else {}
    return pm.expand_plan(plan, today, end, km, repeats=repeats, fallback_km=float(settings.daily_km_estimate))


# ------------------------------------------------------------------------------------------------------------------------ repair forecast


async def repair_forecast(db: AsyncSession, user: User, *, horizon: str, section_id: UUID | None, include_cycles: bool, upcoming_limit: int = 20) -> dict[str, Any]:
    section = effective_section(user, section_id)
    today = today_local()
    end = today + timedelta(days=pm.HORIZON_DAYS[horizon])
    occ = [o for o in await _occurrences(db, section, today, end, include_cycles)]
    items: dict[str, dict[str, Any]] = {}
    totals = {"planned": 0, "projected": 0, "overdue": 0}
    by_type: dict[str, int] = defaultdict(int)
    by_age: dict[str, int] = defaultdict(int)
    for o in occ:
        r = o.row
        it = items.setdefault(r.interval_code, {
            "interval_code": r.interval_code, "interval_name": r.interval_name, "work_type_code": r.work_type_code, "rank": r.rank,
            "planned": 0, "projected": 0, "total": 0, "by_asset_type": {"locomotive": 0, "diesel": 0, "wagon": 0}, "by_age": {"new": 0, "middle": 0, "old": 0, "unknown": 0}})
        key = "projected" if o.projected else "planned"
        it[key] += 1
        it["total"] += 1
        group, cohort = pm.asset_group(r.asset_type), pm.age_cohort(r.year, today)
        it["by_asset_type"][group] += 1
        it["by_age"][cohort] += 1
        totals[key] += 1
        by_type[group] += 1
        by_age[cohort] += 1
        if o.on < today and not o.projected:
            totals["overdue"] += 1
    upcoming = sorted((o for o in occ if not o.projected), key=lambda o: (-(o.row.rank if o.row.rank is not None else -1), o.on, o.row.inv_number))
    return {
        "horizon": horizon, "horizon_days": pm.HORIZON_DAYS[horizon], "today": today, "date_to": end, "section_id": section, "include_cycles": include_cycles,
        "age_rule": f"new: age <= {pm.NEW_MAX_AGE} years, old: age >= {pm.OLD_MIN_AGE}, middle: between; age = current year - commissioning year (else year built)",
        "summary": {**totals, "total": totals["planned"] + totals["projected"], "by_asset_type": {k: by_type.get(k, 0) for k in ("locomotive", "diesel", "wagon")},
                    "by_age": {k: by_age.get(k, 0) for k in ("new", "middle", "old", "unknown")}},
        "items": sorted(items.values(), key=lambda i: (-i["total"], i["interval_code"])),
        "upcoming": [{"asset_id": o.row.asset_id, "inv_number": o.row.inv_number, "asset_type": o.row.asset_type, "interval_code": o.row.interval_code,
                      "interval_name": o.row.interval_name, "scheduled_date": o.on, "days_left": (o.on - today).days, "overdue": o.on < today, "status": o.row.status,
                      "age_cohort": pm.age_cohort(o.row.year, today)} for o in upcoming[:upcoming_limit]],
    }


# ------------------------------------------------------------------------------------------------------------------------ parts demand


async def _planned_demand(db: AsyncSession, section_id: UUID | None, today: date, repeats: bool) -> tuple[dict[UUID, dict[str, dict[str, float]]], list[dict[str, Any]], dict[UUID, float]]:
    """(per nomenclature: horizon -> {qty, cost}; norm gaps; reference price per nomenclature)."""
    end = today + timedelta(days=pm.HORIZON_DAYS["year"])
    occ = await _occurrences(db, section_id, today, end, repeats)
    wt_ids = sorted({o.row.work_type_id for o in occ if o.row.work_type_id is not None}, key=str)
    norms: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    prices: dict[UUID, list[float]] = defaultdict(list)
    for n in await repo.norms_for(db, wt_ids):
        norms[(n["department"], n["work_type_id"])].append(n)
        if n["avg_price"]:
            prices[n["nomenclature_id"]].append(float(n["avg_price"]))
    # repairs per (department, work type, horizon)
    counts: dict[tuple[str, Any], dict[str, int]] = defaultdict(lambda: {h: 0 for h in pm.HORIZON_DAYS})
    gaps: dict[tuple[str, str], dict[str, Any]] = {}
    for o in occ:
        dept = pm.demand_department(o.row.asset_type, o.row.work_type_code)
        key = (dept, o.row.work_type_id)
        if o.row.work_type_id is None or key not in norms:
            g = gaps.setdefault((o.row.interval_code, dept), {"interval_code": o.row.interval_code, "department": dept, "repairs_year": 0,
                                                              "reason": "interval is not linked to a work type" if o.row.work_type_id is None else "no norms for this repair kind in the department"})
            g["repairs_year"] += 1
            continue
        for h, days in pm.HORIZON_DAYS.items():
            if o.on <= today + timedelta(days=days):
                counts[key][h] += 1
    demand: dict[UUID, dict[str, dict[str, float]]] = {}
    for key, per_h in counts.items():
        for n in norms[key]:
            slot = demand.setdefault(n["nomenclature_id"], {h: {"qty": 0.0, "cost": 0.0} for h in pm.HORIZON_DAYS})
            for h, c in per_h.items():
                slot[h]["qty"] += c * _f(n["standard_quantity"])
                slot[h]["cost"] += c * _f(n["standard_quantity"]) * _f(n["avg_price"])
    ref_price = {nid: sum(v) / len(v) for nid, v in prices.items()}
    return demand, sorted(gaps.values(), key=lambda g: -g["repairs_year"]), ref_price


async def parts_demand(db: AsyncSession, user: User, *, horizon: str, section_id: UUID | None, include_cycles: bool, limit: int, offset: int) -> dict[str, Any]:
    section = effective_section(user, section_id)
    today = today_local()
    demand, gaps, _price = await _planned_demand(db, section, today, include_cycles)
    hist = {r["nomenclature_id"]: r for r in await repo.history_totals(db, date_from=today - timedelta(days=30 * pm.HISTORY_MONTHS), section_id=section)}
    ids = sorted(set(demand) | set(hist), key=str)
    meta = await repo.nomenclature_meta(db, ids)
    rows: list[dict[str, Any]] = []
    for nid in ids:
        m = meta.get(nid)
        if not m:
            continue
        d = demand.get(nid)
        h = hist.get(nid)
        monthly = _f(h["qty"]) / pm.HISTORY_MONTHS if h else 0.0
        row = {"nomenclature_id": nid, "name": m["name"], "code": m["code"], "unit": m["unit"], "department": m["department"],
               "qty_quarter": round(d["quarter"]["qty"], 3) if d else 0.0, "qty_half": round(d["half"]["qty"], 3) if d else 0.0, "qty_year": round(d["year"]["qty"], 3) if d else 0.0,
               "cost_quarter": round(d["quarter"]["cost"], 2) if d else 0.0, "cost_half": round(d["half"]["cost"], 2) if d else 0.0, "cost_year": round(d["year"]["cost"], 2) if d else 0.0,
               "history_monthly_avg": round(monthly, 3), "history_monthly_cost": round(_f(h["cost"]) / pm.HISTORY_MONTHS, 2) if h else 0.0,
               "note": None if d else "Нет нормы расхода для запланированных ремонтов: показан только средний расход по истории"}
        rows.append(row)
    key = {"quarter": "cost_quarter", "half": "cost_half", "year": "cost_year", "all": "cost_year"}[horizon]
    if horizon != "all":
        rows = [r for r in rows if r[f"qty_{horizon}"] > 0]
    rows.sort(key=lambda r: (-r[key], -r["history_monthly_cost"], r["name"]))
    total = len(rows)
    return {
        "horizon": horizon, "today": today, "section_id": section, "include_cycles": include_cycles, "items": rows[offset:offset + limit], "total": total, "limit": limit, "offset": offset,
        "summary": {"cost_quarter": round(sum(r["cost_quarter"] for r in rows), 2), "cost_half": round(sum(r["cost_half"] for r in rows), 2), "cost_year": round(sum(r["cost_year"] for r in rows), 2),
                    "items_without_norm": sum(1 for r in rows if r["note"])},
        "norm_gaps": gaps,
    }


# ------------------------------------------------------------------------------------------------------------------------ consumption


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


async def parts_consumption(db: AsyncSession, user: User, *, months: int, section_id: UUID | None, limit: int) -> dict[str, Any]:
    section = effective_section(user, section_id)
    today = today_local()
    first = _add_months(_month_start(today), -(months - 1))
    labels = [_add_months(first, i) for i in range(months)]
    rows = await repo.consumption_rows(db, date_from=first, section_id=section)
    per: dict[UUID, dict[str, Any]] = {}
    month_cost: dict[date, float] = defaultdict(float)
    for r in rows:
        p = per.setdefault(r["nomenclature_id"], {"nomenclature_id": r["nomenclature_id"], "name": r["name"], "code": r["code"], "unit": r["unit"], "qty": 0.0, "cost": 0.0,
                                                  "over_qty": 0.0, "over_cost": 0.0, "series": defaultdict(float), "wt": defaultdict(float), "at": defaultdict(float)})
        q = _f(r["qty"])
        p["qty"] += q
        p["cost"] += _f(r["cost"])
        p["over_qty"] += _f(r["over_qty"])
        p["over_cost"] += _f(r["over_cost"])
        p["series"][r["month"]] += q
        p["wt"][r["work_type"] or "—"] += q
        p["at"][pm.asset_group(r["asset_type"]) if r["asset_type"] else "—"] += q
        month_cost[r["month"]] += _f(r["cost"])
    days = max(1, (today - first).days + 1)
    out = []
    for p in per.values():
        full = [p["series"].get(m, 0.0) for m in labels[:-1]]  # complete months only: the current one is partial
        pct, direction = pm.trend(full)
        out.append({
            "nomenclature_id": p["nomenclature_id"], "name": p["name"], "code": p["code"], "unit": p["unit"],
            "total_qty": round(p["qty"], 3), "total_cost": round(p["cost"], 2), "monthly_avg": round(p["qty"] / (days / 30.4375), 3),
            "series": [{"month": m, "qty": round(p["series"].get(m, 0.0), 3)} for m in labels],
            "trend_pct": pct, "trend": direction,
            "over_qty": round(p["over_qty"], 3), "over_cost": round(p["over_cost"], 2),
            "top_work_types": [{"work_type": k, "qty": round(v, 3)} for k, v in sorted(p["wt"].items(), key=lambda kv: -kv[1])[:3]],
            "top_asset_types": [{"asset_type": k, "qty": round(v, 3)} for k, v in sorted(p["at"].items(), key=lambda kv: -kv[1])[:3]],
        })
    out.sort(key=lambda i: (-i["total_cost"], i["name"]))
    for rank, it in enumerate(out, start=1):
        it["rank"] = rank
    return {
        "months": months, "today": today, "date_from": first, "section_id": section,
        "note": "Source: issued TMC documents (status issued/closed). Trend compares the last 3 complete months with the 3 before (needs months >= 7). Overuse = quantity above the repair norm.",
        "totals": {"items": len(out), "cost": round(sum(i["total_cost"] for i in out), 2), "overuse_cost": round(sum(i["over_cost"] for i in out), 2)},
        "monthly_cost": [{"month": m, "cost": round(month_cost.get(m, 0.0), 2)} for m in labels],
        "items": out[:limit],
        "fastest_growing": [i["nomenclature_id"] for i in sorted((i for i in out if i["trend_pct"] is not None), key=lambda i: -i["trend_pct"])[:5]],
        "saving_potential": sorted(({"nomenclature_id": i["nomenclature_id"], "name": i["name"], "unit": i["unit"], "over_qty": i["over_qty"], "over_cost": i["over_cost"]}
                                    for i in out if i["over_cost"] > 0), key=lambda i: -i["over_cost"])[:10],
    }


# ------------------------------------------------------------------------------------------------------------------------ stock risk


async def stock_risk(
    db: AsyncSession, user: User, *, section_id: UUID | None, status: str | None, sort_by: str, sort_dir: str, limit: int, offset: int, include_cycles: bool = True,
) -> dict[str, Any]:
    section = effective_section(user, section_id)  # first: another section is 404 before anything else is looked at
    if sort_by not in RISK_SORT:
        raise HTTPException(status_code=422, detail="Unsupported sort_by")
    if status is not None and status not in RISK_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported status")
    today = today_local()
    demand, _gaps, ref_price = await _planned_demand(db, section, today, include_cycles)
    hist = {r["nomenclature_id"]: r for r in await repo.history_totals(db, date_from=today - timedelta(days=30 * pm.HISTORY_MONTHS), section_id=section)}
    stock = await repo.stock_now(db)
    terms = await repo.supplier_terms_map(db)
    orders: dict[UUID, list[pm.OpenOrder]] = defaultdict(list)
    for o in await repo.open_orders(db):
        days = (o["expected_on"] - today).days if o["expected_on"] else None
        orders[o["nomenclature_id"]].append(pm.OpenOrder(qty_open=_f(o["qty_open"]), expected_in_days=days))
    # a master sees only parts his section needs (planned or issued); stock itself is a shared warehouse figure
    ids = set(demand) | set(hist) if section is not None else set(demand) | set(hist) | set(stock)
    meta = await repo.nomenclature_meta(db, sorted(ids, key=str))
    items: list[dict[str, Any]] = []
    for nid in ids:
        m = meta.get(nid)
        if not m:
            continue
        h = hist.get(nid)
        monthly = _f(h["qty"]) / pm.HISTORY_MONTHS if h else 0.0
        price = ref_price.get(nid) or ((_f(h["cost"]) / _f(h["qty"])) if h and _f(h["qty"]) > 0 else 0.0)
        d = demand.get(nid)
        s = stock.get(nid)
        t = terms.get(nid)
        res = pm.assess(pm.RiskInput(
            stock=_f(s["qty"]) if s else None, daily_hist=monthly / 30.0, planned={k: v["qty"] for k, v in d.items()} if d else {},
            lead_time_days=t["lead_time_days"] if t else None, safety_days=t["safety_days"] if t else None, orders=orders.get(nid, []), price=price, unit=m["unit"] or ""))
        items.append({"nomenclature_id": nid, "name": m["name"], "code": m["code"], "unit": m["unit"], "department": m["department"],
                      "stock": round(_f(s["qty"]), 3) if s else None, "stock_as_of": s["as_of"] if s else None, "stock_age_days": (today - s["as_of"]).days if s else None,
                      "supplier": t["supplier"] if t else None, "price": round(price, 2), "history_monthly_avg": round(monthly, 3), **res})
    summary = {k: sum(1 for i in items if i["status"] == k) for k in ("critical", "order_now", "ok", "no_data")}
    for hz in pm.HORIZON_DAYS:
        summary[f"shortfall_cost_{hz}"] = round(sum(i[f"shortfall_cost_{hz}"] for i in items), 2)
    if status:
        items = [i for i in items if i["status"] == status]

    def keyf(i: dict[str, Any]) -> tuple:
        if sort_by == "status":
            return (pm.STATUS_ORDER[i["status"]], i["runs_out_in_days"] if i["runs_out_in_days"] is not None else 10**9, i["name"])
        v = i[sort_by]
        return (v is None, v if v is not None else 0, i["name"])

    items.sort(key=keyf, reverse=sort_dir == "desc")
    if sort_dir == "desc":  # None values stay last in both directions
        items.sort(key=lambda i: i.get(sort_by) is None and sort_by != "status")
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset, "summary": summary, "today": today, "section_id": section,
            "rule": "daily demand = max(history monthly average / 30, planned demand of the next 90 days / 90)"}
