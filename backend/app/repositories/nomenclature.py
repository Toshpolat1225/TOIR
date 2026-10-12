from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Nomenclature, NomenclatureNorm
from app.models.maintenance import WorkType
from app.models.organization import Department, Section
from app.models.work_orders import WorkOrderItem

NOMENCLATURE_SORT_FIELDS = frozenset(
    {"name", "code", "unit", "department_id", "created_at", "updated_at"}
)
NORM_SORT_FIELDS = frozenset(
    {
        "standard_quantity",
        "avg_price",
        "min_quantity",
        "max_quantity",
        "department_id",
        "nomenclature_id",
        "work_type_id",
        "created_at",
        "updated_at",
    }
)


def _nomenclature_master_filter(section_id: UUID | None) -> Any:
    return Nomenclature.department_id.in_(
        select(Section.department_id).where(
            Section.id == section_id,
            Section.department_id.is_not(None),
        )
    )


def _norm_master_filter(section_id: UUID | None) -> Any:
    return NomenclatureNorm.department_id.in_(
        select(Section.department_id).where(
            Section.id == section_id,
            Section.department_id.is_not(None),
        )
    )


async def list_nomenclature(
    db: AsyncSession,
    *,
    department_id: UUID | None,
    q: str | None,
    master_only: bool,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[tuple[Nomenclature, str]], int]:
    if sort_by not in NOMENCLATURE_SORT_FIELDS:
        raise ValueError("Unsupported sort field")

    filters: list[Any] = []
    if department_id is not None:
        filters.append(Nomenclature.department_id == department_id)
    if q:
        search = "%" + q.strip() + "%"
        filters.append(
            or_(
                Nomenclature.name.ilike(search),
                Nomenclature.code.ilike(search),
            )
        )
    if master_only:
        filters.append(_nomenclature_master_filter(master_section_id))

    count_query = select(func.count()).select_from(Nomenclature)
    rows_query: Select[Any] = (
        select(Nomenclature, Department.name)
        .join(Department, Department.id == Nomenclature.department_id)
    )
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()
    sort_column = getattr(Nomenclature, sort_by)
    order_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    rows = await db.execute(
        rows_query.order_by(order_column, Nomenclature.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all()), total


async def get_nomenclature_read(
    db: AsyncSession,
    nomenclature_id: UUID,
    *,
    master_only: bool,
    master_section_id: UUID | None,
) -> tuple[Nomenclature, str] | None:
    filters: list[Any] = [Nomenclature.id == nomenclature_id]
    if master_only:
        filters.append(_nomenclature_master_filter(master_section_id))
    result = await db.execute(
        select(Nomenclature, Department.name)
        .join(Department, Department.id == Nomenclature.department_id)
        .where(*filters)
    )
    return result.one_or_none()


async def get_nomenclature(
    db: AsyncSession, nomenclature_id: UUID
) -> Nomenclature | None:
    result = await db.execute(
        select(Nomenclature)
        .where(Nomenclature.id == nomenclature_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def count_work_order_items(
    db: AsyncSession, nomenclature_id: UUID
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(WorkOrderItem)
        .where(WorkOrderItem.nomenclature_id == nomenclature_id)
    )
    return result.scalar_one()


async def list_norms(
    db: AsyncSession,
    *,
    department_id: UUID | None,
    work_type_id: UUID | None,
    nomenclature_id: UUID | None,
    master_only: bool,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[tuple[NomenclatureNorm, str, str | None, str, str]], int]:
    if sort_by not in NORM_SORT_FIELDS:
        raise ValueError("Unsupported sort field")

    filters: list[Any] = []
    if department_id is not None:
        filters.append(NomenclatureNorm.department_id == department_id)
    if work_type_id is not None:
        filters.append(NomenclatureNorm.work_type_id == work_type_id)
    if nomenclature_id is not None:
        filters.append(NomenclatureNorm.nomenclature_id == nomenclature_id)
    if master_only:
        filters.append(_norm_master_filter(master_section_id))

    count_query = select(func.count()).select_from(NomenclatureNorm)
    rows_query: Select[Any] = (
        select(
            NomenclatureNorm,
            Nomenclature.name,
            Nomenclature.code,
            Nomenclature.unit,
            WorkType.code,
        )
        .join(Nomenclature, Nomenclature.id == NomenclatureNorm.nomenclature_id)
        .join(WorkType, WorkType.id == NomenclatureNorm.work_type_id)
    )
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()
    sort_column = getattr(NomenclatureNorm, sort_by)
    order_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    rows = await db.execute(
        rows_query.order_by(order_column, NomenclatureNorm.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all()), total


async def get_norm_read(
    db: AsyncSession,
    norm_id: UUID,
    *,
    master_only: bool,
    master_section_id: UUID | None,
) -> tuple[NomenclatureNorm, str, str | None, str, str] | None:
    filters: list[Any] = [NomenclatureNorm.id == norm_id]
    if master_only:
        filters.append(_norm_master_filter(master_section_id))
    result = await db.execute(
        select(
            NomenclatureNorm,
            Nomenclature.name,
            Nomenclature.code,
            Nomenclature.unit,
            WorkType.code,
        )
        .join(Nomenclature, Nomenclature.id == NomenclatureNorm.nomenclature_id)
        .join(WorkType, WorkType.id == NomenclatureNorm.work_type_id)
        .where(*filters)
    )
    return result.one_or_none()


async def get_norm(db: AsyncSession, norm_id: UUID) -> NomenclatureNorm | None:
    result = await db.execute(
        select(NomenclatureNorm).where(NomenclatureNorm.id == norm_id)
    )
    return result.scalar_one_or_none()
