"""Regression tests for defects found by the live end-to-end run (needs pg_rehearse)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.audit_log import AuditLog
from app.models.identity import User
from app.models.mileage import WagonMileageOpeningBalance as Opening
from app.repositories import assets as asset_repository
from app.services import mileage_opening

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


async def _list(**kw):
    async with SessionFactory() as db:
        return await asset_repository.list_assets(
            db, asset_type=None, status=None, status_behavior=None, section_id=None, depot=None,
            q=kw.get("q"), limit=5, offset=0, sort_by=kw.get("sort_by", "created_at"), sort_order="asc",
        )


async def test_asset_search_and_sort_by_name_no_longer_fail():
    tag = uuid4().hex[:8]
    asset_id = uuid4()
    async with SessionFactory() as db:
        db.add(FixedAsset(id=asset_id, inv_number=f"RG-{tag}", asset_type="locomotive", status="operational"))
        await db.commit()
    try:
        items, total = await _list(q=tag)  # used to raise "returned no FROM clauses due to auto-correlation"
        assert total == 1 and items[0].id == asset_id
        items, total = await _list(sort_by="name")
        assert total >= 1
        items, total = await _list(q="%", sort_by="name")
        assert total >= 0
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
            await db.commit()


async def test_a_nul_character_is_a_data_error_the_api_turns_into_422():
    # this used to surface as an unhandled 500; app.main turns a SQLSTATE-22 DBAPIError into a 422
    with pytest.raises(DBAPIError):
        await _list(q="a\x00b")


async def test_a_second_opening_balance_supersedes_the_first_whatever_the_ids_are():
    """Approving a replacement used to fail ~50 % of the time: the unique 'one approved' index saw two approved rows."""
    admin_id, maker_id, wagon_id = uuid4(), uuid4(), uuid4()
    # the NEW row gets the smaller id, which is the order in which SQLAlchemy would update it first
    old_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    new_id = UUID("00000000-0000-4000-8000-000000000001")
    when = datetime.now(timezone.utc) - timedelta(days=1)
    async with SessionFactory() as db:
        for uid, role in ((admin_id, "admin"), (maker_id, "operator")):
            db.add(User(id=uid, email=f"rg-{uid.hex[:8]}@example.test", full_name="RG", role=role, hashed_password="x", is_active=True))
        db.add(FixedAsset(id=wagon_id, inv_number=f"RG-W-{uuid4().hex[:6]}", asset_type="wagon", status="operational"))
        await db.flush()
        db.add(Opening(id=old_id, asset_id=wagon_id, mileage_km=Decimal("100"), effective_at=when, status="approved",
                       created_by=maker_id, approved_by=admin_id, approved_at=when))
        db.add(Opening(id=new_id, asset_id=wagon_id, mileage_km=Decimal("250"), effective_at=when, status="pending", created_by=maker_id))
        await db.commit()
    try:
        async with SessionFactory() as db:
            admin = await db.get(User, admin_id)
            approved = await mileage_opening.approve_opening_balance(db, new_id, user=admin)
        assert approved.status == "approved" and approved.supersedes_id == old_id
        async with SessionFactory() as db:
            statuses = {row.id: row.status for row in (await db.execute(select(Opening).where(Opening.asset_id == wagon_id))).scalars()}
        assert statuses == {old_id: "superseded", new_id: "approved"}
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(Opening).where(Opening.asset_id == wagon_id))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == wagon_id))
            await db.execute(delete(User).where(User.id.in_([admin_id, maker_id])))
            await db.commit()


async def test_a_pure_wialon_sync_update_of_an_asset_is_not_audited_but_a_business_change_is():
    tag = uuid4().hex[:8]
    asset_id = uuid4()

    async def audit_rows():
        async with SessionFactory() as db:
            return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.object_id == str(asset_id)))

    async with SessionFactory() as db:
        db.add(FixedAsset(id=asset_id, inv_number=f"AU-{tag}", asset_type="locomotive", status="operational"))
        await db.commit()
    try:
        created = await audit_rows()
        assert created == 1  # the creation is audited
        async with SessionFactory() as db:  # no audit actor set: this is the system (Wialon pull) path
            asset = await db.get(FixedAsset, asset_id)
            asset.wialon_online = True
            asset.wialon_speed = Decimal("12.5")
            asset.wialon_last_sync = datetime.now(timezone.utc)
            await db.commit()
        assert await audit_rows() == created  # telemetry noise: not audited
        async with SessionFactory() as db:
            asset = await db.get(FixedAsset, asset_id)
            asset.inv_number = f"AU-{tag}-X"
            await db.commit()
        assert await audit_rows() == created + 1  # a real edit is
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.object_id == str(asset_id)))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
            await db.commit()
