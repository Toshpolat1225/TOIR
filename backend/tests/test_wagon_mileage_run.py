from decimal import Decimal

import pytest

from app.services.wagon_mileage_run import (
    calculate_wagon_projection,
    ledger_idempotency_key,
)


def test_ledger_idempotency_key_is_stable_and_tracks_input_changes():
    base = {
        "wagon_asset_id": "wagon",
        "aggregate_id": "train",
        "period_from": "2026-11-01T00:00:00+00:00",
        "period_to": "2026-11-01T01:00:00+00:00",
        "algorithm_version": "v1",
        "input_hash": "same",
    }

    assert ledger_idempotency_key(**base) == ledger_idempotency_key(**base)
    assert ledger_idempotency_key(**(base | {"input_hash": "changed"})) != (
        ledger_idempotency_key(**base)
    )


def test_wagon_projection_adds_confirmed_and_estimated_km():
    assert calculate_wagon_projection(
        "wagon",
        Decimal("1000"),
        Decimal("10"),
        Decimal("2.5"),
    ) == Decimal("1012.5")


def test_wagon_projection_rejects_locomotive_and_diesel_assets():
    for asset_type in ("locomotive", "diesel"):
        with pytest.raises(ValueError, match="only for wagons"):
            calculate_wagon_projection(
                asset_type,
                Decimal("1000"),
                Decimal("10"),
                Decimal("2"),
            )
