"""Retention of superseded wagon ledger rows (needs the pg test database)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.mileage import MileageCalculationRun, WagonMileageLedger
from app.services import wagon_ledger_retention as retention

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


async def test_old_superseded_rows_go_active_and_recent_ones_stay_and_chain_links_are_cut():
    tag = uuid4().hex[:8]
    asset_id, run_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    t0 = now - timedelta(days=30)
    ids = [uuid4() for _ in range(4)]  # old(sup) <- old(sup) <- recent(sup) <- active
    async with SessionFactory() as db:
        db.add(FixedAsset(id=asset_id, inv_number=f"RT-{tag}", asset_type="wagon", status="operational", mileage=Decimal("0")))
        db.add(MileageCalculationRun(id=run_id, algorithm_version="t", status="completed"))
        await db.flush()
        spec = [("superseded", 30, None), ("superseded", 29, ids[0]), ("superseded", 2, ids[1]), ("active", 1, ids[2])]
        for i, (status, days_ago, prev) in enumerate(spec):
            db.add(WagonMileageLedger(
                id=ids[i], run_id=run_id, wagon_asset_id=asset_id, period_from=t0, period_to=t0 + timedelta(hours=i + 1),
                distance_km=Decimal("10"), classification="ESTIMATED", status=status, idempotency_key=f"{tag}-{i}",
                algorithm_version="t", input_hash="h", supersedes_id=prev, created_at=now - timedelta(days=days_ago)))
            await db.flush()
        await db.commit()
    try:
        dry = await retention.purge_superseded(older_than_days=14, apply=False)
        assert dry["deleted"] == 0 and dry["would_delete"] >= 2
        done = await retention.purge_superseded(older_than_days=14, apply=True)
        assert done["deleted"] >= 2
        async with SessionFactory() as db:
            left = {r.id: r for r in (await db.execute(select(WagonMileageLedger).where(WagonMileageLedger.wagon_asset_id == asset_id))).scalars()}
        assert set(left) == {ids[2], ids[3]}  # the two old superseded rows are gone, the recent one and the active one stay
        assert left[ids[2]].supersedes_id is None  # its link to a removed row was cut
        assert left[ids[3]].supersedes_id == ids[2] and left[ids[3]].status == "active"
        with pytest.raises(ValueError):
            await retention.purge_superseded(older_than_days=0, apply=False)
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(WagonMileageLedger).where(WagonMileageLedger.wagon_asset_id == asset_id))
            await db.execute(delete(MileageCalculationRun).where(MileageCalculationRun.id == run_id))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
            await db.commit()
