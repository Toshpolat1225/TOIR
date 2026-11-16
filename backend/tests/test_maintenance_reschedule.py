"""Manual rescheduling rules of a maintenance plan (no database needed)."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services import maintenance

TODAY = date.today()


def _plan(**over):
    base = dict(
        status="scheduled", scheduled_date=TODAY + timedelta(days=2), scheduled_date_manual=False,
        recommended_date=None, reschedule_reason=None, trigger_mileage=Decimal("5000"),
        asset_id="asset", interval_id="interval", deferral_count=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


async def _apply(plan, **values):
    await maintenance._apply_reschedule(AsyncMock(), plan, dict(values))


@pytest.mark.asyncio
async def test_moving_keeps_the_original_recommendation_and_the_reason():
    plan = _plan()
    target = TODAY + timedelta(days=6)
    await _apply(plan, scheduled_date=target, reschedule_reason="  нет свободного бокса  ")
    assert plan.scheduled_date == target
    assert plan.scheduled_date_manual is True
    assert plan.recommended_date == TODAY + timedelta(days=2)
    assert plan.reschedule_reason == "нет свободного бокса"


@pytest.mark.asyncio
async def test_a_second_move_does_not_replace_the_recommendation_with_the_first_manual_date():
    plan = _plan(scheduled_date=TODAY + timedelta(days=6), scheduled_date_manual=True,
                 recommended_date=TODAY + timedelta(days=2), reschedule_reason="первый перенос")
    await _apply(plan, scheduled_date=TODAY + timedelta(days=9))
    assert plan.recommended_date == TODAY + timedelta(days=2)
    assert plan.reschedule_reason is None  # a new move starts with a clean reason


@pytest.mark.asyncio
@pytest.mark.parametrize("delta", [-1, maintenance.MAX_RESCHEDULE_DAYS + 1])
async def test_past_and_too_distant_dates_are_rejected(delta):
    with pytest.raises(HTTPException) as raised:
        await _apply(_plan(), scheduled_date=TODAY + timedelta(days=delta))
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_today_and_the_far_boundary_are_allowed():
    for delta in (0, maintenance.MAX_RESCHEDULE_DAYS):
        plan = _plan()
        await _apply(plan, scheduled_date=TODAY + timedelta(days=delta))
        assert plan.scheduled_date == TODAY + timedelta(days=delta)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["in_progress", "completed", "cancelled"])
async def test_only_scheduled_plans_can_be_moved(status):
    with pytest.raises(HTTPException) as raised:
        await _apply(_plan(status=status), scheduled_date=TODAY + timedelta(days=3))
    assert raised.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        {"scheduled_date": TODAY + timedelta(days=3), "status": "in_progress"},
        {"scheduled_date": TODAY + timedelta(days=3), "completed_date": TODAY},
        {"scheduled_date": TODAY + timedelta(days=3), "reset_schedule": True},
        {"scheduled_date": None},
        {"reschedule_reason": "причина без даты"},
    ],
)
async def test_invalid_combinations_are_422(values):
    with pytest.raises(HTTPException) as raised:
        await _apply(_plan(), **values)
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_plain_updates_pass_through_untouched():
    plan = _plan()
    values = {"status": "in_progress"}
    await maintenance._apply_reschedule(AsyncMock(), plan, values)
    assert values == {"status": "in_progress"} and plan.scheduled_date_manual is False


@pytest.mark.asyncio
async def test_reset_returns_to_the_recommendation_and_clears_the_manual_state():
    plan = _plan(scheduled_date=TODAY + timedelta(days=9), scheduled_date_manual=True,
                 recommended_date=TODAY + timedelta(days=2), reschedule_reason="x")
    with patch.object(maintenance, "_recommended_date_now", new=AsyncMock(return_value=TODAY + timedelta(days=4))):
        await _apply(plan, reset_schedule=True)
    assert plan.scheduled_date == TODAY + timedelta(days=4)
    assert (plan.scheduled_date_manual, plan.recommended_date, plan.reschedule_reason) == (False, None, None)


@pytest.mark.asyncio
async def test_reset_without_a_fresh_estimate_falls_back_to_the_stored_recommendation():
    plan = _plan(scheduled_date=TODAY + timedelta(days=9), scheduled_date_manual=True,
                 recommended_date=TODAY + timedelta(days=2))
    with patch.object(maintenance, "_recommended_date_now", new=AsyncMock(return_value=None)):
        await _apply(plan, reset_schedule=True)
    assert plan.scheduled_date == TODAY + timedelta(days=2)


@pytest.mark.asyncio
async def test_reset_of_an_automatic_plan_is_a_conflict():
    with pytest.raises(HTTPException) as raised:
        await _apply(_plan(), reset_schedule=True)
    assert raised.value.status_code == 409
