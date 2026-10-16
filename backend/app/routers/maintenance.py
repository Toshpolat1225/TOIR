from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.maintenance import (
    MaintenancePlanRead,
    MaintenancePlanUpdate,
    MaintenanceScheduleRead,
    MaintenanceSettingsRead,
    MaintenanceSettingsUpdate,
)
from app.services import maintenance as service

router = APIRouter(tags=["maintenance"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
MaintenanceConfigurator = Annotated[
    User, Depends(require_role("admin", "operator", "management"))
]
PlanStatus = Literal["scheduled", "in_progress", "completed", "cancelled"]


@router.get("/maintenance-settings", response_model=MaintenanceSettingsRead)
async def read_maintenance_settings(
    _: AuthenticatedUser, db: DatabaseSession
) -> MaintenanceSettingsRead:
    return await service.get_settings(db)


@router.patch("/maintenance-settings", response_model=MaintenanceSettingsRead)
async def patch_maintenance_settings(
    payload: MaintenanceSettingsUpdate,
    _: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenanceSettingsRead:
    return await service.update_settings(db, payload)


@router.get("/maintenance-schedule", response_model=MaintenanceScheduleRead)
async def read_maintenance_schedule(
    _: AuthenticatedUser,
    db: DatabaseSession,
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
) -> MaintenanceScheduleRead:
    return await service.get_schedule(db, month)


@router.get(
    "/maintenance-plan", response_model=PaginatedResponse[MaintenancePlanRead]
)
async def read_maintenance_plans(
    _: AuthenticatedUser,
    db: DatabaseSession,
    asset_id: UUID | None = None,
    status_filter: Annotated[PlanStatus | None, Query(alias="status")] = None,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[MaintenancePlanRead]:
    items, total = await service.list_plans(
        db,
        asset_id=asset_id,
        status_filter=status_filter,
        month=month,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/maintenance-plan/{plan_id}", response_model=MaintenancePlanRead
)
async def patch_maintenance_plan(
    plan_id: UUID,
    payload: MaintenancePlanUpdate,
    _: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenancePlanRead:
    return await service.update_plan(db, plan_id, payload)
