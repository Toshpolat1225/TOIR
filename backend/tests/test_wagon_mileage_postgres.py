import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrain, GtkTrainMember
from app.models.mileage import (
    MileageCalculationInput,
    MileageCalculationRun,
    WagonMileageLedger,
    WagonMileageOpeningBalance,
    WialonOdometerReading,
)
from app.models.identity import User
from app.services.wagon_mileage_run import run_wagon_mileage


@pytest.mark.pg
@pytest.mark.asyncio
async def test_parallel_runs_create_one_idempotent_ledger_set():
    train_id = 900_000_000 + (uuid4().int % 90_000_000)
    wagon_gtk_id = train_id + 1
    locomotive_gtk_id = train_id + 2
    wagon_asset_id = uuid4()
    locomotive_asset_id = uuid4()
    submitter_id = uuid4()
    approver_id = uuid4()
    source_unit_id = str(800_000_000 + (uuid4().int % 100_000_000))
    start = datetime.now(timezone.utc) - timedelta(minutes=2)
    end = start + timedelta(minutes=2)

    async with SessionFactory() as db:
        db.add_all(
            [
                FixedAsset(
                    id=wagon_asset_id,
                    inv_number=f"pg-wagon-{uuid4()}",
                    asset_type="wagon",
                    status="operational",
                    mileage=Decimal("1000"),
                ),
                FixedAsset(
                    id=locomotive_asset_id,
                    inv_number=f"pg-loco-{uuid4()}",
                    asset_type="locomotive",
                    status="operational",
                ),
                User(
                    id=submitter_id,
                    email=f"pg-submitter-{uuid4()}@example.test",
                    full_name="PG test submitter",
                    hashed_password="not-a-real-password-hash",
                    role="admin",
                ),
                User(
                    id=approver_id,
                    email=f"pg-approver-{uuid4()}@example.test",
                    full_name="PG test approver",
                    hashed_password="not-a-real-password-hash",
                    role="admin",
                ),
            ]
        )
        await db.commit()
        db.add(GtkTrain(gtk_id=train_id, is_open=False))
        await db.commit()
        db.add_all(
            [
                WagonMileageOpeningBalance(
                    asset_id=wagon_asset_id,
                    mileage_km=Decimal("1000"),
                    effective_at=start - timedelta(minutes=1),
                    created_by=submitter_id,
                    approved_by=approver_id,
                    approved_at=start - timedelta(minutes=1),
                    status="approved",
                ),
                AssetSourceLink(
                    asset_id=wagon_asset_id,
                    source="gtk",
                    external_id=str(wagon_gtk_id),
                    link_method="manual",
                ),
                AssetSourceLink(
                    asset_id=locomotive_asset_id,
                    source="gtk",
                    external_id=str(locomotive_gtk_id),
                    link_method="manual",
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="carriage",
                    object_gtk_id=wagon_gtk_id,
                    is_main=False,
                    ord=1,
                    observed_from=start,
                    observed_to=end,
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="locomotive",
                    object_gtk_id=locomotive_gtk_id,
                    is_main=True,
                    ord=1,
                    observed_from=start,
                    observed_to=end,
                ),
                WialonOdometerReading(
                    asset_id=locomotive_asset_id,
                    source_unit_id=source_unit_id,
                    odometer_km=Decimal("100"),
                    reading_at=start,
                    observed_at=start,
                    received_at=start,
                    accepted=True,
                    calculation_eligible=True,
                    classification="CONFIRMED",
                    payload_hash=str(uuid4()).replace("-", "") * 2,
                    payload={},
                ),
                WialonOdometerReading(
                    asset_id=locomotive_asset_id,
                    source_unit_id=source_unit_id,
                    odometer_km=Decimal("120"),
                    reading_at=end,
                    observed_at=end,
                    received_at=end,
                    accepted=True,
                    calculation_eligible=True,
                    classification="CONFIRMED",
                    payload_hash=str(uuid4()).replace("-", "") * 2,
                    payload={},
                ),
            ]
        )
        await db.commit()

    run_ids = []
    try:
        results = await asyncio.gather(
            _run_once(),
            _run_once(),
        )
        run_ids = [result["run_id"] for result in results]
        async with SessionFactory() as db:
            ledger_count = await db.scalar(
                select(func.count()).select_from(WagonMileageLedger).where(
                    WagonMileageLedger.wagon_asset_id == wagon_asset_id
                )
            )
            active_count = await db.scalar(
                select(func.count()).select_from(WagonMileageLedger).where(
                    WagonMileageLedger.wagon_asset_id == wagon_asset_id,
                    WagonMileageLedger.status == "active",
                )
            )
            ledger = await db.scalar(
                select(WagonMileageLedger).where(
                    WagonMileageLedger.wagon_asset_id == wagon_asset_id,
                    WagonMileageLedger.status == "active",
                )
            )
            projected_mileage = await db.scalar(
                select(FixedAsset.mileage).where(FixedAsset.id == wagon_asset_id)
            )
        assert ledger_count == 1
        assert active_count == 1
        assert ledger is not None
        assert ledger.distance_km == Decimal("20.00")
        assert ledger.classification == "ESTIMATED"
        assert ledger.calculation_eligible is True
        assert projected_mileage == Decimal("1020.00")
    finally:
        async with SessionFactory() as db:
            await db.execute(
                delete(MileageCalculationInput).where(
                    MileageCalculationInput.run_id.in_(run_ids)
                )
            )
            await db.execute(
                delete(WagonMileageLedger).where(
                    WagonMileageLedger.wagon_asset_id == wagon_asset_id
                )
            )
            await db.execute(
                delete(MileageCalculationRun).where(
                    MileageCalculationRun.id.in_(run_ids)
                )
            )
            await db.execute(
                delete(WialonOdometerReading).where(
                    WialonOdometerReading.asset_id == locomotive_asset_id
                )
            )
            await db.execute(
                delete(WagonMileageOpeningBalance).where(
                    WagonMileageOpeningBalance.asset_id == wagon_asset_id
                )
            )
            await db.execute(
                delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id == train_id)
            )
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == train_id))
            await db.execute(
                delete(AssetSourceLink).where(
                    AssetSourceLink.asset_id.in_(
                        [wagon_asset_id, locomotive_asset_id]
                    )
                )
            )
            await db.execute(
                delete(FixedAsset).where(
                    FixedAsset.id.in_([wagon_asset_id, locomotive_asset_id])
                )
            )
            await db.execute(delete(User).where(User.id.in_([submitter_id, approver_id])))
            await db.commit()


async def _run_once():
    async with SessionFactory() as db:
        return await run_wagon_mileage(db)
