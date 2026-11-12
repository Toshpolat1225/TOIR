from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.models.mileage import WialonRawReceipt
from app.routers import wialon as wialon_router
from app.services import wialon_ingestion
from app.services.wialon_quality import CounterState


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _Scalars(self._rows)


@pytest.mark.asyncio
async def test_unmapped_measurement_is_accepted_raw_but_held_for_calculation():
    reading = SimpleNamespace(id=12, odometer_km=Decimal("100"))
    calls = 0

    async def execute(_statement):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Result()
        if calls == 2:
            return _Result()
        if calls == 3:
            return _Result(reading)
        return _Result(rows=[reading])

    db = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(side_effect=execute),
        flush=AsyncMock(),
    )
    with patch.object(
        wialon_ingestion.counters_repository,
        "get_asset_by_wialon_id",
        new=AsyncMock(return_value=None),
    ):
        result = await wialon_ingestion.ingest_wialon_reading(
            db,
            unit_id="unit-7",
            odometer_km=Decimal("100"),
            reading_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
            transport="push",
            source_time_verified=False,
        )

    assert result.accepted is True
    assert result.calculation_eligible is False
    assert result.classification == "HELD"
    assert result.reason == "unmapped_unit"
    assert result.reading_id == 12
    receipt = db.add.call_args.args[0]
    assert isinstance(receipt, WialonRawReceipt)
    assert receipt.asset_id is None
    assert "token" not in receipt.payload


@pytest.mark.asyncio
async def test_same_time_different_odometer_holds_both_readings():
    old_reading = SimpleNamespace(
        id=20,
        odometer_km=Decimal("100"),
        calculation_eligible=True,
        classification="CONFIRMED",
        rejection_reason=None,
    )
    new_reading = SimpleNamespace(
        id=21,
        odometer_km=Decimal("110"),
        calculation_eligible=False,
        classification="HELD",
        rejection_reason=None,
    )
    calls = 0

    async def execute(_statement):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Result()
        if calls == 2:
            return _Result()
        if calls == 3:
            return _Result(new_reading)
        return _Result(rows=[old_reading, new_reading])

    db = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(side_effect=execute),
        flush=AsyncMock(),
    )
    with patch.object(
        wialon_ingestion.counters_repository,
        "get_asset_by_wialon_id",
        new=AsyncMock(return_value=None),
    ):
        result = await wialon_ingestion.ingest_wialon_reading(
            db,
            unit_id="unit-7",
            odometer_km=Decimal("110"),
            reading_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
            transport="pull",
        )

    assert result.classification == "HELD"
    assert result.reason == "same_time_different_odometer"
    assert old_reading.calculation_eligible is False
    assert new_reading.calculation_eligible is False
    assert old_reading.rejection_reason == "same_time_different_odometer"
    assert new_reading.rejection_reason == "same_time_different_odometer"


@pytest.mark.asyncio
async def test_mapped_conflict_does_not_advance_counter_state():
    observed_at = datetime(2026, 11, 10, tzinfo=timezone.utc)
    old_reading = SimpleNamespace(
        id=22,
        odometer_km=Decimal("100"),
        calculation_eligible=True,
        classification="CONFIRMED",
        rejection_reason=None,
    )
    new_reading = SimpleNamespace(
        id=23,
        odometer_km=Decimal("110"),
        calculation_eligible=False,
        classification="HELD",
        rejection_reason=None,
    )
    state = SimpleNamespace(last_status="accepted", last_reason=None)
    calls = 0

    async def execute(_statement):
        nonlocal calls
        calls += 1
        if calls < 4:
            return _Result(new_reading if calls == 3 else None)
        return _Result(rows=[old_reading, new_reading])

    db = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(side_effect=execute),
        flush=AsyncMock(),
    )
    asset = SimpleNamespace(id="asset-1")
    with (
        patch.object(
            wialon_ingestion.counters_repository,
            "get_asset_by_wialon_id",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            wialon_ingestion.counters_repository,
            "get_state_row",
            new=AsyncMock(return_value=state),
        ),
        patch.object(
            wialon_ingestion.counters_repository,
            "mark_conflict",
            new=AsyncMock(),
        ),
        patch.object(
            wialon_ingestion.counters_repository,
            "save_decision",
            new=AsyncMock(),
        ) as save_decision,
    ):
        result = await wialon_ingestion.ingest_wialon_reading(
            db,
            unit_id="wialon-42",
            odometer_km=Decimal("110"),
            reading_at=observed_at,
            received_at=observed_at,
            transport="pull",
            source_time_verified=True,
        )

    assert result.calculation_eligible is False
    assert result.reason == "same_time_different_odometer"
    assert state.last_reason == "same_time_different_odometer"
    save_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_counter_state_conflict_blocks_later_readings_until_rebaseline():
    observed_at = datetime(2026, 11, 10, 0, 2, tzinfo=timezone.utc)
    reading = SimpleNamespace(
        id=24,
        odometer_km=Decimal("120"),
        calculation_eligible=False,
        classification="HELD",
        rejection_reason=None,
    )
    state = SimpleNamespace(last_reason="same_time_different_odometer")
    calls = 0

    async def execute(_statement):
        nonlocal calls
        calls += 1
        if calls == 3:
            return _Result(reading)
        return _Result(rows=[reading])

    db = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(side_effect=execute),
        flush=AsyncMock(),
    )
    with (
        patch.object(
            wialon_ingestion.counters_repository,
            "get_asset_by_wialon_id",
            new=AsyncMock(return_value=SimpleNamespace(id="asset-1")),
        ),
        patch.object(
            wialon_ingestion.counters_repository,
            "get_state_row",
            new=AsyncMock(return_value=state),
        ),
        patch.object(
            wialon_ingestion.counters_repository,
            "save_decision",
            new=AsyncMock(),
        ) as save_decision,
    ):
        result = await wialon_ingestion.ingest_wialon_reading(
            db,
            unit_id="wialon-42",
            odometer_km=Decimal("120"),
            reading_at=observed_at,
            received_at=observed_at,
            transport="pull",
            source_time_verified=True,
        )

    assert result.accepted is True
    assert result.calculation_eligible is False
    assert result.reason == "counter_state_blocked_by_unresolved_conflict"
    save_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_quality_gate_rejects_hilux_odometer_jump_for_calculation():
    observed_at = datetime(2026, 11, 11, 12, 1, tzinfo=timezone.utc)
    reading = SimpleNamespace(
        id=30,
        odometer_km=Decimal("1000000000"),
        calculation_eligible=False,
        classification="HELD",
        rejection_reason="cnm sakradi",
    )
    calls = 0

    async def execute(_statement):
        nonlocal calls
        calls += 1
        if calls < 4:
            return _Result(reading if calls == 3 else None)
        return _Result(rows=[reading])

    db = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(side_effect=execute),
        flush=AsyncMock(),
    )
    asset = SimpleNamespace(id="asset-1")
    state = CounterState(
        baseline_cnm=Decimal("100"),
        last_cnm=Decimal("100"),
        last_cnm_at=observed_at - timedelta(minutes=1),
    )
    with (
        patch.object(
            wialon_ingestion.counters_repository,
            "get_asset_by_wialon_id",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            wialon_ingestion.counters_repository,
            "get_state_row",
            new=AsyncMock(return_value=state),
        ),
        patch.object(
            wialon_ingestion.counters_repository,
            "save_decision",
            new=AsyncMock(),
        ),
    ):
        result = await wialon_ingestion.ingest_wialon_reading(
            db,
            unit_id="wialon-42",
            odometer_km=Decimal("1000000000"),
            reading_at=observed_at,
            received_at=observed_at,
            transport="pull",
            source_time_verified=True,
        )

    assert result.accepted is True
    assert result.calculation_eligible is False
    assert result.classification == "HELD"
    assert result.mileage_verdict == "rejected"
    assert "sakradi" in result.reason
    assert reading.calculation_eligible is False


def test_push_and_pull_share_the_same_measurement_identity():
    observed_at = datetime(2026, 11, 11, tzinfo=timezone.utc)
    push = wialon_ingestion._measurement_key(
        unit_id="wialon-42",
        reading_at=observed_at,
        odometer_km=Decimal("100"),
        payload_hash="push-hash",
    )
    pull = wialon_ingestion._measurement_key(
        unit_id="wialon-42",
        reading_at=observed_at,
        odometer_km=Decimal("100"),
        payload_hash="pull-hash",
    )
    assert push == pull


@pytest.mark.asyncio
async def test_push_absolute_odometer_does_not_change_fixed_asset_mileage():
    from starlette.requests import Request

    asset = SimpleNamespace(
        id="asset-1",
        name="Locomotive",
        mileage=Decimal("1250"),
        wialon_last_sync=None,
        updated_at=None,
        wialon_speed=None,
        wialon_online=False,
    )
    body = (
        b'{"unit_id":"unit-1","mileage":"1000000000",'
        b'"reading_at":"2026-11-11T00:00:00Z"}'
    )

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/wialon/input",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        },
        receive=receive,
    )
    request.state.wialon_query_size = len(body)
    db = object()

    with (
        patch.object(
            wialon_router.wialon_ingestion,
            "ingest_wialon_reading",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    accepted=True,
                    calculation_eligible=False,
                    classification="HELD",
                )
            ),
        ) as ingest,
        patch.object(
            wialon_router.service,
            "find_wialon_asset",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            wialon_router.service, "_commit", new=AsyncMock()
        ) as commit,
    ):
        result = await wialon_router.post_wialon_input(request, db)

    assert ingest.await_args.kwargs["odometer_km"] == Decimal("1000000000")
    assert ingest.await_args.kwargs["transport"] == "push"
    assert ingest.await_args.kwargs["source_time_verified"] is False
    assert asset.mileage == Decimal("1250")
    assert result["found"] is True
    commit.assert_awaited_once()
