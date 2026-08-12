from uuid import UUID
from fastapi import APIRouter, Depends, Query

from ..schemas.employee import EmployeeRead
from ..schemas.pagination import Paginated
from ..services.employee import EmployeeService, get_employee_service
from ..security.dependencies import require_role
from ..models.user import UserRole

router = APIRouter()


@router.get(
    "",
    response_model=Paginated[EmployeeRead],
    summary="Get a list of employees",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def list_employees(
    service: EmployeeService = Depends(get_employee_service),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    section_id: UUID | None = None,
    q: str | None = None,
):
    """
    Retrieve a paginated list of employees.

    Supports filtering by section and searching by name or tab number.
    """
    return await service.get_all_employees(
        limit=limit, offset=offset, section_id=section_id, search_query=q
    )


@router.get(
    "/{employee_id}",
    response_model=EmployeeRead,
    summary="Get a single employee by ID",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.management, UserRole.master, UserRole.operator))],
)
async def get_employee(
    employee_id: UUID,
    service: EmployeeService = Depends(get_employee_service),
):
    """
    Retrieve a single employee by their unique ID.
    """
    return await service.get_employee_by_id(employee_id)