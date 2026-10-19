from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
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
AuthenticatedUser = Annotated[User, Depends(require_permission("maintenance.view"))]
MaintenanceConfigurator = Annotated[User, Depends(require_permission("maintenance.update"))]
MaintenanceSettingsEditor = Annotated[User, Depends(require_permission("maintenance_settings.update"))]
PlanStatus = Literal["scheduled", "in_progress", "completed", "cancelled"]


@router.get("/maintenance-settings", response_model=MaintenanceSettingsRead)
async def read_maintenance_settings(
    _: AuthenticatedUser, db: DatabaseSession
) -> MaintenanceSettingsRead:
    return await service.get_settings(db)


@router.patch("/maintenance-settings", response_model=MaintenanceSettingsRead)
async def patch_maintenance_settings(
    payload: MaintenanceSettingsUpdate,
    _: MaintenanceSettingsEditor,
    db: DatabaseSession,
) -> MaintenanceSettingsRead:
    return await service.update_settings(db, payload)


@router.get("/maintenance-schedule", response_model=MaintenanceScheduleRead)
async def read_maintenance_schedule(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
) -> MaintenanceScheduleRead:
    return await service.get_schedule(db, current_user, month)


@router.get(
    "/maintenance-plan", response_model=PaginatedResponse[MaintenancePlanRead]
)
async def read_maintenance_plans(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    asset_id: UUID | None = None,
    status_filter: Annotated[PlanStatus | None, Query(alias="status")] = None,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[MaintenancePlanRead]:
    items, total = await service.list_plans(
        db,
        current_user,
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
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenancePlanRead:
    return await service.update_plan(db, current_user, plan_id, payload)
