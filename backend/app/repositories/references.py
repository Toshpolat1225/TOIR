from collections import defaultdict
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.inventory import Nomenclature, NomenclatureNorm, WorkTypeTemplate
from app.models.maintenance import (
    MaintenanceInterval,
    MaintenancePlan,
    WorkSubtask,
    WorkType,
)
from app.models.organization import Department, Employee, Section
from app.models.work_orders import WorkOrder, WorkOrderRepair
from app.models.identity import User

SORT_FIELDS = {
    Department: frozenset({"name", "color", "created_at", "updated_at"}),
    Section: frozenset({"name", "department_id", "created_at", "updated_at"}),
    Employee: frozenset(
        {"tab_number", "full_name", "position", "section_id", "created_at", "updated_at"}
    ),
    WorkType: frozenset({"code", "name", "unit_type", "sort_order", "created_at", "updated_at"}),
    MaintenanceInterval: frozenset(
        {
            "code",
            "name",
            "work_type_id",
            "interval_km",
            "interval_days",
            "is_active",
            "created_at",
            "updated_at",
        }
    ),
    WorkSubtask: frozenset({"name", "sort_order"}),
}


async def list_page(
    db: AsyncSession,
    model: type[Any],
    *,
    filters: Sequence[Any],
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[Any], int]:
    allowed_fields = SORT_FIELDS[model]
    if sort_by not in allowed_fields:
        raise ValueError("Unsupported sort field")
    sort_column = getattr(model, sort_by)
    order_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    count_query = select(func.count()).select_from(model)
    rows_query: Select[Any] = select(model)
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()
    rows_result = await db.execute(
        rows_query.order_by(order_column, model.id.asc()).limit(limit).offset(offset)
    )
    return list(rows_result.scalars().all()), total


async def get_record(db: AsyncSession, model: type[Any], record_id: UUID) -> Any | None:
    result = await db.execute(select(model).where(model.id == record_id))
    return result.scalar_one_or_none()


async def count_references(
    db: AsyncSession, model: type[Any], column_name: str, record_id: UUID
) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(getattr(model, column_name) == record_id)
    )
    return result.scalar_one()


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
) -> tuple[list[Section], int]:
    filters: list[Any] = []
    if master_section_id is not None:
        filters.append(Section.id == master_section_id)
    if parent_id is not None:
        filters.append(Section.parent_id == parent_id)
    elif master_section_id is None:
        filters.append(Section.parent_id.is_(None))
    if not include_archived:
        filters.append(Section.is_archived.is_(False))
    if q and q.strip():
        filters.append(Section.name.ilike(f"%{q.strip()}%"))
    return await list_page(
        db,
        Section,
        filters=filters,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


async def get_section(
    db: AsyncSession, section_id: UUID, *, master_section_id: UUID | None
) -> Section | None:
    filters = [Section.id == section_id]
    if master_section_id is not None:
        filters.append(Section.id == master_section_id)
    result = await db.execute(select(Section).where(*filters))
    return result.scalar_one_or_none()


async def list_section_tree(
    db: AsyncSession,
    *,
    parent_id: UUID | None = None,
    include_archived: bool = False,
) -> list[Section]:
    filters: list[Any] = []
    if parent_id is None:
        filters.append(Section.parent_id.is_(None))
    else:
        filters.append(Section.parent_id == parent_id)
    if not include_archived:
        filters.append(Section.is_archived.is_(False))
    result = await db.execute(
        select(Section)
        .where(*filters)
        .order_by(Section.sort_order.asc(), Section.name.asc())
    )
    return list(result.scalars().all())


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
    scoped_section_id = (
        master_section_id if master_section_id is not None else section_id
    )
    filters = (
        [Employee.section_id == scoped_section_id]
        if scoped_section_id is not None
        else []
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(or_(
            Employee.tab_number.ilike(pattern), Employee.full_name.ilike(pattern),
            Employee.position.ilike(pattern),
            select(Section.id).where(Section.id == Employee.section_id, Section.name.ilike(pattern)).exists(),
        ))
    if is_active is not None:
        filters.append(Employee.is_active.is_(is_active))
    return await list_page(
        db,
        Employee,
        filters=filters,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


async def get_employee(
    db: AsyncSession,
    employee_id: UUID,
    *,
    master_section_id: UUID | None,
) -> Employee | None:
    filters = [Employee.id == employee_id]
    if master_section_id is not None:
        filters.append(Employee.section_id == master_section_id)
    result = await db.execute(select(Employee).where(*filters))
    return result.scalar_one_or_none()


async def list_work_types(
    db: AsyncSession,
    *,
    unit_type: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
    q: str | None = None,
) -> tuple[list[tuple[WorkType, list[WorkSubtask]]], int]:
    filters = [WorkType.unit_type == unit_type] if unit_type is not None else []
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(or_(WorkType.code.ilike(pattern), WorkType.name.ilike(pattern)))
    work_types, total = await list_page(
        db,
        WorkType,
        filters=filters,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    if not work_types:
        return [], total
    subtasks_result = await db.execute(
        select(WorkSubtask)
        .where(WorkSubtask.work_type_id.in_([work_type.id for work_type in work_types]))
        .order_by(WorkSubtask.sort_order.asc(), WorkSubtask.id.asc())
    )
    grouped: dict[UUID, list[WorkSubtask]] = defaultdict(list)
    for subtask in subtasks_result.scalars().all():
        grouped[subtask.work_type_id].append(subtask)
    return [(work_type, grouped[work_type.id]) for work_type in work_types], total


async def get_work_type(
    db: AsyncSession, work_type_id: UUID
) -> tuple[WorkType, list[WorkSubtask]] | None:
    work_type = await get_record(db, WorkType, work_type_id)
    if work_type is None:
        return None
    subtasks_result = await db.execute(
        select(WorkSubtask)
        .where(WorkSubtask.work_type_id == work_type_id)
        .order_by(WorkSubtask.sort_order.asc(), WorkSubtask.id.asc())
    )
    return work_type, list(subtasks_result.scalars().all())


async def list_subtasks(
    db: AsyncSession,
    work_type_id: UUID,
    *,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[WorkSubtask], int]:
    return await list_page(
        db,
        WorkSubtask,
        filters=[WorkSubtask.work_type_id == work_type_id],
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


async def get_subtask(
    db: AsyncSession, work_type_id: UUID, subtask_id: UUID
) -> WorkSubtask | None:
    result = await db.execute(
        select(WorkSubtask).where(
            WorkSubtask.id == subtask_id,
            WorkSubtask.work_type_id == work_type_id,
        )
    )
    return result.scalar_one_or_none()


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
) -> tuple[list[tuple[WorkTypeTemplate, str, Nomenclature | None]], int]:
    template_sort_fields = frozenset(
        {"id", "name", "inv_no", "default_quantity", "is_required"}
    )
    if sort_by not in template_sort_fields:
        raise ValueError("Unsupported sort field")
    sort_column = getattr(WorkTypeTemplate, sort_by)
    order_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    query = (
        select(WorkTypeTemplate, WorkType.code, Nomenclature)
        .join(WorkType, WorkType.id == WorkTypeTemplate.work_type_id)
        .outerjoin(Nomenclature, Nomenclature.id == WorkTypeTemplate.nomenclature_id)
    )
    count_query = select(func.count()).select_from(WorkTypeTemplate).join(
        WorkType, WorkType.id == WorkTypeTemplate.work_type_id
    )
    filters = []
    if work_type_id is not None:
        filters.append(WorkTypeTemplate.work_type_id == work_type_id)
    if work_type_code is not None:
        filters.append(WorkType.code == work_type_code)
    if department_id is not None:
        filters.append(WorkTypeTemplate.department_id == department_id)
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()
    rows_result = await db.execute(
        query.order_by(order_column, WorkTypeTemplate.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows_result.all()), total


async def get_work_type_template(
    db: AsyncSession, template_id: UUID
) -> tuple[WorkTypeTemplate, str, Nomenclature | None] | None:
    result = await db.execute(
        select(WorkTypeTemplate, WorkType.code, Nomenclature)
        .join(WorkType, WorkType.id == WorkTypeTemplate.work_type_id)
        .outerjoin(Nomenclature, Nomenclature.id == WorkTypeTemplate.nomenclature_id)
        .where(WorkTypeTemplate.id == template_id)
    )
    return result.one_or_none()


async def list_maintenance_intervals(
    db: AsyncSession,
    *,
    is_active: bool | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[MaintenanceInterval], int]:
    filters = (
        [MaintenanceInterval.is_active == is_active] if is_active is not None else []
    )
    return await list_page(
        db,
        MaintenanceInterval,
        filters=filters,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
