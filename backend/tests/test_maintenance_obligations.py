"""Evaluating assets into obligations and persisting them (no database: the context is built by hand)."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.services import maintenance_obligations as mo
from app.services.maintenance_engine import Pace

TODAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)


def asset(*, mileage=4650, asset_type="locomotive", status="operational", failure=None, decommissioned=None):
    return SimpleNamespace(
        id=uuid4(), asset_type=asset_type, status=status, mileage=D(mileage), decommissioned_at=decommissioned,
        failure_probability=failure, section_id=uuid4(),
    )


def interval(*, code="ТО-1", km=5000, days=None, hours=None, rank=1, tol=10, lead=7, types=("locomotive", "diesel", "wagon")):
    return SimpleNamespace(
        id=uuid4(), code=code, name=code, interval_km=D(km) if km is not None else None, interval_days=days,
        interval_hours=D(hours) if hours is not None else None, rank=rank, tolerance_pct=D(tol), lead_days=lead,
        asset_types=list(types), is_active=True, work_type_id=None,
    )


def baseline(a, i, *, km=0, hours=None, done_at=None, source="manual"):
    return SimpleNamespace(
        asset_id=a.id, interval_id=i.id, km=D(km), hours=D(hours) if hours is not None else None,
        done_at=done_at, source=source,
    )


def context(a, *, per_day=54, days=30, baselines=(), open_plans=(), closed=None, trusted=(), behaviors=None,
            hours_current=None, hours_per_day=None, stale_assets=()):
    km_deltas = {a.id: [D(per_day)] * days} if days else {}
    hours_deltas = {a.id: [D(hours_per_day)] * days} if hours_per_day is not None else {}
    book = mo.PaceBook(day=TODAY, built_at=0.0, km_deltas=km_deltas, hours_deltas=hours_deltas, group_km={}, group_hours={})
    return mo.Context(
        today=TODAY, now=NOW, default_pace=D(200), default_source="default", book=book,
        baselines={(b.asset_id, b.interval_id): b for b in baselines},
        open_plans={(p.asset_id, p.interval_id): p for p in open_plans},
        closed_triggers=closed or {},
        last_data_at={} if a.id not in stale_assets else {a.id: NOW - timedelta(hours=72)},
        hours_current={a.id: D(hours_current)} if hours_current is not None else {},
        trusted_wagons=set(trusted), assets_in_shop=set(), sensor_failure=set(),
        behavior_of_status=behaviors or {"operational": "operational", "repair": "repair", "out": "out_of_service"},
    )


def plan(a, i, *, status="scheduled", trigger=5000, manual=False, deferrals=0, scheduled=TODAY):
    return SimpleNamespace(
        id=uuid4(), asset_id=a.id, interval_id=i.id, status=status, trigger_mileage=D(trigger) if trigger is not None else None,
        scheduled_date=scheduled, scheduled_date_manual=manual, recommended_date=None, deferral_count=deferrals,
        updated_at=None,
    )


def test_a_locomotive_close_to_its_limit_gets_an_obligation_with_markers_and_a_low_confidence_baseline():
    a, i = asset(mileage=4650), interval()
    [ob] = mo.evaluate_asset(a, [i], context(a))
    assert ob.due_km == D(5000) and ob.baseline_km == D(0)
    assert ob.baseline_source == "provisional" and ob.confidence == "low"  # the grid baseline is a guess
    assert ob.markers.state == "due_soon"
    assert ob.markers.date_p75 == TODAY + timedelta(days=7)  # 350 km at 54 km/day
    assert ob.priority.score > 0 and ob.priority.why


def test_a_real_baseline_counts_from_the_last_service_not_from_the_grid():
    a, i = asset(mileage=7000), interval()
    [ob] = mo.evaluate_asset(a, [i], context(a, baselines=[baseline(a, i, km=6500, source="completed")]))
    assert ob.baseline_km == D(6500) and ob.due_km == D(11500)
    assert ob.markers.used == D(500) and ob.markers.state == "forecast"
    assert ob.confidence == "high"


def test_a_baseline_before_tracking_began_may_be_negative():
    a, i = asset(mileage=1200), interval()
    [ob] = mo.evaluate_asset(a, [i], context(a, baselines=[baseline(a, i, km=-3000, source="import")]))
    assert ob.markers.used == D(4200) and ob.due_km == D(2000)


def test_an_open_plan_keeps_its_own_cycle_even_after_the_limit_is_passed():
    a, i = asset(mileage=5100), interval()
    p = plan(a, i, trigger=5000)
    [ob] = mo.evaluate_asset(a, [i], context(a, open_plans=[p]))
    assert ob.plan is p and ob.due_km == D(5000)
    assert ob.markers.state == "over_limit"  # the obligation is not lost, it is overdue


def test_a_closed_cycle_is_not_planned_again():
    a, i = asset(mileage=5100), interval()
    [ob] = mo.evaluate_asset(a, [i], context(a, closed={(a.id, i.id): D(10000)}))
    assert ob.baseline_km == D(10000)  # the 10 000 cycle is closed: the next one starts from there


def test_wagon_km_obligations_exist_only_for_confirmed_mileage():
    a, i = asset(mileage=4650, asset_type="wagon"), interval()
    assert mo.evaluate_asset(a, [i], context(a)) == []
    assert len(mo.evaluate_asset(a, [i], context(a, trusted=[a.id]))) == 1


def test_withdrawn_assets_have_no_obligations_and_assets_in_the_shop_are_paused():
    out = asset(status="out")
    assert mo.evaluate_asset(out, [interval()], context(out)) == []
    gone = asset(decommissioned=date(2026, 1, 1))
    assert mo.evaluate_asset(gone, [interval()], context(gone)) == []
    in_shop = asset(status="repair")
    [ob] = mo.evaluate_asset(in_shop, [interval()], context(in_shop))
    assert ob.paused and ob.markers.date_p75 is None  # a stopped unit does not run the clock


def test_moto_hours_can_be_the_limiting_meter():
    a = asset(mileage=100)
    i = interval(km=50000, hours=500, rank=1)
    b = baseline(a, i, km=0, hours=0, source="completed")
    [ob] = mo.evaluate_asset(a, [i], context(a, baselines=[b], hours_current=470, hours_per_day=6, per_day=10))
    assert ob.markers.limiting == "hours"
    assert ob.markers.date_p75 == TODAY + timedelta(days=5)  # 30 h left at 6 h/day


def test_calendar_interval_needs_a_real_baseline_date():
    a = asset()
    i = interval(km=None, days=90, rank=None)
    assert mo.evaluate_asset(a, [i], context(a)) == []
    b = baseline(a, i, done_at=TODAY - timedelta(days=80), source="manual")
    [ob] = mo.evaluate_asset(a, [i], context(a, baselines=[b]))
    assert ob.markers.limiting == "days" and ob.markers.date_p75 == TODAY + timedelta(days=10)


def test_stale_data_lowers_confidence():
    a, i = asset(), interval()
    [ob] = mo.evaluate_asset(a, [i], context(a, baselines=[baseline(a, i, km=0, source="completed")], stale_assets={a.id}))
    assert ob.confidence == "stale"


def test_a_lower_rank_due_just_before_a_higher_one_is_merged_into_one_visit():
    a = asset(mileage=14700)
    low = interval(code="ТО-1", km=5000, rank=1)
    high = interval(code="ТО-2", km=15000, rank=2)
    obs = {ob.interval.code: ob for ob in mo.evaluate_asset(a, [low, high], context(a, baselines=[
        baseline(a, low, km=9850, source="completed"), baseline(a, high, km=0, source="completed")]))}
    assert obs["ТО-1"].merged_into == high.id
    assert obs["ТО-1"].planned_date == obs["ТО-2"].planned_date


@pytest.mark.asyncio
async def test_persist_creates_a_plan_only_when_the_window_is_open():
    a, i = asset(mileage=4650), interval()
    [ob] = mo.evaluate_asset(a, [i], context(a))
    created_plan = SimpleNamespace(status="scheduled")
    upsert = AsyncMock(return_value=(created_plan, True))
    db = Mock(flush=AsyncMock())
    with patch.object(mo.repository, "upsert_scheduled_plan_with_created", new=upsert):
        assert await mo.persist_obligations(db, [ob], TODAY) == 1
    assert upsert.await_args.kwargs["trigger_mileage"] == D(5000)
    assert upsert.await_args.kwargs["scheduled_date"] == ob.planned_date

    far_asset = asset(mileage=1000)
    [far] = mo.evaluate_asset(far_asset, [i], context(far_asset))
    upsert.reset_mock()
    with patch.object(mo.repository, "upsert_scheduled_plan_with_created", new=upsert):
        assert await mo.persist_obligations(db, [far], TODAY) == 0
    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_moves_a_scheduled_plan_with_the_forecast_but_not_a_pinned_date():
    a, i = asset(mileage=4650), interval()
    free = plan(a, i, scheduled=TODAY + timedelta(days=30))
    [ob] = mo.evaluate_asset(a, [i], context(a, open_plans=[free]))
    db = Mock(flush=AsyncMock())
    await mo.persist_obligations(db, [ob], TODAY)
    assert free.scheduled_date == ob.planned_date

    pinned_date = TODAY + timedelta(days=30)
    pinned = plan(a, i, manual=True, scheduled=pinned_date)
    [ob] = mo.evaluate_asset(a, [i], context(a, open_plans=[pinned]))
    await mo.persist_obligations(db, [ob], TODAY)
    assert pinned.scheduled_date == pinned_date and pinned.recommended_date == ob.planned_date


@pytest.mark.asyncio
async def test_persist_leaves_running_and_blocked_plans_alone():
    a, i = asset(mileage=4650), interval()
    for status in ("in_progress", "blocked"):
        p = plan(a, i, status=status, scheduled=TODAY - timedelta(days=9))
        [ob] = mo.evaluate_asset(a, [i], context(a, open_plans=[p]))
        await mo.persist_obligations(Mock(flush=AsyncMock()), [ob], TODAY)
        assert p.scheduled_date == TODAY - timedelta(days=9)


@pytest.mark.asyncio
async def test_a_voided_twin_of_a_due_cycle_comes_back_instead_of_being_lost():
    a, i = asset(mileage=9700), interval()
    [ob] = mo.evaluate_asset(a, [i], context(a))
    twin = SimpleNamespace(status="cancelled", scheduled_date=None, updated_at=None)
    upsert = AsyncMock(return_value=(twin, False))
    with patch.object(mo.repository, "upsert_scheduled_plan_with_created", new=upsert):
        assert await mo.persist_obligations(Mock(flush=AsyncMock()), [ob], TODAY) == 1
    assert twin.status == "scheduled" and twin.scheduled_date is not None
