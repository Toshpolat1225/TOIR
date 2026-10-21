from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.inventory import Nomenclature, NomenclatureNorm, WorkTypeTemplate
from app.models.localization import SectionTranslation
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


async def _validate_section_hierarchy(
    db: AsyncSession,
    *,
    section_id: UUID | None,
    parent_id: UUID | None,
    unit_type: str,
) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(1936028276)"))
    if unit_type not in {"department", "division", "section", "team"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported unit type",
        )

    if parent_id == section_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Section cannot be its own parent",
        )

    if parent_id is not None:
        parent = await repository.get_record(db, Section, parent_id)
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent section not found",
            )
        if parent.is_archived:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Archived units cannot be assigned as a parent",
            )

        if unit_type == "department":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Department cannot be assigned to a parent unit",
            )

        if unit_type == "division" and parent.unit_type not in {"department", "division"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Division parent must be a department or division",
            )

        if unit_type == "section" and parent.unit_type not in {"department", "division", "section"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Section parent must be a department, division, or section",
            )

        if unit_type == "team" and parent.unit_type not in {"division", "section", "team"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Team parent must be a division, section, or team",
            )

        cursor_id = parent_id
        seen: set[UUID] = set()
        while cursor_id is not None:
            if cursor_id in seen:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Existing parent cycle detected",
                )
            seen.add(cursor_id)
            current = await repository.get_record(db, Section, cursor_id)
            if current is None:
                break
            if section_id is not None and current.id == section_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Parent cycle detected",
                )
            cursor_id = current.parent_id

    if section_id is not None:
        children = await repository.list_all_sections(db)
        invalid_child = next(
            (
                child
                for child in children
                if child.parent_id == section_id
                and not _is_valid_section_parent(child.unit_type, unit_type)
            ),
            None,
        )
        if invalid_child is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Changing this unit would invalidate a child relationship",
            )


def _is_valid_section_parent(child_type: str, parent_type: str) -> bool:
    allowed_parents = {
        "division": {"department", "division"},
        "section": {"department", "division", "section"},
        "team": {"division", "section", "team"},
    }
    return parent_type in allowed_parents.get(child_type, set())


async def _attach_section_translations(
    db: AsyncSession, sections: list[Section]
) -> None:
    translations = await repository.get_section_translations(
        db, {section.id for section in sections}
    )
    for section in sections:
        section.translations = translations.get(section.id, {})

async def list_sections(
    db: AsyncSession,
    *,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
    q: str | None = None,
    parent_id: UUID | None = None,
    include_archived: bool = False,
    unit_type: str | None = None,
    is_active: bool | None = None,
    department_id: UUID | None = None,
) -> tuple[list[Section], int]:
    try:
        items, total = await repository.list_sections(
            db,
            master_section_id=master_section_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            q=q,
            parent_id=parent_id,
            include_archived=include_archived,
            unit_type=unit_type,
            is_active=is_active,
            department_id=department_id,
        )
        await _attach_section_translations(db, items)
        return items, total
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
    await _attach_section_translations(db, [section])
    return section


async def list_section_tree(
    db: AsyncSession,
    *,
    parent_id: UUID | None = None,
    include_archived: bool = False,
    master_section_id: UUID | None = None,
    q: str | None = None,
    unit_type: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    rows = await repository.list_all_sections(
        db,
        include_archived=include_archived,
        master_section_id=master_section_id,
    )
    await _attach_section_translations(db, rows)
    dict_by_id: dict[UUID, dict[str, Any]] = {}
    children_by_parent: dict[UUID | None, list[dict[str, Any]]] = {}
    for row in rows:
        node = {
            "id": row.id,
            "name": row.name,
            "department_id": row.department_id,
            "parent_id": row.parent_id,
            "unit_type": row.unit_type,
            "code": row.code,
            "translations": row.translations,
            "is_active": row.is_active,
            "is_archived": row.is_archived,
            "sort_order": row.sort_order,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "children": [],
        }
        dict_by_id[row.id] = node
        children_by_parent.setdefault(row.parent_id, []).append(node)

    def build(node: dict[str, Any], seen: set[UUID]) -> dict[str, Any]:
        node_id = node["id"]
        if node_id in seen:
            return node
        next_seen = {*seen, node_id}
        node["children"] = [
            build(child, next_seen)
            for child in children_by_parent.get(node_id, [])
        ]
        return node

    if master_section_id is not None:
        roots = [dict_by_id[master_section_id]] if master_section_id in dict_by_id else []
    elif parent_id is not None:
        roots = children_by_parent.get(parent_id, [])
    else:
        roots = children_by_parent.get(None, [])
    tree = [build(root, set()) for root in roots]

    def matches_query(node: dict[str, Any]) -> bool:
        return not q or q.casefold() in node["name"].casefold() or any(
            q.casefold() in name.casefold()
            for name in node["translations"].values()
        )

    def prune(
        nodes: list[dict[str, Any]], ancestor_matches_query: bool = False
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for node in nodes:
            node_matches_query = matches_query(node)
            matching_children = prune(
                node["children"],
                ancestor_matches_query or node_matches_query,
            )
            matches = (
                (not q or node_matches_query or ancestor_matches_query)
                and (unit_type is None or node["unit_type"] == unit_type)
                and (is_active is None or node["is_active"] is is_active)
            )
            if matches or matching_children:
                result.append(
                    {
                        **node,
                        "children": (
                            node["children"]
                            if node_matches_query and unit_type is None and is_active is None
                            else matching_children
                        ),
                    }
                )
        return result

    return prune(tree) if q or unit_type is not None or is_active is not None else tree


async def _save_section_translations(
    db: AsyncSession,
    section: Section,
    translations: dict[str, str] | None,
) -> None:
    if translations is None:
        section.translations = {}
        return
    await db.execute(
        delete(SectionTranslation).where(
            SectionTranslation.section_id == section.id
        )
    )
    db.add_all(
        SectionTranslation(
            section_id=section.id,
            locale=locale,
            name=name,
        )
        for locale, name in translations.items()
    )
    section.translations = translations


async def create_section(db: AsyncSession, payload: SectionCreate) -> Section:
    await _validate_section_hierarchy(
        db,
        section_id=None,
        parent_id=payload.parent_id,
        unit_type=payload.unit_type,
    )
    section_data = payload.model_dump(exclude={"translations"})
    section = Section(**section_data)
    db.add(section)
    await db.flush()
    await _save_section_translations(db, section, payload.translations)
    await _commit_or_conflict(db, "Section name already exists or the hierarchy is invalid")
    await db.refresh(section)
    return section


async def update_section(
    db: AsyncSession, section_id: UUID, payload: SectionUpdate
) -> Section:
    section = await get_section(db, section_id, master_section_id=None)
    update_data = payload.model_dump(exclude_unset=True)
    translations = update_data.pop("translations", None)
    if translations is not None:
        update_data["name"] = translations["ru"]
    parent_id = update_data.get("parent_id", section.parent_id)
    unit_type = update_data.get("unit_type", section.unit_type)
    await _validate_section_hierarchy(
        db,
        section_id=section_id,
        parent_id=parent_id,
        unit_type=unit_type,
    )
    for field_name, value in update_data.items():
        setattr(section, field_name, value)
    if translations is not None:
        await _save_section_translations(db, section, translations)
    elif "name" in update_data:
        russian_translation = (
            await db.execute(
                select(SectionTranslation).where(
                    SectionTranslation.section_id == section.id,
                    SectionTranslation.locale == "ru",
                )
            )
        ).scalar_one_or_none()
        if russian_translation is not None:
            russian_translation.name = update_data["name"]
    section.updated_at = datetime.now(timezone.utc)
    await _commit_or_conflict(db, "Section name already exists or the hierarchy is invalid")
    await db.refresh(section)
    return section


async def delete_section(db: AsyncSession, section_id: UUID) -> None:
    section = await get_section(db, section_id, master_section_id=None)
    if section.is_archived:
        return
    if await repository.has_active_children(db, section.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Move or archive child units before archiving this unit",
        )
    section.is_archived = True
    await _commit_or_conflict(db, "Section could not be archived")


async def list_employees(
    db: AsyncSession,
    *,
    section_id: UUID | None,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
    q: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[Employee], int]:
    try:
        return await repository.list_employees(
            db,
            section_id=section_id,
            master_section_id=master_section_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            q=q,
            is_active=is_active,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc


async def get_employee(
    db: AsyncSession,
    employee_id: UUID,
    *,
    master_section_id: UUID | None = None,
) -> Employee:
    employee = await repository.get_employee(
        db, employee_id, master_section_id=master_section_id
    )
    if employee is None:
        raise _http_not_found("Employee")
    return employee


async def create_employee(db: AsyncSession, payload: EmployeeCreate) -> Employee:
    if payload.section_id is not None and await repository.get_non_archived_section(
        db, payload.section_id
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot assign an archived or missing section to an employee",
        )
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
    changes = payload.model_dump(exclude_unset=True)
    section_id = changes.get("section_id")
    if section_id is not None and section_id != employee.section_id:
        if await repository.get_non_archived_section(db, section_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot assign an archived or missing section to an employee",
            )
    for field_name, value in changes.items():
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
    q: str | None = None,
) -> tuple[list[WorkTypeRead], int]:
    try:
        rows, total = await repository.list_work_types(
            db,
            unit_type=unit_type,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            q=q,
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
