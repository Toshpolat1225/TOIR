"""PostgreSQL tests for the unified wagon mileage run (needs pg_rehearse)."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text

from app.core.database import SessionFactory, engine
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrain, GtkTrainMember
from app.models.identity import User
from app.models.mileage import (
    MileageCalculationInput,
    MileageCalculationRun,
    WagonIdlePeriod,
    WagonMileageLedger,
    WagonMileageOpeningBalance,
    WialonOdometerReading,
)
from app.services import wagon_mileage_run as run_module
from app.services.wagon_mileage_run import run_wagon_mileage

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


@asynccontextmanager
async def scenario(
    opening_offset_min: float, *, loco_mileage="500", open_membership=False
):
    """One wagon + one locomotive, 20 km over [start, start+2min).

    opening effective_at = start + opening_offset_min.
    """
    train_id = 900_000_000 + (uuid4().int % 90_000_000)
    wagon_gtk, loco_gtk = train_id + 1, train_id + 2
    wagon_id, loco_id = uuid4(), uuid4()
    submitter, approver = uuid4(), uuid4()
    unit = str(800_000_000 + (uuid4().int % 100_000_000))
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=2)
    end = start + timedelta(minutes=2)
    info = dict(
        wagon_id=wagon_id,
        loco_id=loco_id,
        start=start,
        end=end,
        train_id=train_id,
        run_ids=[],
    )
    async with SessionFactory() as db:
        db.add_all(
            [
                FixedAsset(
                    id=wagon_id,
                    inv_number=f"pg-w-{uuid4()}",
                    asset_type="wagon",
                    status="operational",
                    mileage=Decimal("1000"),
                ),
                FixedAsset(
                    id=loco_id,
                    inv_number=f"pg-l-{uuid4()}",
                    asset_type="locomotive",
                    status="operational",
                    mileage=Decimal(loco_mileage),
                ),
                User(
                    id=submitter,
                    email=f"s-{uuid4()}@example.test",
                    full_name="s",
                    hashed_password="x",
                    role="admin",
                ),
                User(
                    id=approver,
                    email=f"a-{uuid4()}@example.test",
                    full_name="a",
                    hashed_password="x",
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
                    asset_id=wagon_id,
                    mileage_km=Decimal("1000"),
                    effective_at=start + timedelta(minutes=opening_offset_min),
                    created_by=submitter,
                    approved_by=approver,
                    approved_at=start,
                    status="approved",
                ),
                AssetSourceLink(
                    asset_id=wagon_id,
                    source="gtk",
                    external_id=str(wagon_gtk),
                    link_method="manual",
                ),
                AssetSourceLink(
                    asset_id=loco_id,
                    source="gtk",
                    external_id=str(loco_gtk),
                    link_method="manual",
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="carriage",
                    object_gtk_id=wagon_gtk,
                    is_main=False,
                    ord=1,
                    observed_from=start,
                    observed_to=None if open_membership else end,
                ),
                GtkTrainMember(
                    train_gtk_id=train_id,
                    kind="locomotive",
                    object_gtk_id=loco_gtk,
                    is_main=True,
                    ord=1,
                    observed_from=start,
                    observed_to=None if open_membership else end,
                ),
            ]
            + [
                WialonOdometerReading(
                    asset_id=loco_id,
                    source_unit_id=unit,
                    odometer_km=Decimal(km),
                    reading_at=at,
                    observed_at=at,
                    received_at=at,
                    accepted=True,
                    calculation_eligible=True,
                    classification="CONFIRMED",
                    payload_hash=str(uuid4()).replace("-", "") * 2,
                    payload={},
                )
                for km, at in (("100", start), ("120", end))
            ]
        )
        await db.commit()
    try:
        yield info
    finally:
        async with SessionFactory() as db:
            ids = (
                await db.scalars(
                    select(MileageCalculationRun.id)
                    .join(
                        WagonMileageLedger,
                        WagonMileageLedger.run_id == MileageCalculationRun.id,
                        isouter=True,
                    )
                    .where(
                        (WagonMileageLedger.wagon_asset_id == wagon_id)
                        | MileageCalculationRun.id.in_(info["run_ids"] or [uuid4()])
                    )
                )
            ).all()
            await db.execute(
                delete(MileageCalculationInput).where(
                    MileageCalculationInput.run_id.in_(ids)
                )
            )
            await db.execute(
                delete(WagonIdlePeriod).where(WagonIdlePeriod.wagon_asset_id == wagon_id)
            )
            await db.execute(
                delete(WagonMileageLedger).where(
                    WagonMileageLedger.wagon_asset_id == wagon_id
                )
            )
            await db.execute(
                delete(MileageCalculationRun).where(MileageCalculationRun.id.in_(ids))
            )
            await db.execute(
                delete(WialonOdometerReading).where(
                    WialonOdometerReading.asset_id == loco_id
                )
            )
            await db.execute(
                delete(WagonMileageOpeningBalance).where(
                    WagonMileageOpeningBalance.asset_id == wagon_id
                )
            )
            await db.execute(
                delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id == train_id)
            )
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == train_id))
            await db.execute(
                delete(AssetSourceLink).where(
                    AssetSourceLink.asset_id.in_([wagon_id, loco_id])
                )
            )
            await db.execute(
                delete(FixedAsset).where(FixedAsset.id.in_([wagon_id, loco_id]))
            )
            await db.execute(delete(User).where(User.id.in_([submitter, approver])))
            await db.commit()


async def _rows(wagon_id):
    async with SessionFactory() as db:
        return (
            await db.scalars(
                select(WagonMileageLedger).where(
                    WagonMileageLedger.wagon_asset_id == wagon_id
                )
            )
        ).all()


async def _mileage(asset_id):
    async with SessionFactory() as db:
        return await db.scalar(select(FixedAsset.mileage).where(FixedAsset.id == asset_id))


async def _run():
    async with SessionFactory() as db:
        return await run_wagon_mileage(db)


async def test_no_backfill_period_before_effective_at_is_not_calculated_or_held():
    async with scenario(opening_offset_min=5) as s:  # effective_at after the period
        report = await _run()
        s["run_ids"].append(report["run_id"])
        assert await _rows(s["wagon_id"]) == []
        assert "period_precedes_approved_opening_balance" not in report["held_reasons"]
        assert await _mileage(s["wagon_id"]) == Decimal("1000")


async def test_period_straddling_effective_at_is_clipped_to_effective_at():
    async with scenario(opening_offset_min=1) as s:  # effective_at in the middle
        report = await _run()
        s["run_ids"].append(report["run_id"])
        rows = await _rows(s["wagon_id"])
        assert len(rows) == 1
        assert rows[0].period_from == s["start"] + timedelta(minutes=1)
        assert rows[0].distance_km == Decimal("10.00")
        assert rows[0].classification == "ESTIMATED"
        assert await _mileage(s["wagon_id"]) == Decimal("1010.00")


async def test_rerun_adds_no_rows_and_keeps_projection_and_locomotive_mileage():
    async with scenario(opening_offset_min=-1, loco_mileage="500") as s:
        first = await _run()
        s["run_ids"].append(first["run_id"])
        rows_1 = await _rows(s["wagon_id"])
        projected = await _mileage(s["wagon_id"])
        second = await _run()
        s["run_ids"].append(second["run_id"])
        rows_2 = await _rows(s["wagon_id"])
        assert [r.id for r in rows_1] == [r.id for r in rows_2]
        assert second["changed_assets"] == 0
        assert await _mileage(s["wagon_id"]) == projected == Decimal("1020.00")
        assert await _mileage(s["loco_id"]) == Decimal("500")
        assert first["locomotive_checksum_before"] == first["locomotive_checksum_after"]


async def test_invariant_failure_marks_run_failed_and_writes_no_projection():
    async with scenario(opening_offset_min=-1) as s:
        with patch.object(
            run_module,
            "_assert_ledger_invariants",
            new=AsyncMock(
                side_effect=run_module.WagonMileageInvariantError("boom invariant")
            ),
        ):
            with pytest.raises(run_module.WagonMileageInvariantError):
                await _run()
        assert await _mileage(s["wagon_id"]) == Decimal("1000")
        async with SessionFactory() as db:
            failed = (
                await db.scalars(
                    select(MileageCalculationRun)
                    .join(
                        WagonMileageLedger,
                        WagonMileageLedger.run_id == MileageCalculationRun.id,
                    )
                    .where(WagonMileageLedger.wagon_asset_id == s["wagon_id"])
                )
            ).first()
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error == "boom invariant"


async def test_unexpected_error_marks_run_failed_without_leaking_details():
    async with scenario(opening_offset_min=-1) as s:
        with patch.object(
            run_module.maintenance_service,
            "reconcile_asset_plans",
            new=AsyncMock(side_effect=RuntimeError("secret-connection-detail")),
        ):
            with pytest.raises(RuntimeError):
                await _run()
        assert await _mileage(s["wagon_id"]) == Decimal("1000")
        async with SessionFactory() as db:
            run = (
                await db.scalars(
                    select(MileageCalculationRun)
                    .join(
                        WagonMileageLedger,
                        WagonMileageLedger.run_id == MileageCalculationRun.id,
                    )
                    .where(WagonMileageLedger.wagon_asset_id == s["wagon_id"])
                )
            ).first()
        assert run.status == "failed"
        assert run.error == "RuntimeError"


async def test_second_run_is_skipped_while_run_lock_is_held():
    lock_expression = func.hashtextextended(run_module.RUN_LOCK_KEY, 0)
    async with engine.connect() as holder:
        holder = await holder.execution_options(isolation_level="AUTOCOMMIT")
        assert await holder.scalar(select(func.pg_try_advisory_lock(lock_expression)))
        try:
            async with SessionFactory() as db:
                before = await db.scalar(
                    select(func.count()).select_from(MileageCalculationRun)
                )
                report = await run_wagon_mileage(db)
                after = await db.scalar(
                    select(func.count()).select_from(MileageCalculationRun)
                )
        finally:
            await holder.scalar(select(func.pg_advisory_unlock(lock_expression)))
    assert report == {"dry_run": False, "skipped": True, "reason": "run_in_progress"}
    assert before == after


async def test_dry_run_writes_nothing_and_needs_no_lock():
    async with scenario(opening_offset_min=-1) as s:
        async with SessionFactory() as db:
            report = await run_wagon_mileage(db, dry_run=True)
        assert report["dry_run"] is True
        assert "watermark" in report
        assert await _rows(s["wagon_id"]) == []
        assert await _mileage(s["wagon_id"]) == Decimal("1000")


async def test_open_membership_growing_between_runs_is_not_double_counted():
    async with scenario(opening_offset_min=-1, open_membership=True) as s:
        first = await _run()
        s["run_ids"].append(first["run_id"])
        rows = await _rows(s["wagon_id"])
        assert [r.status for r in rows] == ["active"]
        assert rows[0].distance_km == Decimal("20.00")
        assert await _mileage(s["wagon_id"]) == Decimal("1020.00")

        # two more minutes of locomotive data arrive: 120 -> 130 km
        later = s["end"] + timedelta(minutes=2)
        async with SessionFactory() as db:
            unit = (
                await db.scalars(
                    select(WialonOdometerReading.source_unit_id).where(
                        WialonOdometerReading.asset_id == s["loco_id"]
                    )
                )
            ).first()
            db.add(
                WialonOdometerReading(
                    asset_id=s["loco_id"],
                    source_unit_id=unit,
                    odometer_km=Decimal("130"),
                    reading_at=later,
                    observed_at=later,
                    received_at=later,
                    accepted=True,
                    calculation_eligible=True,
                    classification="CONFIRMED",
                    payload_hash=str(uuid4()).replace("-", "") * 2,
                    payload={},
                )
            )
            await db.commit()
        second = await _run()
        s["run_ids"].append(second["run_id"])

        rows = await _rows(s["wagon_id"])
        active = [r for r in rows if r.status == "active"]
        assert len(active) == 1, [(r.status, r.distance_km) for r in rows]
        assert active[0].distance_km == Decimal("30.00")
        assert len([r for r in rows if r.status == "superseded"]) == 1
        # projection counts the span once: 1000 + 30, not 1000 + 20 + 30
        assert await _mileage(s["wagon_id"]) == Decimal("1030.00")

        third = await _run()
        s["run_ids"].append(third["run_id"])
        assert third["changed_assets"] == 0
        assert await _mileage(s["wagon_id"]) == Decimal("1030.00")


async def test_legacy_overlapping_active_rows_are_cleaned_up_by_the_next_run():
    async with scenario(opening_offset_min=-1, open_membership=True) as s:
        first = await _run()
        s["run_ids"].append(first["run_id"])
        # simulate the old bug: a second ACTIVE overlapping row for the same span
        async with SessionFactory() as db:
            row = (
                await db.scalars(
                    select(WagonMileageLedger).where(
                        WagonMileageLedger.wagon_asset_id == s["wagon_id"]
                    )
                )
            ).one()
            db.add(
                WagonMileageLedger(
                    run_id=row.run_id,
                    wagon_asset_id=row.wagon_asset_id,
                    locomotive_asset_id=row.locomotive_asset_id,
                    train_gtk_id=row.train_gtk_id,
                    period_from=row.period_from,
                    period_to=row.period_to - timedelta(seconds=60),
                    distance_km=Decimal("5.00"),
                    estimated=True,
                    classification="ESTIMATED",
                    calculation_eligible=True,
                    status="active",
                    idempotency_key=str(uuid4()).replace("-", "") * 2,
                    algorithm_version=row.algorithm_version,
                    input_hash="legacy",
                    calculation_details={"reason": "legacy"},
                )
            )
            await db.commit()
        second = await _run()
        s["run_ids"].append(second["run_id"])
        rows = await _rows(s["wagon_id"])
        assert len([r for r in rows if r.status == "active"]) == 1
        assert await _mileage(s["wagon_id"]) == Decimal("1020.00")


async def test_gps_track_fallback_serves_a_period_the_odometer_cannot_and_is_off_by_default():
    """The locomotive has no usable odometer readings (HELD) but a GPS track: with the flag the period is ESTIMATED from the track, with the basis recorded."""
    from app.core.config import settings
    from app.models.position_history import AssetPositionHistory

    async with scenario(-10) as s:
        async with SessionFactory() as db:
            await db.execute(delete(WialonOdometerReading).where(WialonOdometerReading.asset_id == s["loco_id"]))
            for i in range(5):  # a fix every 30 s along the track, ~111 m apart: ~0.44 km over the 2 minutes
                db.add(AssetPositionHistory(asset_id=s["loco_id"], at=s["start"] + timedelta(seconds=30 * i), lat=Decimal(str(round(40.80 + 0.001 * i, 7))), lon=Decimal("69.57"), source="wialon"))
            await db.commit()
        try:
            async with SessionFactory() as db:
                off = await run_wagon_mileage(db, dry_run=True)
            assert off["track_fallback_enabled"] is False and off["track_fallback_used"] == 0
            with patch.object(settings, "wagon_mileage_track_fallback", True):
                async with SessionFactory() as db:
                    dry = await run_wagon_mileage(db, dry_run=True)
                assert dry["track_fallback_enabled"] is True and dry["track_fallback_used"] >= 1
                result = await _run()
                s["run_ids"].append(result.get("run_id")) if isinstance(result, dict) and result.get("run_id") else None
            rows = await _rows(s["wagon_id"])
            active = [r for r in rows if r.status == "active"]
            assert len(active) == 1 and active[0].classification == "ESTIMATED" and active[0].estimated is True
            assert 0.3 < float(active[0].distance_km) < 0.6, active[0].distance_km
            assert str(active[0].calculation_details["reason"]).startswith("gps_track_fallback:")
            assert active[0].calculation_details["track_fallback"]["basis"] in {"fused_track", "track", "single_source", "conflict"}
        finally:
            async with SessionFactory() as db:
                await db.execute(delete(AssetPositionHistory).where(AssetPositionHistory.asset_id == s["loco_id"]))
                await db.commit()
