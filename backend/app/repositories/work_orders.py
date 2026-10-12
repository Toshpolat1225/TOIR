from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.inventory import Nomenclature, NomenclatureNorm, WorkTypeTemplate
from app.models.maintenance import WorkType
from app.models.organization import Employee, Section
from app.models.work_orders import WorkOrder, WorkOrderItem, WorkOrderRepair

SORT_FIELDS = frozenset(
    {"created_at", "updated_at", "date_start", "date_end", "status", "priority"}
)


async def get_asset(db: AsyncSession, asset_id: UUID, *, lock: bool = False) -> FixedAsset | None:
    statement = select(FixedAsset).where(FixedAsset.id == asset_id)
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def get_section(db: AsyncSession, section_id: UUID) -> Section | None:
    return (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()


async def get_order(db: AsyncSession, order_id: UUID, *, lock: bool = False) -> WorkOrder | None:
    statement = select(WorkOrder).where(WorkOrder.id == order_id)
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


def _order_rows_statement():
    return (
        select(
            WorkOrder,
            FixedAsset.name.label("asset_name"),
            FixedAsset.inv_number.label("asset_inv_number"),
            Employee.full_name.label("executor_name"),
            Section.name.label("section_name"),
        )
        .join(FixedAsset, FixedAsset.id == WorkOrder.fixed_asset_id)
        .join(Section, Section.id == WorkOrder.section_id)
        .outerjoin(Employee, Employee.id == WorkOrder.executor_id)
    )


async def list_orders(
    db: AsyncSession,
    *,
    statuses: list[str] | None,
    section_id: UUID | None,
    department_id: UUID | None,
    fixed_asset_id: UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    q: str | None,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[dict[str, Any]], int]:
    if sort_by not in SORT_FIELDS:
        raise ValueError("Unsupported sort field")
    filters: list[Any] = []
    if statuses:
        filters.append(WorkOrder.status.in_(statuses))
    if section_id is not None:
        filters.append(WorkOrder.section_id == section_id)
    if department_id is not None:
        filters.append(WorkOrder.department_id == department_id)
    if fixed_asset_id is not None:
        filters.append(WorkOrder.fixed_asset_id == fixed_asset_id)
    if date_from is not None:
        filters.append(WorkOrder.date_start >= date_from)
    if date_to is not None:
        filters.append(WorkOrder.date_start <= date_to)
    if master_section_id is not None:
        filters.append(WorkOrder.section_id == master_section_id)
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                WorkOrder.number.ilike(term),
                WorkOrder.description.ilike(term),
                FixedAsset.name.ilike(term),
            )
        )

    count_query = select(func.count()).select_from(WorkOrder).join(
        FixedAsset, FixedAsset.id == WorkOrder.fixed_asset_id
    )
    row_query: Select[Any] = _order_rows_statement()
    if filters:
        count_query = count_query.where(*filters)
        row_query = row_query.where(*filters)
    total = (await db.execute(count_query)).scalar_one()
    column = getattr(WorkOrder, sort_by)
    ordering = column.desc() if sort_order == "desc" else column.asc()
    rows = (
        await db.execute(
            row_query.order_by(ordering, WorkOrder.id.asc()).limit(limit).offset(offset)
        )
    ).all()
    packed = [
        {
            "order": row[0],
            "asset_name": row.asset_name,
            "asset_inv_number": row.asset_inv_number,
            "executor_name": row.executor_name,
            "section_name": row.section_name,
        }
        for row in rows
    ]
    if packed:
        await _attach_repairs(db, packed)
    return packed, total


async def get_order_row(db: AsyncSession, order_id: UUID) -> dict[str, Any] | None:
    row = (
        await db.execute(_order_rows_statement().where(WorkOrder.id == order_id))
    ).one_or_none()
    if row is None:
        return None
    packed = {
        "order": row[0],
        "asset_name": row.asset_name,
        "asset_inv_number": row.asset_inv_number,
        "executor_name": row.executor_name,
        "section_name": row.section_name,
    }
    await _attach_repairs(db, [packed])
    return packed


async def _attach_repairs(db: AsyncSession, packed: list[dict[str, Any]]) -> None:
    order_ids = [row["order"].id for row in packed]
    repairs = (
        await db.execute(
            select(WorkOrderRepair, WorkType.code, WorkType.name)
            .join(WorkType, WorkType.id == WorkOrderRepair.work_type_id)
            .where(WorkOrderRepair.work_order_id.in_(order_ids))
            .order_by(WorkOrderRepair.sort_order, WorkOrderRepair.id)
        )
    ).all()
    repair_ids = [row[0].id for row in repairs]
    item_groups: dict[UUID, list[WorkOrderItem]] = defaultdict(list)
    if repair_ids:
        items = (
            await db.execute(
                select(WorkOrderItem)
                .where(WorkOrderItem.repair_id.in_(repair_ids))
                .order_by(WorkOrderItem.sort_order, WorkOrderItem.id)
            )
        ).scalars()
        for item in items:
            item_groups[item.repair_id].append(item)
    repair_groups: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for repair, type_code, type_name in repairs:
        repair_groups[repair.work_order_id].append(
            {
                "id": repair.id,
                "work_order_id": repair.work_order_id,
                "work_type_id": repair.work_type_id,
                "work_type_code": type_code,
                "work_type_name": type_name,
                "sort_order": repair.sort_order,
                "items": item_groups[repair.id],
            }
        )
    for row in packed:
        row["repairs"] = repair_groups[row["order"].id]


async def add_repair_rows(
    db: AsyncSession, order_id: UUID, repairs_payload: list[Any]
) -> None:
    for repair_order, repair_input in enumerate(repairs_payload):
        repair = WorkOrderRepair(
            work_order_id=order_id,
            work_type_id=repair_input.work_type_id,
            sort_order=repair_order,
        )
        db.add(repair)
        await db.flush()
        for item_order, item_input in enumerate(repair_input.items):
            db.add(
                WorkOrderItem(
                    repair_id=repair.id,
                    nomenclature_id=item_input.nomenclature_id,
                    name=item_input.name,
                    inv_no=item_input.inv_no,
                    unit=item_input.unit,
                    qty=item_input.qty,
                    note=item_input.note,
                    sort_order=item_order,
                )
            )


async def replace_repairs(
    db: AsyncSession, order_id: UUID, repairs_payload: list[Any]
) -> None:
    repair_ids = list(
        (
            await db.execute(
                select(WorkOrderRepair.id).where(WorkOrderRepair.work_order_id == order_id)
            )
        ).scalars()
    )
    if repair_ids:
        await db.execute(
            WorkOrderItem.__table__.delete().where(WorkOrderItem.repair_id.in_(repair_ids))
        )
        await db.execute(
            WorkOrderRepair.__table__.delete().where(WorkOrderRepair.id.in_(repair_ids))
        )
    await add_repair_rows(db, order_id, repairs_payload)


async def find_norms(
    db: AsyncSession, department_id: UUID, keys: list[tuple[UUID, UUID]]
) -> dict[tuple[UUID, UUID], NomenclatureNorm]:
    if not keys:
        return {}
    conditions = [
        (NomenclatureNorm.nomenclature_id == nomenclature_id)
        & (NomenclatureNorm.work_type_id == work_type_id)
        for nomenclature_id, work_type_id in keys
    ]
    rows = (
        await db.execute(
            select(NomenclatureNorm).where(
                NomenclatureNorm.department_id == department_id,
                or_(*conditions),
            )
        )
    ).scalars()
    return {(row.nomenclature_id, row.work_type_id): row for row in rows}


async def list_template_items(
    db: AsyncSession, work_type_id: UUID, department_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(WorkTypeTemplate, WorkType.code, Nomenclature.name)
            .join(WorkType, WorkType.id == WorkTypeTemplate.work_type_id)
            .outerjoin(Nomenclature, Nomenclature.id == WorkTypeTemplate.nomenclature_id)
            .where(
                WorkTypeTemplate.work_type_id == work_type_id,
                or_(
                    WorkTypeTemplate.department_id == department_id,
                    WorkTypeTemplate.department_id.is_(None),
                ),
            )
            .order_by(WorkTypeTemplate.id)
        )
    ).all()
    return [
        {
            "id": template.id,
            "work_type_id": template.work_type_id,
            "work_type": code,
            "department_id": template.department_id,
            "nomenclature_id": template.nomenclature_id,
            "nomenclature_name": nomenclature_name,
            "name": template.name or nomenclature_name,
            "inv_no": template.inv_no,
            "unit": template.unit,
            "default_quantity": template.default_quantity,
            "is_required": template.is_required,
            "note": template.note,
        }
        for template, code, nomenclature_name in rows
    ]
