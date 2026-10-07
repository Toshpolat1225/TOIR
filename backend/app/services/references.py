from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.inventory import Nomenclature, NomenclatureNorm, WorkTypeTemplate
from app.models.maintenance import MaintenanceInterval, MaintenancePlan, WorkSubtask, WorkType
from app.models.organization import Department, Employee, Section
from app.models.work_orders import WorkOrder, WorkOrderRepair
from app.repositories import references as repository
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
    TemplateNomenclatureRead,
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


def _http_not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )


def _unsupported_sort() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Unsupported sort field",
    )


async def _commit_or_conflict(db: AsyncSession, detail: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc


async def _ensure_unreferenced(
    db: AsyncSession,
    record_id: UUID,
    references: list[tuple[type[Any], str]],
    resource: str,
) -> None:
    for model, field_name in references:
        if await repository.count_references(db, model, field_name, record_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete {resource}: it is referenced by existing records",
            )


async def _delete(
    db: AsyncSession,
    record: Any,
    *,
    resource: str,
    references: list[tuple[type[Any], str]],
) -> None:
    await _ensure_unreferenced(db, record.id, references, resource)
    await db.delete(record)
    await _commit_or_conflict(
        db,
        f"Cannot delete {resource}: it is referenced by existing records",
    )


async def list_departments(
    db: AsyncSession, *, limit: int, offset: int, sort_by: str, sort_order: str
) -> tuple[list[Department], int]:
    try:
        return await repository.list_page(
            db,
            Department,
            filters=[],
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc


async def get_department(db: AsyncSession, department_id: UUID) -> Department:
    department = await repository.get_record(db, Department, department_id)
    if department is None:
        raise _http_not_found("Department")
    return department


async def create_department(db: AsyncSession, payload: DepartmentCreate) -> Department:
    department = Department(**payload.model_dump())
    db.add(department)
    await _commit_or_conflict(db, "Department name already exists or the request conflicts with related data")
    await db.refresh(department)
    return department


async def update_department(
    db: AsyncSession, department_id: UUID, payload: DepartmentUpdate
) -> Department:
    department = await get_department(db, department_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(department, field_name, value)
    await _commit_or_conflict(db, "Department name already exists or the request conflicts with related data")
    await db.refresh(department)
    return department


async def delete_department(db: AsyncSession, department_id: UUID) -> None:
    department = await get_department(db, department_id)
    await _delete(
        db,
        department,
        resource="department",
        references=[
            (Section, "department_id"),
            (Nomenclature, "department_id"),
            (NomenclatureNorm, "department_id"),
            (WorkTypeTemplate, "department_id"),
            (WorkOrder, "department_id"),
        ],
    )


async def list_sections(
    db: AsyncSession,
    *,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[Section], int]:
    try:
        return await repository.list_sections(
            db,
            master_section_id=master_section_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc


async def get_section(
    db: AsyncSession, section_id: UUID, *, master_section_id: UUID | None
) -> Section:
    section = await repository.get_section(
        db, section_id, master_section_id=master_section_id
    )
    if section is None:
        raise _http_not_found("Section")
    return section


async def create_section(db: AsyncSession, payload: SectionCreate) -> Section:
    section = Section(**payload.model_dump())
    db.add(section)
    await _commit_or_conflict(db, "Section name already exists or the department does not exist")
    await db.refresh(section)
    return section


async def update_section(
    db: AsyncSession, section_id: UUID, payload: SectionUpdate
) -> Section:
    section = await get_section(db, section_id, master_section_id=None)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(section, field_name, value)
    await _commit_or_conflict(db, "Section name already exists or the department does not exist")
    await db.refresh(section)
    return section


async def delete_section(db: AsyncSession, section_id: UUID) -> None:
    section = await get_section(db, section_id, master_section_id=None)
    await _delete(
        db,
        section,
        resource="section",
        references=[
            (User, "section_id"),
            (Employee, "section_id"),
            (FixedAsset, "section_id"),
            (WorkOrder, "section_id"),
        ],
    )


async def list_employees(
    db: AsyncSession,
    *,
    section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[Employee], int]:
    try:
        return await repository.list_employees(
            db,
            section_id=section_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc


async def get_employee(db: AsyncSession, employee_id: UUID) -> Employee:
    employee = await repository.get_record(db, Employee, employee_id)
    if employee is None:
        raise _http_not_found("Employee")
    return employee


async def create_employee(db: AsyncSession, payload: EmployeeCreate) -> Employee:
    employee = Employee(**payload.model_dump())
    db.add(employee)
    await _commit_or_conflict(
        db,
        "Employee tab number already exists or the assigned section is invalid",
    )
    await db.refresh(employee)
    return employee


async def update_employee(
    db: AsyncSession, employee_id: UUID, payload: EmployeeUpdate
) -> Employee:
    employee = await get_employee(db, employee_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(employee, field_name, value)
    await _commit_or_conflict(
        db,
        "Employee tab number already exists or the assigned section is invalid",
    )
    await db.refresh(employee)
    return employee


async def delete_employee(db: AsyncSession, employee_id: UUID) -> None:
    employee = await get_employee(db, employee_id)
    await _delete(
        db,
        employee,
        resource="employee",
        references=[
            (WorkOrder, "executor_id"),
            (WorkOrder, "chief_id"),
        ],
    )


def _work_type_read(
    work_type: WorkType, subtasks: list[WorkSubtask]
) -> WorkTypeRead:
    result = WorkTypeRead.model_validate(work_type)
    return result.model_copy(
        update={
            "subtasks": [WorkSubtaskRead.model_validate(subtask) for subtask in subtasks]
        }
    )


async def list_work_types(
    db: AsyncSession,
    *,
    unit_type: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[WorkTypeRead], int]:
    try:
        rows, total = await repository.list_work_types(
            db,
            unit_type=unit_type,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc
    return [_work_type_read(work_type, subtasks) for work_type, subtasks in rows], total


async def get_work_type(db: AsyncSession, work_type_id: UUID) -> WorkTypeRead:
    result = await repository.get_work_type(db, work_type_id)
    if result is None:
        raise _http_not_found("Work type")
    return _work_type_read(*result)


async def create_work_type(db: AsyncSession, payload: WorkTypeCreate) -> WorkTypeRead:
    work_type = WorkType(**payload.model_dump())
    db.add(work_type)
    await _commit_or_conflict(db, "Work type code already exists")
    await db.refresh(work_type)
    return await get_work_type(db, work_type.id)


async def update_work_type(
    db: AsyncSession, work_type_id: UUID, payload: WorkTypeUpdate
) -> WorkTypeRead:
    work_type = await repository.get_record(db, WorkType, work_type_id)
    if work_type is None:
        raise _http_not_found("Work type")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(work_type, field_name, value)
    await _commit_or_conflict(db, "Work type code already exists")
    return await get_work_type(db, work_type_id)


async def delete_work_type(db: AsyncSession, work_type_id: UUID) -> None:
    work_type = await repository.get_record(db, WorkType, work_type_id)
    if work_type is None:
        raise _http_not_found("Work type")
    await _delete(
        db,
        work_type,
        resource="work type",
        references=[
            (WorkSubtask, "work_type_id"),
            (MaintenanceInterval, "work_type_id"),
            (NomenclatureNorm, "work_type_id"),
            (WorkTypeTemplate, "work_type_id"),
            (WorkOrderRepair, "work_type_id"),
        ],
    )


async def list_work_subtasks(
    db: AsyncSession,
    work_type_id: UUID,
    *,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[WorkSubtask], int]:
    if await repository.get_record(db, WorkType, work_type_id) is None:
        raise _http_not_found("Work type")
    try:
        return await repository.list_subtasks(
            db,
            work_type_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc


async def get_work_subtask(
    db: AsyncSession, work_type_id: UUID, subtask_id: UUID
) -> WorkSubtask:
    subtask = await repository.get_subtask(db, work_type_id, subtask_id)
    if subtask is None:
        raise _http_not_found("Work subtask")
    return subtask


async def create_work_subtask(
    db: AsyncSession, work_type_id: UUID, payload: WorkSubtaskCreate
) -> WorkSubtask:
    if await repository.get_record(db, WorkType, work_type_id) is None:
        raise _http_not_found("Work type")
    subtask = WorkSubtask(work_type_id=work_type_id, **payload.model_dump())
    db.add(subtask)
    await _commit_or_conflict(db, "Could not create work subtask")
    await db.refresh(subtask)
    return subtask


async def update_work_subtask(
    db: AsyncSession,
    work_type_id: UUID,
    subtask_id: UUID,
    payload: WorkSubtaskUpdate,
) -> WorkSubtask:
    subtask = await get_work_subtask(db, work_type_id, subtask_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(subtask, field_name, value)
    await _commit_or_conflict(db, "Could not update work subtask")
    await db.refresh(subtask)
    return subtask


async def delete_work_subtask(
    db: AsyncSession, work_type_id: UUID, subtask_id: UUID
) -> None:
    subtask = await get_work_subtask(db, work_type_id, subtask_id)
    await _delete(db, subtask, resource="work subtask", references=[])


def _template_read(
    template: WorkTypeTemplate,
    work_type_code: str,
    nomenclature: Nomenclature | None,
) -> WorkTypeTemplateRead:
    return WorkTypeTemplateRead(
        id=template.id,
        work_type_id=template.work_type_id,
        work_type=work_type_code,
        department_id=template.department_id,
        nomenclature_id=template.nomenclature_id,
        name=template.name,
        inv_no=template.inv_no,
        unit=template.unit,
        default_quantity=template.default_quantity,
        is_required=template.is_required,
        note=template.note,
        nomenclature=(
            TemplateNomenclatureRead.model_validate(nomenclature)
            if nomenclature is not None
            else None
        ),
    )


async def list_work_type_templates(
    db: AsyncSession,
    *,
    work_type_id: UUID | None,
    work_type_code: str | None,
    department_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[WorkTypeTemplateRead], int]:
    try:
        rows, total = await repository.list_work_type_templates(
            db,
            work_type_id=work_type_id,
            work_type_code=work_type_code,
            department_id=department_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc
    return [
        _template_read(template, code, nomenclature)
        for template, code, nomenclature in rows
    ], total


async def get_work_type_template(
    db: AsyncSession, template_id: UUID
) -> WorkTypeTemplateRead:
    row = await repository.get_work_type_template(db, template_id)
    if row is None:
        raise _http_not_found("Work type template")
    return _template_read(*row)


async def create_work_type_template(
    db: AsyncSession, payload: WorkTypeTemplateCreate
) -> WorkTypeTemplateRead:
    template = WorkTypeTemplate(**payload.model_dump())
    db.add(template)
    await _commit_or_conflict(
        db,
        "Could not create template; verify the work type, department, and nomenclature",
    )
    await db.refresh(template)
    return await get_work_type_template(db, template.id)


async def update_work_type_template(
    db: AsyncSession, template_id: UUID, payload: WorkTypeTemplateUpdate
) -> WorkTypeTemplateRead:
    template = await repository.get_record(db, WorkTypeTemplate, template_id)
    if template is None:
        raise _http_not_found("Work type template")
    changes = payload.model_dump(exclude_unset=True)
    effective_name = changes.get("name", template.name)
    effective_nomenclature_id = changes.get(
        "nomenclature_id", template.nomenclature_id
    )
    if effective_nomenclature_id is None and not effective_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide nomenclature_id or a template name",
        )
    for field_name, value in changes.items():
        setattr(template, field_name, value)
    await _commit_or_conflict(
        db,
        "Could not update template; verify the department and nomenclature",
    )
    return await get_work_type_template(db, template_id)


async def delete_work_type_template(db: AsyncSession, template_id: UUID) -> None:
    template = await repository.get_record(db, WorkTypeTemplate, template_id)
    if template is None:
        raise _http_not_found("Work type template")
    await _delete(db, template, resource="work type template", references=[])


async def list_maintenance_intervals(
    db: AsyncSession,
    *,
    is_active: bool | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[MaintenanceInterval], int]:
    try:
        return await repository.list_maintenance_intervals(
            db,
            is_active=is_active,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc


async def get_maintenance_interval(
    db: AsyncSession, interval_id: UUID
) -> MaintenanceInterval:
    interval = await repository.get_record(db, MaintenanceInterval, interval_id)
    if interval is None:
        raise _http_not_found("Maintenance interval")
    return interval


async def create_maintenance_interval(
    db: AsyncSession, payload: MaintenanceIntervalCreate
) -> MaintenanceInterval:
    interval = MaintenanceInterval(**payload.model_dump())
    db.add(interval)
    await _commit_or_conflict(
        db,
        "Maintenance interval code already exists or the selected work type is invalid",
    )
    await db.refresh(interval)
    return interval


async def update_maintenance_interval(
    db: AsyncSession,
    interval_id: UUID,
    payload: MaintenanceIntervalUpdate,
) -> MaintenanceInterval:
    interval = await get_maintenance_interval(db, interval_id)
    changes = payload.model_dump(exclude_unset=True)
    next_km = changes.get("interval_km", interval.interval_km)
    next_days = changes.get("interval_days", interval.interval_days)
    if next_km is None and next_days is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of interval_km or interval_days is required",
        )
    for field_name, value in changes.items():
        setattr(interval, field_name, value)
    await _commit_or_conflict(
        db,
        "Maintenance interval code already exists or the selected work type is invalid",
    )
    await db.refresh(interval)
    return interval


async def delete_maintenance_interval(
    db: AsyncSession, interval_id: UUID
) -> None:
    interval = await get_maintenance_interval(db, interval_id)
    await _delete(
        db,
        interval,
        resource="maintenance interval",
        references=[(MaintenancePlan, "interval_id")],
    )
