import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.mileage import WagonMileageOpeningBalance
from app.repositories import mileage as repository
from app.schemas.mileage import MileageOpeningCreate
from app.services.audit_log import set_audit_actor

logger = logging.getLogger(__name__)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opening balance not found")


async def submit_opening_balance(
    db: AsyncSession,
    payload: MileageOpeningCreate,
    *,
    user: User,
    master_section_id: UUID | None = None,
) -> WagonMileageOpeningBalance:
    asset = await repository.get_asset_for_opening(
        db, payload.asset_id, section_id=master_section_id, lock=True
    )
    if asset is None:
        raise _not_found()
    if asset.asset_type != "wagon":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Opening balance is only available for wagons",
        )

    set_audit_actor(
        db,
        actor_id=user.id,
        actor_name=user.full_name,
        actor_type="user",
        route="/api/v1/wagon-mileage/openings",
    )
    opening = WagonMileageOpeningBalance(
        asset_id=asset.id,
        mileage_km=payload.mileage_km,
        effective_at=payload.effective_at.astimezone(timezone.utc),
        created_by=user.id,
        note=payload.note,
        status="pending",
    )
    try:
        await repository.add_opening_balance(db, opening)
        await db.commit()
        await db.refresh(opening)
    except IntegrityError as exc:
        await db.rollback()
        logger.exception("Could not save wagon mileage opening balance")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Opening balance could not be saved",
        ) from exc
    return opening


async def approve_opening_balance(
    db: AsyncSession,
    opening_id: UUID,
    *,
    user: User,
) -> WagonMileageOpeningBalance:
    opening = await repository.get_opening_for_update(db, opening_id)
    if opening is None:
        raise _not_found()
    if opening.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Opening balance is not pending",
        )
    if opening.created_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submitter and approver policy is pending approval",
        )

    asset = await repository.get_asset_for_opening(db, opening.asset_id, lock=True)
    if asset is None:
        raise _not_found()
    if asset.asset_type != "wagon":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Opening balance asset is no longer a wagon",
        )

    previous = await repository.get_approved_opening_for_update(db, asset.id)
    if previous is not None:
        previous.status = "superseded"
        opening.supersedes_id = previous.id

    set_audit_actor(
        db,
        actor_id=user.id,
        actor_name=user.full_name,
        actor_type="user",
        route="/api/v1/wagon-mileage/openings/approve",
    )
    opening.status = "approved"
    opening.approved_by = user.id
    opening.approved_at = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(opening)
    except IntegrityError as exc:
        await db.rollback()
        logger.exception("Could not approve wagon mileage opening balance")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another opening balance was approved concurrently",
        ) from exc
    return opening


async def list_opening_balances(
    db: AsyncSession,
    *,
    asset_id: UUID | None = None,
    master_section_id: UUID | None = None,
    opening_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[WagonMileageOpeningBalance], int]:
    if asset_id is not None:
        asset = await repository.get_asset_for_opening(
            db, asset_id, section_id=master_section_id
        )
        if asset is None:
            raise _not_found()
    return await repository.list_opening_balances(
        db,
        asset_id=asset_id,
        section_id=master_section_id,
        status=opening_status,
        limit=limit,
        offset=offset,
    )
