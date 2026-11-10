from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.mileage import WagonMileageOpeningBalance
from app.repositories import work_orders as work_orders_repository
from app.routers import mileage as mileage_router
from app.schemas.mileage import MileageOpeningCreate
from app.services import assets as assets_service
from app.services import mileage_opening


def _user(user_id=None):
    return SimpleNamespace(
        id=user_id or uuid4(),
        full_name="Test user",
        role="admin",
    )


def _db():
    return SimpleNamespace(
        commit=AsyncMock(),
        refresh=AsyncMock(),
        rollback=AsyncMock(),
    )


def test_opening_requires_timezone_aware_effective_time():
    with pytest.raises(ValidationError):
        MileageOpeningCreate(
            asset_id=uuid4(),
            mileage_km=Decimal("10"),
            effective_at=datetime(2026, 1, 1),
        )


@pytest.mark.asyncio
async def test_submit_opening_creates_pending_balance_without_projecting_asset():
    user = _user()
    asset = SimpleNamespace(id=uuid4(), asset_type="wagon", mileage=Decimal("0"))
    db = _db()
    payload = MileageOpeningCreate(
        asset_id=asset.id,
        mileage_km=Decimal("123.45"),
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        note="Opening",
    )
    created = []

    async def add_opening(_db, opening):
        created.append(opening)
        opening.id = uuid4()
        return opening

    with (
        patch.object(
            mileage_opening.repository,
            "get_asset_for_opening",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            mileage_opening.repository,
            "add_opening_balance",
            side_effect=add_opening,
        ),
        patch.object(mileage_opening, "set_audit_actor"),
    ):
        opening = await mileage_opening.submit_opening_balance(
            db, payload, user=user
        )

    assert opening.status == "pending"
    assert opening.created_by == user.id
    assert opening.approved_by is None
    assert opening.mileage_km == Decimal("123.45")
    assert asset.mileage == Decimal("0")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_opening_submission_is_limited_to_wagons_and_scoped_assets():
    user = _user()
    asset = SimpleNamespace(id=uuid4(), asset_type="locomotive")
    db = _db()
    payload = MileageOpeningCreate(
        asset_id=asset.id,
        mileage_km=Decimal("1"),
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    lookup = AsyncMock(return_value=asset)
    with patch.object(
        mileage_opening.repository, "get_asset_for_opening", new=lookup
    ):
        with pytest.raises(HTTPException) as error:
            await mileage_opening.submit_opening_balance(
                db, payload, user=user, master_section_id=uuid4()
            )
    assert error.value.status_code == 422
    assert lookup.await_args.kwargs["section_id"] is not None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_submitter_approval_remains_pending_until_policy_is_decided():
    user = _user()
    opening = WagonMileageOpeningBalance(
        asset_id=uuid4(),
        mileage_km=Decimal("12"),
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        created_by=user.id,
        status="pending",
    )
    db = _db()
    with patch.object(
        mileage_opening.repository,
        "get_opening_for_update",
        new=AsyncMock(return_value=opening),
    ):
        with pytest.raises(HTTPException) as error:
            await mileage_opening.approve_opening_balance(
                db, uuid4(), user=user
            )
    assert error.value.status_code == 409
    assert opening.status == "pending"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_approval_supersedes_old_balance_and_records_actor_time():
    user = _user()
    previous = WagonMileageOpeningBalance(
        id=uuid4(),
        asset_id=uuid4(),
        mileage_km=Decimal("10"),
        effective_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        created_by=uuid4(),
        approved_by=uuid4(),
        approved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        status="approved",
    )
    opening = WagonMileageOpeningBalance(
        id=uuid4(),
        asset_id=previous.asset_id,
        mileage_km=Decimal("20"),
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        created_by=uuid4(),
        status="pending",
    )
    asset = SimpleNamespace(id=previous.asset_id, asset_type="wagon")
    db = _db()
    with (
        patch.object(
            mileage_opening.repository,
            "get_opening_for_update",
            new=AsyncMock(return_value=opening),
        ),
        patch.object(
            mileage_opening.repository,
            "get_asset_for_opening",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            mileage_opening.repository,
            "get_approved_opening_for_update",
            new=AsyncMock(return_value=previous),
        ),
        patch.object(mileage_opening, "set_audit_actor"),
    ):
        approved = await mileage_opening.approve_opening_balance(
            db, opening.id, user=user
        )

    assert previous.status == "superseded"
    assert approved.status == "approved"
    assert approved.approved_by == user.id
    assert approved.approved_at is not None
    assert approved.supersedes_id == previous.id
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_generic_asset_writes_cannot_bypass_opening_approval():
    with pytest.raises(HTTPException) as create_error:
        await assets_service.create_fixed_asset(
            None,
            SimpleNamespace(mileage=Decimal("10")),
        )
    assert create_error.value.status_code == 422

    asset = SimpleNamespace(id=uuid4(), mileage=Decimal("0"))
    with patch.object(
        assets_service,
        "_get_scoped_asset",
        new=AsyncMock(return_value=asset),
    ):
        with pytest.raises(HTTPException) as update_error:
            await assets_service.update_fixed_asset(
                _db(),
                asset.id,
                assets_service.FixedAssetUpdate(mileage=Decimal("10")),
            )
    assert update_error.value.status_code == 422

    with pytest.raises(HTTPException) as legacy_error:
        await assets_service.set_fixed_asset_mileage(
            _db(),
            uuid4(),
            SimpleNamespace(mileage=Decimal("10")),
        )
    assert legacy_error.value.status_code == 422


@pytest.mark.asyncio
async def test_opening_list_enforces_master_section_scope():
    section_id = uuid4()
    user = SimpleNamespace(role="master", section_id=section_id)
    with patch.object(
        mileage_opening,
        "list_opening_balances",
        new=AsyncMock(return_value=([], 0)),
    ) as list_balances:
        result = await mileage_router.get_openings(
            user, _db(), opening_status=None, limit=100, offset=0
        )

    assert result.total == 0
    assert list_balances.await_args.kwargs["master_section_id"] == section_id


@pytest.mark.asyncio
async def test_opening_list_rejects_unassigned_master():
    user = SimpleNamespace(role="master", section_id=None)
    with pytest.raises(HTTPException) as error:
        await mileage_router.get_openings(
            user, _db(), opening_status=None, limit=100, offset=0
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_only_admin_can_approve_opening():
    user = SimpleNamespace(role="operator")
    with pytest.raises(HTTPException) as error:
        await mileage_router.approve_opening(uuid4(), user, _db())
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_work_order_does_not_read_locomotive_fixed_asset_projection():
    db = SimpleNamespace(execute=AsyncMock())
    asset = SimpleNamespace(asset_type="locomotive", id=uuid4(), mileage=Decimal("900"))

    assert await work_orders_repository.get_known_asset_mileage(db, asset) is None
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_work_order_uses_only_confirmed_wagon_projection():
    db = SimpleNamespace()
    asset = SimpleNamespace(asset_type="wagon", id=uuid4(), mileage=Decimal("500"))
    with patch.object(
        work_orders_repository.mileage_repository,
        "has_confirmed_projection",
        new=AsyncMock(return_value=True),
    ):
        mileage = await work_orders_repository.get_known_asset_mileage(db, asset)
    assert mileage == Decimal("500")

    with patch.object(
        work_orders_repository.mileage_repository,
        "has_confirmed_projection",
        new=AsyncMock(return_value=False),
    ):
        mileage = await work_orders_repository.get_known_asset_mileage(db, asset)
    assert mileage is None
