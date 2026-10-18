from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.references import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
    MaintenanceIntervalCreate,
    MaintenanceIntervalRead,
    MaintenanceIntervalUpdate,
    SectionCreate,
    SectionRead,
    SectionUpdate,
    WorkSubtaskCreate,
    WorkSubtaskRead,
    WorkSubtaskUpdate,
    WorkTypeCreate,
    WorkTypeRead,
    WorkTypeTemplateCreate,
    WorkTypeTemplateRead,
    WorkTypeTemplateUpdate,
    WorkTypeUpdate,
)
from app.services import references as service

router = APIRouter(tags=["reference data"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(require_permission("organization.view"))]
ReferenceCreator = Annotated[User, Depends(require_permission("organization.create"))]
ReferenceUpdater = Annotated[User, Depends(require_permission("organization.update"))]
ReferenceDeleter = Annotated[User, Depends(require_permission("organization.delete"))]
SortOrder = Literal["asc", "desc"]


def _master_section_id(user: User) -> UUID | None:
    if user.role == "master" and user.section_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master user must be assigned to a section",
        )
    return user.section_id if user.role == "master" else None


@router.get("/departments", response_model=PaginatedResponse[DepartmentRead])
async def get_departments(
    _: AuthenticatedUser,
    db: DatabaseSession,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[DepartmentRead]:
    items, total = await service.list_departments(
        db,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[DepartmentRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/departments/{department_id}", response_model=DepartmentRead)
async def get_department(
    department_id: UUID, _: AuthenticatedUser, db: DatabaseSession
) -> DepartmentRead:
    return await service.get_department(db, department_id)


@router.post(
    "/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_department(
    payload: DepartmentCreate, _: ReferenceCreator, db: DatabaseSession
) -> DepartmentRead:
    return await service.create_department(db, payload)


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
async def patch_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    _: ReferenceUpdater,
    db: DatabaseSession,
) -> DepartmentRead:
    return await service.update_department(db, department_id, payload)


@router.delete(
    "/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_department(
    department_id: UUID, _: ReferenceDeleter, db: DatabaseSession
) -> Response:
    await service.delete_department(db, department_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sections", response_model=PaginatedResponse[SectionRead])
async def get_sections(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[SectionRead]:
    items, total = await service.list_sections(
        db,
        master_section_id=(
            current_user.section_id if current_user.role == "master" else None
        ),
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[SectionRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/sections/{section_id}", response_model=SectionRead)
async def get_section(
    section_id: UUID, current_user: AuthenticatedUser, db: DatabaseSession
) -> SectionRead:
    return await service.get_section(
        db,
        section_id,
        master_section_id=(
            current_user.section_id if current_user.role == "master" else None
        ),
    )


@router.post(
    "/sections",
    response_model=SectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_section(
    payload: SectionCreate, _: ReferenceCreator, db: DatabaseSession
) -> SectionRead:
    return await service.create_section(db, payload)


@router.patch("/sections/{section_id}", response_model=SectionRead)
async def patch_section(
    section_id: UUID,
    payload: SectionUpdate,
    _: ReferenceUpdater,
    db: DatabaseSession,
) -> SectionRead:
    return await service.update_section(db, section_id, payload)


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_section(
    section_id: UUID, _: ReferenceDeleter, db: DatabaseSession
) -> Response:
    await service.delete_section(db, section_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/employees", response_model=PaginatedResponse[EmployeeRead])
async def get_employees(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    section_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="full_name"),
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[EmployeeRead]:
    items, total = await service.list_employees(
        db,
        section_id=section_id,
        master_section_id=_master_section_id(current_user),
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        q=q,
        is_active=is_active,
    )
    return PaginatedResponse[EmployeeRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/employees/{employee_id}", response_model=EmployeeRead)
async def get_employee(
    employee_id: UUID, current_user: AuthenticatedUser, db: DatabaseSession
) -> EmployeeRead:
    return await service.get_employee(
        db, employee_id, master_section_id=_master_section_id(current_user)
    )


@router.post(
    "/employees",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_employee(
    payload: EmployeeCreate, _: ReferenceCreator, db: DatabaseSession
) -> EmployeeRead:
    return await service.create_employee(db, payload)


@router.patch("/employees/{employee_id}", response_model=EmployeeRead)
async def patch_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    _: ReferenceUpdater,
    db: DatabaseSession,
) -> EmployeeRead:
    return await service.update_employee(db, employee_id, payload)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_employee(
    employee_id: UUID, _: ReferenceDeleter, db: DatabaseSession
) -> Response:
    await service.delete_employee(db, employee_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/work-types", response_model=PaginatedResponse[WorkTypeRead])
async def get_work_types(
    _: AuthenticatedUser,
    db: DatabaseSession,
    unit_type: Literal["locomotive", "wagon"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="sort_order"),
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[WorkTypeRead]:
    items, total = await service.list_work_types(
        db,
        unit_type=unit_type,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        q=q,
    )
    return PaginatedResponse[WorkTypeRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/work-types/{work_type_id}", response_model=WorkTypeRead)
async def get_work_type(
    work_type_id: UUID, _: AuthenticatedUser, db: DatabaseSession
) -> WorkTypeRead:
    return await service.get_work_type(db, work_type_id)


@router.post(
    "/work-types",
    response_model=WorkTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_work_type(
    payload: WorkTypeCreate, _: ReferenceCreator, db: DatabaseSession
) -> WorkTypeRead:
    return await service.create_work_type(db, payload)


@router.patch("/work-types/{work_type_id}", response_model=WorkTypeRead)
async def patch_work_type(
    work_type_id: UUID,
    payload: WorkTypeUpdate,
    _: ReferenceUpdater,
    db: DatabaseSession,
) -> WorkTypeRead:
    return await service.update_work_type(db, work_type_id, payload)


@router.delete("/work-types/{work_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_work_type(
    work_type_id: UUID, _: ReferenceDeleter, db: DatabaseSession
) -> Response:
    await service.delete_work_type(db, work_type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/work-types/{work_type_id}/subtasks",
    response_model=PaginatedResponse[WorkSubtaskRead],
)
async def get_work_subtasks(
    work_type_id: UUID,
    _: AuthenticatedUser,
    db: DatabaseSession,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="sort_order"),
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[WorkSubtaskRead]:
    items, total = await service.list_work_subtasks(
        db,
        work_type_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[WorkSubtaskRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/work-types/{work_type_id}/subtasks/{subtask_id}",
    response_model=WorkSubtaskRead,
)
async def get_work_subtask(
    work_type_id: UUID,
    subtask_id: UUID,
    _: AuthenticatedUser,
    db: DatabaseSession,
) -> WorkSubtaskRead:
    return await service.get_work_subtask(db, work_type_id, subtask_id)


@router.post(
    "/work-types/{work_type_id}/subtasks",
    response_model=WorkSubtaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_work_subtask(
    work_type_id: UUID,
    payload: WorkSubtaskCreate,
    _: ReferenceCreator,
    db: DatabaseSession,
) -> WorkSubtaskRead:
    return await service.create_work_subtask(db, work_type_id, payload)


@router.patch(
    "/work-types/{work_type_id}/subtasks/{subtask_id}",
    response_model=WorkSubtaskRead,
)
async def patch_work_subtask(
    work_type_id: UUID,
    subtask_id: UUID,
    payload: WorkSubtaskUpdate,
    _: ReferenceUpdater,
    db: DatabaseSession,
) -> WorkSubtaskRead:
    return await service.update_work_subtask(
        db, work_type_id, subtask_id, payload
    )


@router.delete(
    "/work-types/{work_type_id}/subtasks/{subtask_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_work_subtask(
    work_type_id: UUID,
    subtask_id: UUID,
    _: ReferenceDeleter,
    db: DatabaseSession,
) -> Response:
    await service.delete_work_subtask(db, work_type_id, subtask_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/work-type-templates",
    response_model=PaginatedResponse[WorkTypeTemplateRead],
)
async def get_work_type_templates(
    _: AuthenticatedUser,
    db: DatabaseSession,
    work_type_id: UUID | None = None,
    work_type: str | None = None,
    department_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["id", "name", "inv_no", "default_quantity", "is_required"] = "id",
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[WorkTypeTemplateRead]:
    items, total = await service.list_work_type_templates(
        db,
        work_type_id=work_type_id,
        work_type_code=work_type,
        department_id=department_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[WorkTypeTemplateRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/work-type-templates/{template_id}", response_model=WorkTypeTemplateRead
)
async def get_work_type_template(
    template_id: UUID, _: AuthenticatedUser, db: DatabaseSession
) -> WorkTypeTemplateRead:
    return await service.get_work_type_template(db, template_id)


@router.post(
    "/work-type-templates",
    response_model=WorkTypeTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_work_type_template(
    payload: WorkTypeTemplateCreate, _: ReferenceCreator, db: DatabaseSession
) -> WorkTypeTemplateRead:
    return await service.create_work_type_template(db, payload)


@router.patch(
    "/work-type-templates/{template_id}", response_model=WorkTypeTemplateRead
)
async def patch_work_type_template(
    template_id: UUID,
    payload: WorkTypeTemplateUpdate,
    _: ReferenceUpdater,
    db: DatabaseSession,
) -> WorkTypeTemplateRead:
    return await service.update_work_type_template(db, template_id, payload)


@router.delete(
    "/work-type-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_work_type_template(
    template_id: UUID, _: ReferenceDeleter, db: DatabaseSession
) -> Response:
    await service.delete_work_type_template(db, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/maintenance-intervals",
    response_model=PaginatedResponse[MaintenanceIntervalRead],
)
async def get_maintenance_intervals(
    _: AuthenticatedUser,
    db: DatabaseSession,
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="interval_km"),
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[MaintenanceIntervalRead]:
    items, total = await service.list_maintenance_intervals(
        db,
        is_active=is_active,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[MaintenanceIntervalRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/maintenance-intervals/{interval_id}",
    response_model=MaintenanceIntervalRead,
)
async def get_maintenance_interval(
    interval_id: UUID, _: AuthenticatedUser, db: DatabaseSession
) -> MaintenanceIntervalRead:
    return await service.get_maintenance_interval(db, interval_id)


@router.post(
    "/maintenance-intervals",
    response_model=MaintenanceIntervalRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_maintenance_interval(
    payload: MaintenanceIntervalCreate, _: ReferenceCreator, db: DatabaseSession
) -> MaintenanceIntervalRead:
    return await service.create_maintenance_interval(db, payload)


@router.patch(
    "/maintenance-intervals/{interval_id}",
    response_model=MaintenanceIntervalRead,
)
async def patch_maintenance_interval(
    interval_id: UUID,
    payload: MaintenanceIntervalUpdate,
    _: ReferenceUpdater,
    db: DatabaseSession,
) -> MaintenanceIntervalRead:
    return await service.update_maintenance_interval(db, interval_id, payload)


@router.delete(
    "/maintenance-intervals/{interval_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_maintenance_interval(
    interval_id: UUID, _: ReferenceDeleter, db: DatabaseSession
) -> Response:
    await service.delete_maintenance_interval(db, interval_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
