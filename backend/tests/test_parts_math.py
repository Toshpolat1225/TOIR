"""Spare-part analytics maths: horizons, age cohorts, repeat cycles, demand rule and the stock-risk verdicts (no database)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services import parts_math as pm

TODAY = date(2026, 11, 26)


def test_age_cohorts_follow_the_documented_rule():
    assert pm.age_cohort(2026 - 10, TODAY) == "new"
    assert pm.age_cohort(2026 - 11, TODAY) == "middle"
    assert pm.age_cohort(2026 - 24, TODAY) == "middle"
    assert pm.age_cohort(2026 - 25, TODAY) == "old"
    assert pm.age_cohort(None, TODAY) == "unknown" and pm.age_cohort(0, TODAY) == "unknown"


def test_asset_groups_and_departments_match_the_demo_mapping():
    assert [pm.asset_group(t) for t in ("diesel", "locomotive", "wagon", "tank_car", "platform", None)] == ["diesel", "locomotive", "wagon", "wagon", "wagon", "wagon"]
    assert pm.demand_department("diesel", "ТО-1") == "Участок ПТОЛ"
    assert pm.demand_department("locomotive", "ТР-1") == "Электровозное депо"
    assert pm.demand_department("wagon", "ТО-2В") == "Участок ПТОВ"
    assert pm.demand_department("tank_car", "ДР") == "Участок ВРП" and pm.demand_department("wagon", "КРВ") == "Участок ВРП"


def test_period_prefers_days_then_km_over_the_daily_pace():
    assert pm.period_days(180, Decimal(5000), Decimal(100)) == 180
    assert pm.period_days(None, Decimal(5000), Decimal(100)) == 50
    assert pm.period_days(None, Decimal(5000), None) is None
    assert pm.period_days(None, None, Decimal(100)) is None


def test_occurrences_repeat_inside_the_horizon_and_overdue_counts_once():
    end = TODAY + timedelta(days=90)
    assert pm.occurrences(TODAY + timedelta(days=10), 30, end, repeats=True) == [TODAY + timedelta(days=d) for d in (10, 40, 70)]
    assert pm.occurrences(TODAY + timedelta(days=10), 30, end, repeats=False) == [TODAY + timedelta(days=10)]
    assert pm.occurrences(TODAY - timedelta(days=5), None, end, repeats=True) == [TODAY - timedelta(days=5)]
    assert pm.occurrences(TODAY + timedelta(days=200), 30, end, repeats=True) == []
    assert pm.occurrences(None, 30, end, repeats=True) == []
    assert len(pm.occurrences(TODAY, 1, TODAY + timedelta(days=5000), repeats=True)) == pm.MAX_REPEATS


def _row(code, rank, days, first, asset="a1", km=None):
    return pm.PlanRow(plan_id=f"p-{asset}-{code}", asset_id=asset, inv_number=asset, asset_type="diesel", section_id="s", year=2000, interval_code=code, interval_name=code,
                      work_type_id="w", work_type_code=code, rank=rank, interval_days=days, interval_km=km, scheduled_date=TODAY + timedelta(days=first))


def test_a_bigger_repair_covers_the_smaller_one_next_to_it():
    small, big = _row("ТО-1", 1, 30, 10), _row("ТО-2", 2, 60, 10)
    end = TODAY + timedelta(days=100)
    occ = pm.expand_plan([small, big], TODAY, end, {}, repeats=True, fallback_km=200)
    got = sorted((o.row.interval_code, (o.on - TODAY).days, o.projected) for o in occ)
    # ТО-1 at 10 (own plan row) stays; its repeats at 40 and 70 are next to the ТО-2 repeat at 70 only -> 70 dropped, 40 stays
    assert ("ТО-1", 10, False) in got and ("ТО-2", 10, False) in got and ("ТО-2", 70, True) in got
    assert ("ТО-1", 40, True) in got and ("ТО-1", 70, True) not in got and ("ТО-1", 100, True) in got  # 100 is 30 days from the ТО-2 at 70: not covered
    # without repeats only the plan rows are counted
    only = pm.expand_plan([small, big], TODAY, end, {}, repeats=False, fallback_km=200)
    assert len(only) == 2 and not any(o.projected for o in only)


def test_horizon_counts_split_planned_and_projected():
    rows = [_row("ТО-1", 1, 30, -3), _row("ТР-1", 4, 400, 100, asset="a2")]
    occ = pm.expand_plan(rows, TODAY, TODAY + timedelta(days=365), {}, repeats=True, fallback_km=200)
    c = pm.horizon_counts(occ, TODAY)
    assert c["quarter"]["planned"] == 1 and c["quarter"]["overdue"] == 1 and c["quarter"]["projected"] == 3  # repeats at +27, +57, +87
    assert c["half"]["planned"] == 2 and c["year"]["planned"] == 2


def test_daily_demand_takes_the_larger_of_history_and_plan():
    assert pm.daily_demand(30, 0) == 1.0
    assert pm.daily_demand(0, 90) == 1.0
    assert pm.daily_demand(60, 90) == 2.0


def _inp(stock, daily_per_day, lead=30, safety=14, orders=(), planned=None, price=100.0):
    return pm.RiskInput(stock=stock, daily_hist=daily_per_day, planned=planned or {}, lead_time_days=lead, safety_days=safety, orders=list(orders), price=price, unit="шт.")


def test_no_balance_is_no_data():
    r = pm.assess(_inp(None, 1.0))
    assert r["status"] == "no_data" and r["runs_out_in_days"] is None and "1С" in r["message"]


def test_critical_when_stock_ends_before_the_delivery_and_nothing_arrives():
    r = pm.assess(_inp(20, 1.0, lead=45))
    assert r["status"] == "critical" and r["runs_out_in_days"] == 20 and r["order_arrives_in_days"] is None
    assert "20 дн." in r["message"] and "срок поставки 45 дн." in r["message"]
    late = pm.assess(_inp(20, 1.0, lead=45, orders=[pm.OpenOrder(10, 60)]))
    assert late["status"] == "critical" and late["order_arrives_in_days"] == 60 and "позже" in late["message"]


def test_an_order_that_lands_in_time_extends_the_cover():
    r = pm.assess(_inp(20, 1.0, lead=45, orders=[pm.OpenOrder(100, 15)]))
    assert r["order_arrives_in_days"] == 15 and r["runs_out_with_orders_in_days"] == 120 and r["status"] == "ok"
    assert "заказ придёт через 15 дн." in r["message"]


def test_order_now_when_the_need_date_is_inside_the_lead_time():
    r = pm.assess(_inp(60, 1.0, lead=40, safety=14))  # runs out in 60 >= lead 40 (not critical); need_by 46 > 40 -> ok
    assert r["status"] == "ok"
    r = pm.assess(_inp(50, 1.0, lead=40, safety=14))  # need_by 36 <= 40 -> order now
    assert r["status"] == "order_now" and r["need_by_days"] == 36 and r["order_by_in_days"] == -4 and "заказывать нужно сейчас" in r["message"]


def test_missing_lead_time_uses_30_days_and_is_flagged():
    r = pm.assess(pm.RiskInput(stock=10, daily_hist=1.0, planned={}, lead_time_days=None, safety_days=None))
    assert r["lead_time_days"] == 30 and r["lead_time_unknown"] is True and r["safety_days"] == 14 and r["status"] == "critical"
    assert "по умолчанию" in r["message"]


def test_no_demand_is_ok_without_a_run_out_date():
    r = pm.assess(_inp(5, 0.0))
    assert r["status"] == "ok" and r["runs_out_in_days"] is None


def test_planned_demand_drives_the_daily_figure_and_the_coverage():
    r = pm.assess(_inp(90, 0.0, planned={"quarter": 180.0, "half": 300.0, "year": 500.0}, price=10.0))
    assert r["daily_demand"] == 2.0 and r["runs_out_in_days"] == 45
    cov = r["coverage"]
    assert cov["quarter"]["covers"] is False and cov["quarter"]["shortfall_qty"] == 90.0 and cov["quarter"]["shortfall_cost"] == 900.0
    assert r["shortfall_cost_year"] == 4100.0


def test_open_orders_reduce_the_shortfall_but_a_covered_horizon_says_yes():
    r = pm.assess(_inp(10, 0.0, planned={"quarter": 30.0, "half": 30.0, "year": 30.0}, orders=[pm.OpenOrder(25, 5)]))
    assert r["coverage"]["year"]["covers"] is True and r["shortfall_cost_year"] == 0.0


def test_an_order_without_a_date_is_assumed_to_come_after_the_lead_time():
    r = pm.assess(_inp(10, 1.0, lead=30, orders=[pm.OpenOrder(50, None)]))
    assert r["order_arrives_in_days"] == 30 and r["status"] == "critical"


@pytest.mark.parametrize("series,expected", [([1] * 5, (None, None)), ([10, 10, 10, 20, 20, 20], (100.0, "up")), ([20, 20, 20, 10, 10, 10], (-50.0, "down")), ([10, 10, 10, 10, 10, 10], (0.0, "flat")), ([0, 0, 0, 5, 5, 5], (None, "up"))])
def test_trend_compares_the_last_three_months_with_the_three_before(series, expected):
    assert pm.trend([float(x) for x in series]) == expected
