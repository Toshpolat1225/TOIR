from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.models.mileage import WialonRawReceipt
from app.services import wialon_ingestion


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
