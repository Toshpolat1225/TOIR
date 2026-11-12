from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.mileage import (
    MileageOpeningCreate,
    MileageOpeningList,
    MileageOpeningRead,
    WagonMileageSummary,
)
from app.services import mileage_opening

router = APIRouter(prefix="/wagon-mileage", tags=["wagon-mileage"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AssetUpdater = Annotated[User, Depends(require_permission("assets.update"))]


def _master_section(user: User) -> UUID | None:
    if user.role == "master" and user.section_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master user must be assigned to a section",
        )
    return user.section_id if user.role == "master" else None


@router.post("/openings", response_model=MileageOpeningRead, status_code=201)
async def submit_opening(
    payload: MileageOpeningCreate,
    user: AssetUpdater,
    db: DatabaseSession,
) -> MileageOpeningRead:
    opening = await mileage_opening.submit_opening_balance(
        db,
        payload,
        user=user,
        master_section_id=_master_section(user),
    )
    return MileageOpeningRead.model_validate(opening)


@router.get("/openings", response_model=MileageOpeningList)
async def get_openings(
    user: Annotated[User, Depends(require_permission("assets.view"))],
    db: DatabaseSession,
    asset_id: UUID | None = None,
    opening_status: Annotated[
        str | None, Query(alias="status", pattern="^(pending|approved|rejected|superseded)$")
    ] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> MileageOpeningList:
    items, total = await mileage_opening.list_opening_balances(
        db,
        asset_id=asset_id,
        master_section_id=_master_section(user),
        opening_status=opening_status,
        limit=limit,
        offset=offset,
    )
    return MileageOpeningList(
        items=[MileageOpeningRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/openings/{opening_id}/approve",
    response_model=MileageOpeningRead,
)
async def approve_opening(
    opening_id: UUID,
    user: AssetUpdater,
    db: DatabaseSession,
) -> MileageOpeningRead:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can approve opening balances",
        )
    opening = await mileage_opening.approve_opening_balance(
        db, opening_id, user=user
    )
    return MileageOpeningRead.model_validate(opening)


@router.get("/assets/{asset_id}", response_model=WagonMileageSummary)
async def get_wagon_mileage(
    asset_id: UUID,
    user: Annotated[User, Depends(require_permission("assets.view"))],
    db: DatabaseSession,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> WagonMileageSummary:
    return await mileage_opening.get_wagon_mileage_summary(
        db,
        asset_id,
        master_section_id=_master_section(user),
        limit=limit,
        offset=offset,
    )
