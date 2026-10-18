from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.assets import (
    AssetStatus,
    AssetType,
    FixedAssetCreate,
    FixedAssetRead,
    FixedAssetStats,
    FixedAssetUpdate,
    MileageHistoryList,
    MileageUpdate,
)
from app.schemas.asset_catalogs import AssetBehavior
from app.schemas.common import PaginatedResponse
from app.services import assets as service

router = APIRouter(prefix="/fixed-assets", tags=["fixed assets"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(require_permission("assets.view"))]
AssetCreator = Annotated[User, Depends(require_permission("assets.create"))]
AssetUpdater = Annotated[User, Depends(require_permission("assets.update"))]
AssetDeleter = Annotated[User, Depends(require_permission("assets.delete"))]
SortOrder = Literal["asc", "desc"]


def _master_section(user: User) -> UUID | None:
    if user.role == "master" and user.section_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master user must be assigned to a section",
        )
    return user.section_id if user.role == "master" else None


@router.get("/stats", response_model=FixedAssetStats)
async def get_fixed_asset_stats(
    user: AuthenticatedUser, db: DatabaseSession,
    asset_type: AssetType | None = None,
    status_filter: Annotated[AssetStatus | None, Query(alias="status")] = None,
    status_behavior: AssetBehavior | None = None, section_id: UUID | None = None,
    depot: str | None = None, q: str | None = Query(default=None, max_length=200),
) -> FixedAssetStats:
    return await service.get_fixed_asset_stats(
        db, master_section_id=_master_section(user), asset_type=asset_type,
        asset_status=status_filter, status_behavior=status_behavior,
        section_id=section_id, depot=depot, q=q,
    )


@router.get("", response_model=PaginatedResponse[FixedAssetRead])
async def get_fixed_assets(
    user: AuthenticatedUser,
    db: DatabaseSession,
    asset_type: AssetType | None = None,
    status_filter: Annotated[
        AssetStatus | None, Query(alias="status")
    ] = None,
    status_behavior: AssetBehavior | None = None,
    section_id: UUID | None = None,
    depot: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_order: SortOrder = Query(default="desc"),
) -> PaginatedResponse[FixedAssetRead]:
    items, total = await service.list_fixed_assets(
        db,
        asset_type=asset_type,
        asset_status=status_filter,
        status_behavior=status_behavior,
        section_id=section_id,
        master_section_id=_master_section(user),
        depot=depot,
        q=q,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[FixedAssetRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/{asset_id}/mileage-history", response_model=MileageHistoryList)
async def get_asset_mileage_history(
    asset_id: UUID,
    user: AuthenticatedUser,
    db: DatabaseSession,
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=100, ge=1, le=1000),
) -> MileageHistoryList:
    return await service.get_mileage_history(
        db,
        asset_id,
        days=days,
        limit=limit,
        master_section_id=_master_section(user),
    )


@router.post(
    "/{asset_id}/mileage",
    response_model=FixedAssetRead,
)
async def post_asset_mileage(
    asset_id: UUID, payload: MileageUpdate, _: AssetUpdater, db: DatabaseSession
) -> FixedAssetRead:
    return await service.set_fixed_asset_mileage(db, asset_id, payload)


@router.get("/{asset_id}", response_model=FixedAssetRead)
async def get_fixed_asset(
    asset_id: UUID, user: AuthenticatedUser, db: DatabaseSession
) -> FixedAssetRead:
    return await service.get_fixed_asset(
        db, asset_id, master_section_id=_master_section(user)
    )


@router.post(
    "",
    response_model=FixedAssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_fixed_asset(
    payload: FixedAssetCreate, _: AssetCreator, db: DatabaseSession
) -> FixedAssetRead:
    return await service.create_fixed_asset(db, payload)


@router.patch("/{asset_id}", response_model=FixedAssetRead)
async def patch_fixed_asset(
    asset_id: UUID,
    payload: FixedAssetUpdate,
    _: AssetUpdater,
    db: DatabaseSession,
) -> FixedAssetRead:
    return await service.update_fixed_asset(db, asset_id, payload)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_fixed_asset(
    asset_id: UUID, _: AssetDeleter, db: DatabaseSession
) -> Response:
    await service.delete_fixed_asset(db, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
