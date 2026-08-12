from fastapi import APIRouter, Depends, Query

from ..schemas.maintenance_schedule import MaintenanceScheduleResponse
from ..services.maintenance_schedule import (
    MaintenanceScheduleService,
    get_maintenance_schedule_service,
)
from ..security.dependencies import require_role
from ..models.user import UserRole

router = APIRouter()


@router.get(
    "",
    response_model=MaintenanceScheduleResponse,
    summary="Get the aggregated maintenance schedule",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def get_maintenance_schedule(
    service: MaintenanceScheduleService = Depends(get_maintenance_schedule_service),
    month: str
    | None = Query(
        None,
        pattern=r"^\d{4}-\d{2}$",
        description="The month to generate the schedule for, in YYYY-MM format.",
    ),
):
    """
    Retrieve the aggregated maintenance schedule for a given month, combining
    existing work orders, planned maintenance, and calculated future maintenance based on mileage.
    """
    schedule_items = await service.get_schedule(month_str=month)
    return MaintenanceScheduleResponse(schedule=schedule_items)