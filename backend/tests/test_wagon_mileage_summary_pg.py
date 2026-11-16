"""summarize_active_ledger must work on real PostgreSQL (GROUP BY on a JSON expression)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrain
from app.models.mileage import MileageCalculationRun, WagonMileageLedger
from app.repositories import mileage as mileage_repository

T0 = datetime(2026, 11, 14, tzinfo=timezone.utc)
TRAIN_ID = 910_000_000 + (uuid4().int % 80_000_000)


def _row(run_id, wagon_id, index, classification, km, reason=None, status="active"):
    return WagonMileageLedger(
        run_id=run_id,
        wagon_asset_id=wagon_id,
        train_gtk_id=TRAIN_ID,
        period_from=T0 + timedelta(hours=index),
        period_to=T0 + timedelta(hours=index, minutes=30),
        distance_km=Decimal(km),
        estimated=classification == "ESTIMATED",
        status=status,
        idempotency_key=uuid4().hex,
        classification=classification,
        calculation_eligible=classification != "HELD",
        algorithm_version="test",
        input_hash=uuid4().hex + uuid4().hex,
        calculation_details={"reason": reason} if reason else {},
    )


@pytest.mark.pg
@pytest.mark.asyncio
async def test_summary_groups_held_reasons_and_sums_km_by_class():
    wagon_id, run_id = uuid4(), uuid4()
    async with SessionFactory() as db:
        db.add(FixedAsset(id=wagon_id, inv_number=f"SUM-{uuid4().hex[:8]}", asset_type="wagon", status="operational"))
        await db.commit()
        db.add(GtkTrain(gtk_id=TRAIN_ID, is_open=False))
        db.add(MileageCalculationRun(id=run_id, status="completed", algorithm_version="test"))
        await db.commit()
        db.add_all([
            _row(run_id, wagon_id, 0, "CONFIRMED", "10"),
            _row(run_id, wagon_id, 1, "ESTIMATED", "5"),
            _row(run_id, wagon_id, 2, "HELD", "0", "odometer_sample_gap_exceeded"),
            _row(run_id, wagon_id, 3, "HELD", "0", "odometer_sample_gap_exceeded"),
            _row(run_id, wagon_id, 4, "HELD", "0", "reading_not_calculation_eligible"),
            _row(run_id, wagon_id, 5, "HELD", "0"),
            _row(run_id, wagon_id, 6, "HELD", "0", "ignored_superseded", status="superseded"),
        ])
        await db.commit()
    try:
        async with SessionFactory() as db:
            totals, reasons = await mileage_repository.summarize_active_ledger(db, wagon_id)
        assert totals == {"CONFIRMED": Decimal("10"), "ESTIMATED": Decimal("5"), "HELD": Decimal("0")}
        assert reasons == {
            "odometer_sample_gap_exceeded": 2,
            "reading_not_calculation_eligible": 1,
            "unknown": 1,
        }
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(WagonMileageLedger).where(WagonMileageLedger.wagon_asset_id == wagon_id))
            await db.execute(delete(MileageCalculationRun).where(MileageCalculationRun.id == run_id))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == TRAIN_ID))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == wagon_id))
            await db.commit()
