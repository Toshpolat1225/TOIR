from uuid import UUID
from fastapi import APIRouter, Depends, Query

from ..schemas.maintenance_interval import MaintenanceIntervalRead
from ..schemas.pagination import Paginated
from ..services.maintenance_interval import (
    MaintenanceIntervalService,
    get_maintenance_interval_service,
)
from ..security.dependencies import require_role
from ..models.user import UserRole

router = APIRouter()


@router.get(
    "",
    response_model=Paginated[MaintenanceIntervalRead],
    summary="Get a list of maintenance intervals",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def list_maintenance_intervals(
    service: MaintenanceIntervalService = Depends(get_maintenance_interval_service),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    asset_type: str | None = None,
):
    """
    Retrieve a paginated list of maintenance intervals.
    """
    return await service.get_all(limit=limit, offset=offset, asset_type=asset_type)


@router.get(
    "/{interval_id}",
    response_model=MaintenanceIntervalRead,
    summary="Get a single maintenance interval by ID",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def get_maintenance_interval(
    interval_id: UUID,
    service: MaintenanceIntervalService = Depends(get_maintenance_interval_service),
):
    """
    Retrieve a single maintenance interval by its unique ID.
    """
    return await service.get_by_id(interval_id)