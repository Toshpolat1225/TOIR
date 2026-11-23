from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.core.security import get_current_user
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.maintenance import (
    AvgDailyMileageRow,
    MaintenanceBaselineRead,
    MaintenanceBaselineUpsert,
    MaintenanceDecisionRead,
    MaintenanceDisruptionCreate,
    MaintenanceDisruptionRead,
    MaintenanceHealthRead,
    MaintenanceKpiRead,
    MaintenancePlanBlock,
    MaintenancePlanFromForecast,
    MaintenancePlanRead,
    MaintenancePlanUpdate,
    MaintenancePlanWaive,
    MaintenanceScheduleRead,
    MaintenanceSettingsRead,
    MaintenanceSettingsUpdate,
    MaintenanceUrgency,
)
from app.services import avg_daily_mileage
from app.services import maintenance as service
from app.services import maintenance_lifecycle as lifecycle

router = APIRouter(tags=["maintenance"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
MaintenanceConfigurator = Annotated[User, Depends(require_permission("maintenance.update"))]
MaintenanceSettingsEditor = Annotated[User, Depends(require_permission("maintenance_settings.update"))]
PlanStatus = Literal[
    "scheduled", "in_progress", "completed", "cancelled", "blocked", "covered", "waived"
]


@router.get("/maintenance-settings", response_model=MaintenanceSettingsRead)
async def read_maintenance_settings(
    _: AuthenticatedUser, db: DatabaseSession
) -> MaintenanceSettingsRead:
    return await service.get_settings(db)


@router.patch("/maintenance-settings", response_model=MaintenanceSettingsRead)
async def patch_maintenance_settings(
    payload: MaintenanceSettingsUpdate,
    current_user: MaintenanceSettingsEditor,
    db: DatabaseSession,
) -> MaintenanceSettingsRead:
    _require_planner(current_user)  # the permission alone also let the read-mostly `management` role change it
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
    urgency: MaintenanceUrgency | None = None,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[MaintenancePlanRead]:
    items, total = await service.list_plans(
        db,
        current_user,
        asset_id=asset_id,
        status_filter=status_filter,
        urgency_filter=urgency,
        month=month,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/maintenance-plan/from-forecast",
    response_model=MaintenancePlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_plan_from_forecast(
    payload: MaintenancePlanFromForecast,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenancePlanRead:
    if current_user.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and operators can plan maintenance",
        )
    return await service.create_plan_from_forecast(db, current_user, payload)


@router.patch(
    "/maintenance-plan/{plan_id}", response_model=MaintenancePlanRead
)
async def patch_maintenance_plan(
    plan_id: UUID,
    payload: MaintenancePlanUpdate,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenancePlanRead:
    if current_user.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and operators can update maintenance plans",
        )
    return await service.update_plan(db, current_user, plan_id, payload)


def _require_planner(user: User) -> None:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and operators can change the maintenance plan",
        )


@router.post("/maintenance-plan/{plan_id}/block", response_model=MaintenancePlanRead)
async def block_maintenance_plan(
    plan_id: UUID,
    payload: MaintenancePlanBlock,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenancePlanRead:
    _require_planner(current_user)
    return await service.block_plan(db, current_user, plan_id, payload)


@router.post("/maintenance-plan/{plan_id}/unblock", response_model=MaintenancePlanRead)
async def unblock_maintenance_plan(
    plan_id: UUID,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenancePlanRead:
    _require_planner(current_user)
    return await service.unblock_plan(db, current_user, plan_id)


@router.post("/maintenance-plan/{plan_id}/waive", response_model=MaintenancePlanRead)
async def waive_maintenance_plan(
    plan_id: UUID,
    payload: MaintenancePlanWaive,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenancePlanRead:
    return await service.waive_plan(db, current_user, plan_id, payload)  # admin-only inside


@router.get(
    "/maintenance-plan/{plan_id}/decisions",
    response_model=list[MaintenanceDecisionRead],
)
async def read_maintenance_plan_decisions(
    plan_id: UUID, current_user: AuthenticatedUser, db: DatabaseSession
) -> list[MaintenanceDecisionRead]:
    return await service.list_plan_decisions(db, current_user, plan_id)


@router.get("/maintenance-disruptions", response_model=list[MaintenanceDisruptionRead])
async def read_maintenance_disruptions(
    _: AuthenticatedUser,
    db: DatabaseSession,
    only_open: bool = True,
) -> list[MaintenanceDisruptionRead]:
    return await lifecycle.list_disruptions(db, only_open=only_open)


@router.post(
    "/maintenance-disruptions",
    response_model=MaintenanceDisruptionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_disruption(
    payload: MaintenanceDisruptionCreate,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenanceDisruptionRead:
    _require_planner(current_user)
    return await lifecycle.create_disruption(db, payload, current_user)


@router.post(
    "/maintenance-disruptions/{disruption_id}/close",
    response_model=MaintenanceDisruptionRead,
)
async def close_maintenance_disruption(
    disruption_id: UUID,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenanceDisruptionRead:
    _require_planner(current_user)
    return await lifecycle.close_disruption(db, disruption_id, current_user)


@router.get("/maintenance-baselines", response_model=list[MaintenanceBaselineRead])
async def read_maintenance_baselines(
    asset_id: UUID, current_user: AuthenticatedUser, db: DatabaseSession
) -> list[MaintenanceBaselineRead]:
    return await lifecycle.list_baselines(
        db, asset_id=asset_id, master_section_id=service._master_section_scope(current_user)
    )


@router.put("/maintenance-baselines", response_model=MaintenanceBaselineRead)
async def put_maintenance_baseline(
    payload: MaintenanceBaselineUpsert,
    current_user: MaintenanceConfigurator,
    db: DatabaseSession,
) -> MaintenanceBaselineRead:
    _require_planner(current_user)
    return await lifecycle.set_baseline(db, payload, current_user)


@router.get("/maintenance-kpis", response_model=MaintenanceKpiRead)
async def read_maintenance_kpis(
    current_user: AuthenticatedUser, db: DatabaseSession
) -> MaintenanceKpiRead:
    return await lifecycle.compute_kpis(
        db, master_section_id=service._master_section_scope(current_user)
    )


@router.get("/maintenance-health", response_model=MaintenanceHealthRead)
async def read_maintenance_health(
    current_user: MaintenanceConfigurator, db: DatabaseSession
) -> MaintenanceHealthRead:
    _require_planner(current_user)
    return await lifecycle.run_health(db, fix=False)


@router.get("/maintenance-avg-daily-mileage", response_model=list[AvgDailyMileageRow])
async def read_avg_daily_mileage(
    current_user: AuthenticatedUser, db: DatabaseSession
) -> list[dict]:
    """Average daily mileage per section and equipment type (a master sees only their own section)."""
    return await avg_daily_mileage.compute(db, section_id=service._master_section_scope(current_user))


@router.get("/maintenance-avg-daily-mileage/detail")
async def read_avg_daily_mileage_detail(
    current_user: AuthenticatedUser, db: DatabaseSession, section_id: UUID, asset_type: str
) -> dict:
    """How one group's average was calculated. A master asking for another section gets 404."""
    scope = service._master_section_scope(current_user)
    if scope is not None and scope != section_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    result = await avg_daily_mileage.detail(db, section_id=section_id, asset_type=asset_type)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return result
