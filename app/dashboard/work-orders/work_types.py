from uuid import UUID
from fastapi import APIRouter, Depends, Query

from ..schemas.work_type import WorkTypeRead
from ..schemas.pagination import Paginated
from ..services.work_type import WorkTypeService, get_work_type_service
from ..security.dependencies import require_role
from ..models.user import UserRole

router = APIRouter()


@router.get(
    "",
    response_model=Paginated[WorkTypeRead],
    summary="Get a list of work types",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def list_work_types(
    service: WorkTypeService = Depends(get_work_type_service),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    unit_type: str | None = None,
):
    """
    Retrieve a paginated list of work types, optionally filtered by unit type
    (e.g., 'locomotive', 'wagon').
    """
    return await service.get_all(limit=limit, offset=offset, unit_type=unit_type)


@router.get(
    "/{work_type_id}",
    response_model=WorkTypeRead,
    summary="Get a single work type by ID",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def get_work_type(
    work_type_id: UUID,
    service: WorkTypeService = Depends(get_work_type_service),
):
    """
    Retrieve a single work type by its unique ID.
    """
    return await service.get_by_id(work_type_id)