from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status

from ..schemas.work_order import WorkOrderRead, WorkOrderCreate, WorkOrderUpdate
from ..schemas.pagination import Paginated
from ..services.work_order import WorkOrderService, get_work_order_service
from ..security.dependencies import require_role
from ..models.user import UserRole

router = APIRouter()

ALLOWED_SORT_FIELDS = [
    "created_at",
    "updated_at",
    "date_start",
    "date_end",
    "status",
    "priority",
]


@router.get(
    "",
    response_model=Paginated[WorkOrderRead],
    summary="Get a list of Work Orders",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def list_work_orders(
    service: WorkOrderService = Depends(get_work_order_service),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at", enum=ALLOWED_SORT_FIELDS),
    sort_order: str = Query("desc", enum=["asc", "desc"]),
    status: str | None = None,
    section_id: UUID | None = None,
    department_id: UUID | None = None,
    fixed_asset_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
):
    """
    Retrieve a paginated list of work orders with advanced filtering and sorting.
    """
    return await service.get_all_work_orders(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status=status,
        section_id=section_id,
        department_id=department_id,
        fixed_asset_id=fixed_asset_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )


@router.post(
    "",
    response_model=WorkOrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Work Order",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management))],
)
async def create_work_order(
    wo_in: WorkOrderCreate,
    service: WorkOrderService = Depends(get_work_order_service),
):
    """
    Create a new work order.
    """
    return await service.create_work_order(wo_in)


@router.get(
    "/{work_order_id}",
    response_model=WorkOrderRead,
    summary="Get a single Work Order by ID",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def get_work_order(
    work_order_id: str,
    service: WorkOrderService = Depends(get_work_order_service),
):
    """
    Retrieve a single work order by its unique ID, including related data.
    """
    return await service.get_work_order_by_id(work_order_id)


@router.patch(
    "/{work_order_id}",
    response_model=WorkOrderRead,
    summary="Update a Work Order",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master))],
)
async def update_work_order(
    work_order_id: str,
    wo_in: WorkOrderUpdate,
    service: WorkOrderService = Depends(get_work_order_service),
):
    """
    Update an existing work order. Allows partial updates.
    """
    return await service.update_work_order(work_order_id, wo_in)


# Note: DELETE endpoint is omitted as per soft-delete preference.
# It can be added here if hard-delete is confirmed as the desired strategy.