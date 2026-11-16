"""Which wagons does the maintenance planner trust? (decision D9; needs pg_rehearse)

A wagon's mileage is a published projection once an administrator approved its opening balance:
projection = approved opening + eligible CONFIRMED *and* ESTIMATED ledger km. The planner used to ask for
a CONFIRMED ledger row, which dropped ~480 of 481 wagons that had a real, approved projection.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrain
from app.models.identity import User
from app.models.maintenance import MaintenanceInterval
from app.models.mileage import MileageCalculationRun, WagonMileageLedger
from app.models.mileage import WagonMileageOpeningBalance as Opening
from app.repositories import mileage as mileage_repository
from app.services import maintenance_obligations as obligations

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]

T0 = datetime(2026, 11, 14, tzinfo=timezone.utc)
TRAIN_ID = 920_000_000 + (uuid4().int % 70_000_000)


class Fleet:
    def __init__(self):
        tag = uuid4().hex[:8]
        self.tag = tag
        self.admin_id = uuid4()
        self.run_id = uuid4()
        self.interval_id = uuid4()
        self.wagons: dict[str, object] = {}

    def wagon(self, name):
        self.wagons[name] = uuid4()
        return self.wagons[name]


@pytest_asyncio.fixture
async def fleet():
    f = Fleet()
    async with SessionFactory() as db:
        db.add(User(id=f.admin_id, email=f"gate-{f.tag}@example.test", full_name="Gate", role="admin", hashed_password="x", is_active=True))
        db.add(GtkTrain(gtk_id=TRAIN_ID, is_open=False))
        db.add(MileageCalculationRun(id=f.run_id, status="completed", algorithm_version="test"))
        db.add(MaintenanceInterval(id=f.interval_id, code=f"W-{f.tag}", name="wagon gate", interval_km=Decimal("90"),
                                   asset_types=["wagon"], is_active=True))
        await db.commit()
    yield f
    ids = list(f.wagons.values())
    async with SessionFactory() as db:
        await db.execute(delete(WagonMileageLedger).where(WagonMileageLedger.wagon_asset_id.in_(ids)))
        await db.execute(delete(Opening).where(Opening.asset_id.in_(ids)))
        await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(ids)))
        await db.execute(delete(MaintenanceInterval).where(MaintenanceInterval.id == f.interval_id))
        await db.execute(delete(MileageCalculationRun).where(MileageCalculationRun.id == f.run_id))
        await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == TRAIN_ID))
        await db.execute(delete(User).where(User.id == f.admin_id))
        await db.commit()


async def _add_wagon(f: Fleet, name: str, *, mileage="0", opening: str | None = None, ledger: tuple[str, ...] = ()):
    wagon_id = f.wagon(name)
    async with SessionFactory() as db:
        db.add(FixedAsset(id=wagon_id, inv_number=f"G-{f.tag}-{name}", asset_type="wagon", status="operational", mileage=Decimal(mileage)))
        await db.flush()
        if opening is not None:
            now = datetime.now(timezone.utc)
            db.add(Opening(
                asset_id=wagon_id, mileage_km=Decimal("0"), effective_at=T0 - timedelta(days=1), status=opening,
                created_by=f.admin_id,
                **({"approved_by": f.admin_id, "approved_at": now} if opening == "approved" else {}),
            ))
        for index, classification in enumerate(ledger):
            db.add(WagonMileageLedger(
                run_id=f.run_id, wagon_asset_id=wagon_id, train_gtk_id=TRAIN_ID,
                period_from=T0 + timedelta(hours=index), period_to=T0 + timedelta(hours=index, minutes=30),
                distance_km=Decimal("10"), estimated=classification == "ESTIMATED", status="active",
                idempotency_key=uuid4().hex, classification=classification, calculation_eligible=classification != "HELD",
                algorithm_version="test", input_hash=uuid4().hex + uuid4().hex,
            ))
        await db.commit()
    return wagon_id


async def test_only_an_approved_opening_balance_makes_the_projection_trusted(fleet):
    approved = await _add_wagon(fleet, "approved", opening="approved", ledger=("ESTIMATED",))
    pending = await _add_wagon(fleet, "pending", opening="pending", ledger=("CONFIRMED",))
    rejected = await _add_wagon(fleet, "rejected", opening="rejected", ledger=("CONFIRMED",))
    superseded = await _add_wagon(fleet, "superseded", opening="superseded", ledger=("CONFIRMED",))
    bare = await _add_wagon(fleet, "bare", ledger=("CONFIRMED", "ESTIMATED"))  # a ledger without an approved opening
    async with SessionFactory() as db:
        verdicts = {name: await mileage_repository.has_approved_projection(db, wagon_id)
                    for name, wagon_id in fleet.wagons.items()}
        trusted = await mileage_repository.approved_projection_asset_ids(db, fleet.wagons.values())
    assert verdicts == {"approved": True, "pending": False, "rejected": False, "superseded": False, "bare": False}
    assert trusted == {approved}
    assert pending not in trusted and rejected not in trusted and superseded not in trusted and bare not in trusted


async def test_a_wagon_whose_km_are_only_estimated_is_trusted_but_flagged(fleet):
    estimated = await _add_wagon(fleet, "estimated", mileage="40", opening="approved", ledger=("ESTIMATED", "ESTIMATED"))
    measured = await _add_wagon(fleet, "measured", mileage="40", opening="approved", ledger=("CONFIRMED",))
    quiet = await _add_wagon(fleet, "quiet", mileage="0", opening="approved")  # approved opening, no movement yet
    async with SessionFactory() as db:
        trusted = await mileage_repository.approved_projection_asset_ids(db, fleet.wagons.values())
        flagged = await mileage_repository.estimated_projection_asset_ids(db, trusted)
    assert trusted == {estimated, measured, quiet}  # the old rule would have kept only `measured`
    assert flagged == {estimated}


async def test_wagon_pace_comes_from_the_ledger_and_gives_the_wagon_a_date(fleet):
    obligations.reset_pace_book()
    # ledger rows of the fixture: 10 km each, one per hour from 2026-11-14 00:00 (UTC): 9 rows cover 8.5 h of that day
    runner = await _add_wagon(fleet, "runner", mileage="40", opening="approved", ledger=("ESTIMATED",) * 9)
    idle = await _add_wagon(fleet, "idle", mileage="0", opening="approved")
    stranger = await _add_wagon(fleet, "stranger", mileage="40", ledger=("ESTIMATED",))  # no approved opening
    async with SessionFactory() as db:
        book = await obligations.get_pace_book(db, T0.date() + timedelta(days=3), force=True)
        assert runner in book.km_deltas and idle in book.km_deltas
        assert stranger not in book.km_deltas  # no published projection, so no pace either
        assert any(rate > 0 for rate in book.km_deltas[runner])
        assert all(rate == 0 for rate in book.km_deltas[idle])  # covered by the ledger window but never moved
        assert book.group_km["wagon"] is not None  # a group of wagons forms from the ledger
        asset = await db.get(FixedAsset, runner)
        _, evaluated = await obligations.evaluate_for_asset(db, asset, today=T0.date() + timedelta(days=3))
    [ob] = [o for o in evaluated if o.interval.id == fleet.interval_id]
    assert ob.pace_km is not None and ob.pace_km.p75 > 0
    assert ob.markers.date_p75 is not None  # the wagon can now be put on a calendar
    obligations.reset_pace_book()


async def test_the_planner_now_sees_wagons_that_have_an_approved_projection(fleet):
    obligations.reset_pace_book()
    estimated = await _add_wagon(fleet, "estimated", mileage="40", opening="approved", ledger=("ESTIMATED",))
    untrusted = await _add_wagon(fleet, "untrusted", mileage="40", ledger=("ESTIMATED",))
    async with SessionFactory() as db:
        results = {}
        for name, wagon_id in (("estimated", estimated), ("untrusted", untrusted)):
            asset = await db.get(FixedAsset, wagon_id)
            _, evaluated = await obligations.evaluate_for_asset(db, asset)
            results[name] = [ob for ob in evaluated if ob.interval.id == fleet.interval_id]
    [ob] = results["estimated"]
    assert ob.mileage_estimated is True and ob.confidence == "low"
    assert ob.markers.used == Decimal("40.00") and ob.due_km == Decimal("90.00")
    assert results["untrusted"] == []  # no approved opening: no published projection, no km obligation
    obligations.reset_pace_book()
