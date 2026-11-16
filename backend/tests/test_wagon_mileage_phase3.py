import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services import gtk as gtk_service
from app.services.wagon_mileage import OdometerPoint, sum_wialon_sample_deltas

T0 = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)


def _point(reading_id: int, at: datetime, km: str, loco) -> OdometerPoint:
    return OdometerPoint(
        reading_id=reading_id,
        locomotive_asset_id=loco,
        odometer_km=Decimal(km),
        reading_at=at,
        accepted=True,
        calculation_eligible=True,
        received_at=at,
    )


def test_three_hour_equal_odometer_is_confirmed_zero_km():
    loco = uuid4()
    decision = sum_wialon_sample_deltas(
        [_point(1, T0, "100", loco), _point(2, T0 + timedelta(hours=3), "100", loco)],
        period_from=T0,
        period_to=T0 + timedelta(hours=3),
    )
    assert decision.classification == "CONFIRMED"
    assert decision.km == Decimal("0.00")


def test_forty_km_locomotive_hour_gives_twenty_km_for_half_hour_wagon():
    loco = uuid4()
    points = [
        _point(i, T0 + timedelta(minutes=2 * i), str(100 + Decimal(40) * 2 * i / 60), loco)
        for i in range(31)
    ]
    decision = sum_wialon_sample_deltas(
        points, period_from=T0, period_to=T0 + timedelta(minutes=30)
    )
    assert decision.classification in {"CONFIRMED", "ESTIMATED"}
    assert decision.km == Decimal("20.00")


async def _one_periodic_iteration(flag: bool):
    class Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        raise asyncio.CancelledError

    with (
        patch.object(
            gtk_service,
            "settings",
            SimpleNamespace(
                gtk_pull_enabled=True,
                wagon_mileage_engine_enabled=flag,
                gtk_sync_interval_minutes=5,
            ),
        ),
        patch.object(gtk_service, "auto_sync_stopped", return_value=False),
        patch.object(gtk_service, "SessionFactory", return_value=Ctx()),
        patch.object(gtk_service, "sync_gtk", new=AsyncMock()) as sync,
        patch.object(gtk_service, "run_wagon_mileage", new=AsyncMock()) as run,
        patch.object(gtk_service.asyncio, "sleep", new=fake_sleep),
    ):
        with pytest.raises(asyncio.CancelledError):
            await gtk_service.run_periodic_gtk_sync()
    return sync, run


@pytest.mark.asyncio
async def test_periodic_sync_does_not_run_engine_when_flag_is_false():
    sync, run = await _one_periodic_iteration(False)
    sync.assert_awaited_once()
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_periodic_sync_runs_engine_when_flag_is_true():
    sync, run = await _one_periodic_iteration(True)
    sync.assert_awaited_once()
    run.assert_awaited_once()


def test_zero_km_over_partial_sample_overlap_is_confirmed_not_estimated():
    loco = uuid4()
    decision = sum_wialon_sample_deltas(
        [_point(1, T0, "100", loco), _point(2, T0 + timedelta(minutes=2), "100", loco)],
        period_from=T0 + timedelta(seconds=30),
        period_to=T0 + timedelta(seconds=90),
    )
    assert decision.classification == "CONFIRMED"
    assert decision.km == Decimal("0.00")


def test_moving_partial_overlap_stays_estimated():
    loco = uuid4()
    decision = sum_wialon_sample_deltas(
        [_point(1, T0, "100", loco), _point(2, T0 + timedelta(minutes=2), "104", loco)],
        period_from=T0 + timedelta(seconds=30),
        period_to=T0 + timedelta(seconds=90),
    )
    assert decision.classification == "ESTIMATED"
    assert decision.km == Decimal("2.00")


def test_single_locomotive_with_blocked_readings_reports_specific_reason():
    from types import SimpleNamespace

    from app.services import wagon_mileage_run as run_module

    loco = uuid4()
    blocked = OdometerPoint(
        reading_id=1,
        locomotive_asset_id=loco,
        odometer_km=Decimal("100"),
        reading_at=T0,
        accepted=True,
        calculation_eligible=False,
        received_at=T0,
    )
    blocked_2 = OdometerPoint(
        reading_id=2,
        locomotive_asset_id=loco,
        odometer_km=Decimal("101"),
        reading_at=T0 + timedelta(minutes=2),
        accepted=True,
        calculation_eligible=False,
        received_at=T0 + timedelta(minutes=2),
    )
    member = SimpleNamespace(
        observed_from=T0, observed_to=T0 + timedelta(minutes=2), is_main=True
    )
    decision, _ = run_module._candidate_decisions(
        start=T0,
        end=T0 + timedelta(minutes=2),
        train_id=1,
        locomotive_rows=[(member, None, None, loco)],
        by_locomotive={loco: [blocked, blocked_2]},
    )
    assert decision.classification == "HELD"
    assert decision.reason == "reading_not_calculation_eligible"
