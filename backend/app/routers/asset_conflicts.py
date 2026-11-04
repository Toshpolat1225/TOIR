from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.asset_field_changes import AssetFieldChangeRead
from app.schemas.common import PaginatedResponse
from app.services import asset_field_changes as service

router = APIRouter(prefix="/asset-conflicts", tags=["asset conflicts"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
ConflictManager = Annotated[User, Depends(require_permission("asset_conflicts.manage"))]


@router.get("", response_model=PaginatedResponse[AssetFieldChangeRead])
async def list_asset_conflicts(
    _: ConflictManager,
    db: DatabaseSession,
    status_filter: Annotated[
        Literal["pending", "applied", "accepted", "rejected"],
        Query(alias="status"),
    ] = "pending",
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AssetFieldChangeRead]:
    items, total = await service.list_conflicts(
        db, status_filter=status_filter, limit=limit, offset=offset
    )
    return PaginatedResponse[AssetFieldChangeRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.post("/{change_id}/accept", response_model=AssetFieldChangeRead)
async def accept_asset_conflict(
    change_id: int,
    user: ConflictManager,
    db: DatabaseSession,
) -> AssetFieldChangeRead:
    return await service.accept_conflict(db, change_id, user.id)


@router.post("/{change_id}/reject", response_model=AssetFieldChangeRead)
async def reject_asset_conflict(
    change_id: int,
    user: ConflictManager,
    db: DatabaseSession,
) -> AssetFieldChangeRead:
    return await service.reject_conflict(db, change_id, user.id)
