"""The pure planning engine of the 'Tirik reja' model."""
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.services.maintenance_engine import (
    CalendarInput, MeterInput, ObligationDraft, Pace, compute_markers, confidence, covered_interval_ids,
    daily_deltas, estimate_pace, group_pace, merge_visits, priority_score, project_date, quantile,
)

TODAY = date(2026, 11, 16)


def pace(p25, p50, p75, n=30, source="asset"):
    return Pace(D(p25), D(p50), D(p75), n, source)


# ── pace ─────────────────────────────────────────────────────────────────────

def test_quantile_matches_percentile_cont():
    values = [D(v) for v in (10, 20, 30, 40)]
    assert quantile(values, 0.5) == D(25)
    assert quantile(values, 0.25) == D("17.5")
    assert quantile(values, 0.75) == D("32.5")
    assert quantile([D(7)], 0.9) == D(7)
    with pytest.raises(ValueError):
        quantile([], 0.5)


def test_daily_deltas_count_idle_days_as_zero_and_clamp_corrections():
    d0 = date(2026, 11, 1)
    readings = [(d0, D(100)), (d0 + timedelta(days=1), D(150)), (d0 + timedelta(days=3), D(180)), (d0 + timedelta(days=4), D(170))]
    deltas = daily_deltas(readings, first_day=d0, last_day=d0 + timedelta(days=5))
    # day1 +50, day2 idle 0, day3 +30, day4 correction (-10) -> 0, day5 idle 0
    assert deltas == [D(50), D(0), D(30), D(0), D(0)]


def test_daily_deltas_without_data_or_before_the_first_reading():
    assert daily_deltas([], first_day=TODAY, last_day=TODAY) == []
    d0 = date(2026, 11, 10)
    # window starts 5 days before the first reading: those days are not "idle", they are unknown
    assert daily_deltas([(d0, D(10)), (d0 + timedelta(days=1), D(25))], first_day=d0 - timedelta(days=5), last_day=d0 + timedelta(days=1)) == [D(15)]


def test_asset_with_a_month_of_data_is_dominated_by_its_own_pace():
    own = [D(50)] * 30
    group = pace(100, 100, 100, source="group")
    result = estimate_pace(own, group=group, fallback_per_day=D(200))
    assert result.source == "asset" and result.n_days == 30
    # weight 30/37 on its own 50 km/day and 7/37 on the group's 100: 59.5, still dominated by its own data
    assert D(55) < result.p50 < D(60)


def test_thin_data_is_pulled_toward_the_group_and_labelled_blend():
    result = estimate_pace([D(10)] * 3, group=pace(60, 60, 60, source="group"), fallback_per_day=D(200))
    assert result.source == "blend"
    # weight 3/10 own + 7/10 group = 3 + 42
    assert result.p50 == D(45)


def test_enough_own_data_without_a_group_is_not_diluted_by_the_flat_fallback():
    result = estimate_pace([D(54)] * 30, group=None, fallback_per_day=D(200))
    assert (result.source, result.p50) == ("asset", D(54))
    thin = estimate_pace([D(54)] * 3, group=None, fallback_per_day=D(200))
    assert thin.source == "blend" and D(54) < thin.p50 < D(200)  # thin data still leans on the fallback


def test_no_data_uses_the_group_then_the_fallback_and_says_so():
    from_group = estimate_pace([], group=pace(40, 50, 60, source="group"), fallback_per_day=D(200))
    assert (from_group.source, from_group.p50, from_group.n_days) == ("group", D(50), 0)
    fallback = estimate_pace([], group=None, fallback_per_day=D(200), fallback_source="setting")
    assert (fallback.source, fallback.p50, fallback.p25, fallback.p75) == ("setting", D(200), D(200), D(200))
    assert not fallback.reliable


def test_group_pace_is_the_median_of_members_that_have_history():
    members = [pace(10, 20, 30, n=10), pace(30, 40, 50, n=10), pace(50, 60, 70, n=10), pace(900, 900, 900, n=0)]
    group = group_pace(members)
    assert group is not None and group.p50 == D(40)
    assert group_pace([pace(1, 1, 1, n=0)]) is None


# ── dates ────────────────────────────────────────────────────────────────────

def test_project_date():
    assert project_date(TODAY, D(100), D(50)) == TODAY + timedelta(days=2)
    assert project_date(TODAY, D(101), D(50)) == TODAY + timedelta(days=3)
    assert project_date(TODAY, D(100), D(0)) is None
    assert project_date(TODAY, D(-100), D(50)) == TODAY - timedelta(days=2)  # already passed
    assert project_date(TODAY, D(0), D(0)) == TODAY


def km_meter(*, limit=5000, baseline=0, current=4650, p25=40, p50=54, p75=71):
    return MeterInput("km", D(limit), D(baseline), D(current), pace(p25, p50, p75))


def test_markers_order_cautious_typical_slow_and_window():
    m = compute_markers(TODAY, [km_meter()], None, tolerance_pct=D(10), lead_days=7)
    assert m.limiting == "km" and m.used == D(4650) and m.remaining == D(350)
    # 350 km: fast pace 71 -> 5 days, typical 54 -> 7 days, slow 40 -> 9 days
    assert (m.date_p75, m.date_p50, m.date_p25) == (TODAY + timedelta(days=5), TODAY + timedelta(days=7), TODAY + timedelta(days=9))
    assert m.date_p75 <= m.date_p50 <= m.date_p25
    assert m.window_open == TODAY - timedelta(days=2)
    assert m.state == "due_soon"  # window (7 days before the cautious date) is already open
    assert m.tolerance == D(500)


def test_states_forecast_due_soon_over_limit_over_tolerance():
    far = compute_markers(TODAY, [km_meter(current=1000)], None, tolerance_pct=D(10), lead_days=7)
    assert far.state == "forecast"
    at = compute_markers(TODAY, [km_meter(current=5100)], None, tolerance_pct=D(10), lead_days=7)
    assert at.state == "over_limit" and at.remaining == D(-100)
    beyond = compute_markers(TODAY, [km_meter(current=5600)], None, tolerance_pct=D(10), lead_days=7)
    assert beyond.state == "over_tolerance"
    zero_tolerance = compute_markers(TODAY, [km_meter(current=5001)], None, tolerance_pct=D(0), lead_days=7)
    assert zero_tolerance.state == "over_tolerance"


def test_since_last_service_not_grid():
    # serviced late at 6500 km: the next limit is 6500 + 5000, not 10000
    m = compute_markers(TODAY, [km_meter(baseline=6500, current=7000)], None, tolerance_pct=D(10), lead_days=7)
    assert m.used == D(500) and m.remaining == D(4500)


def test_the_meter_that_runs_out_first_decides_and_is_named():
    km = km_meter(limit=5000, current=1000)  # lots of km left
    hours = MeterInput("hours", D(500), D(0), D(480), pace(1, 2, 3))  # 20 h left at 3 h/day = 7 days
    m = compute_markers(TODAY, [km, hours], None, tolerance_pct=D(10), lead_days=7)
    assert m.limiting == "hours" and m.date_p75 == TODAY + timedelta(days=7)

    calendar = CalendarInput(limit_days=30, baseline_date=TODAY - timedelta(days=28))
    m = compute_markers(TODAY, [km], calendar, tolerance_pct=D(10), lead_days=7)
    assert m.limiting == "days" and m.date_p75 == TODAY + timedelta(days=2)


def test_overrun_projection_and_tolerance_check():
    m = compute_markers(TODAY, [km_meter(current=4800)], None, tolerance_pct=D(10), lead_days=7)
    assert m.overrun_on(TODAY) == D(0)
    # +10 days at 54 km/day = 540 km -> 5340 used -> 340 over, inside the 500 tolerance
    assert m.overrun_on(TODAY + timedelta(days=10)) == D(340)
    assert not m.beyond_tolerance_on(TODAY + timedelta(days=10))
    assert m.beyond_tolerance_on(TODAY + timedelta(days=20))


def test_without_any_pace_or_calendar_nothing_is_projected():
    parked = MeterInput("km", D(5000), D(0), D(1000), pace(0, 0, 0))
    m = compute_markers(TODAY, [parked], None, tolerance_pct=D(10), lead_days=7)
    assert m.date_p75 is None and m.window_open is None and m.state == "forecast"
    empty = compute_markers(TODAY, [], None, tolerance_pct=D(10), lead_days=7)
    assert empty.limiting is None and empty.date_p75 is None


def test_confidence():
    solid = pace(1, 2, 3, n=30)
    assert confidence(baseline_source="completed", pace=solid, stale=False) == "high"
    assert confidence(baseline_source="provisional", pace=solid, stale=False) == "low"
    assert confidence(baseline_source="completed", pace=pace(1, 2, 3, n=2, source="blend"), stale=False) == "low"
    assert confidence(baseline_source="completed", pace=solid, stale=True) == "stale"


# ── cascade and visits ───────────────────────────────────────────────────────

def test_completing_a_higher_rank_covers_every_lower_rank_and_itself():
    ranks = {"to1": 1, "to2": 2, "to3": 3, "tr1": 4, "test": None}
    assert set(covered_interval_ids(ranks, "to3")) == {"to1", "to2", "to3"}
    assert set(covered_interval_ids(ranks, "to1")) == {"to1"}
    assert covered_interval_ids(ranks, "test") == ["test"]  # unranked is independent
    assert "test" not in covered_interval_ids(ranks, "tr1")


def draft(key, rank, limit_km, current, baseline=0, p50=54, p75=60):
    markers = compute_markers(TODAY, [MeterInput("km", D(limit_km), D(baseline), D(current), pace(p50 - 10, p50, p75))], None, tolerance_pct=D(10), lead_days=7)
    return ObligationDraft(key=key, rank=rank, limit_km=D(limit_km), markers=markers)


def test_a_lower_rank_due_shortly_before_a_higher_one_is_merged_into_one_visit():
    to1 = draft("to1", 1, 5000, current=4850)   # due in ~3 days
    to2 = draft("to2", 2, 15000, current=14700)  # due in ~5 days: 2 days later, inside 15 % of 5000 km = 14 days
    merge_visits([to1, to2], merge_pct=D(15))
    assert to1.merged_into == "to2"
    assert to1.planned_date == to2.planned_date == to1.markers.date_p75  # the earlier date wins


def test_far_apart_ranks_stay_separate_visits():
    to1 = draft("to1", 1, 5000, current=4850)
    to3 = draft("to3", 3, 30000, current=20000)
    merge_visits([to1, to3], merge_pct=D(15))
    assert to1.merged_into is None and to3.planned_date == to3.markers.date_p75


def test_a_higher_rank_that_falls_due_before_the_lower_one_is_not_a_merge():
    to1 = draft("to1", 1, 5000, current=3000)
    to2 = draft("to2", 2, 15000, current=14900)
    merge_visits([to1, to2], merge_pct=D(15))
    assert to1.merged_into is None


# ── priority ─────────────────────────────────────────────────────────────────

def test_priority_rises_as_the_limit_approaches_and_explains_itself():
    near = priority_score(days_to_limit=3, pace_p75=D(71), health=0.2, deferrals=0, ready=True)
    far = priority_score(days_to_limit=55, pace_p75=D(71), health=0.2, deferrals=0, ready=True)
    over = priority_score(days_to_limit=-4, pace_p75=D(71), health=0.2, deferrals=2, ready=False, baseline_provisional=True)
    assert 0 <= far.score < near.score < over.score <= 100
    assert over.score >= 80  # a reached limit always outranks an approaching one
    assert any("до лимита ~3 дн." in line for line in near.why)
    assert any("уже достигнут" in line for line in over.why) and any("предположительная" in line for line in over.why)
    assert any("переносов: 2" in line for line in over.why)


def test_priority_is_bounded_and_survives_missing_inputs():
    worst = priority_score(days_to_limit=-100, pace_p75=None, health=5.0, deferrals=99, ready=False, consequence=1.0)
    assert worst.score <= 100
    blank = priority_score(days_to_limit=None, pace_p75=None, health=None, deferrals=0, ready=None)
    assert 0 <= blank.score <= 100
