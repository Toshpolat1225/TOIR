from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.maintenance import (
    MaintenanceInterval,
    MaintenancePlan,
    MaintenanceSettings,
    WorkType,
)
from app.models.organization import Employee, Section
from app.models.work_orders import WorkOrder, WorkOrderRepair


async def get_settings(db: AsyncSession) -> MaintenanceSettings | None:
    return await db.get(MaintenanceSettings, 1)


async def save_daily_average_km(
    db: AsyncSession, daily_average_km: Decimal
) -> MaintenanceSettings:
    statement = (
        insert(MaintenanceSettings)
        .values(id=1, daily_average_km=daily_average_km)
        .on_conflict_do_update(
            index_elements=[MaintenanceSettings.id],
            set_={
                "daily_average_km": daily_average_km,
                "updated_at": func.now(),
            },
        )
        .returning(MaintenanceSettings)
    )
    result = await db.execute(statement)
    settings = result.scalar_one()
    await db.commit()
    return settings


async def get_asset(db: AsyncSession, asset_id: UUID) -> FixedAsset | None:
    return await db.get(FixedAsset, asset_id)


async def lock_asset_mileage(db: AsyncSession, asset_id: UUID) -> Decimal | None:
    result = await db.execute(
        select(FixedAsset.mileage)
        .where(FixedAsset.id == asset_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def list_active_intervals(
    db: AsyncSession, asset_type: str
) -> list[MaintenanceInterval]:
    result = await db.execute(
        select(MaintenanceInterval)
        .where(
            MaintenanceInterval.is_active.is_(True),
            MaintenanceInterval.asset_types.any(asset_type),
        )
        .order_by(MaintenanceInterval.code.asc(), MaintenanceInterval.id.asc())
    )
    return list(result.scalars().all())


async def get_interval(
    db: AsyncSession, interval_id: UUID
) -> MaintenanceInterval | None:
    return await db.get(MaintenanceInterval, interval_id)


async def list_schedule_assets(
    db: AsyncSession, *, master_section_id: UUID | None = None
) -> list[FixedAsset]:
    statement = select(FixedAsset)
    if master_section_id is not None:
        statement = statement.where(FixedAsset.section_id == master_section_id)
    result = await db.execute(statement.order_by(FixedAsset.name.asc(), FixedAsset.id.asc()))
    return list(result.scalars().all())


async def plans_for_interval(
    db: AsyncSession, asset_id: UUID, interval_id: UUID
) -> list[MaintenancePlan]:
    result = await db.execute(
        select(MaintenancePlan)
        .where(
            MaintenancePlan.asset_id == asset_id,
            MaintenancePlan.interval_id == interval_id,
        )
        .order_by(
            MaintenancePlan.trigger_mileage.desc().nullslast(),
            MaintenancePlan.scheduled_date.desc().nullslast(),
            MaintenancePlan.created_at.desc(),
        )
    )
    return list(result.scalars().all())


async def get_plan(
    db: AsyncSession,
    plan_id: UUID,
    *,
    master_section_id: UUID | None = None,
    lock: bool = False,
) -> MaintenancePlan | None:
    statement = select(MaintenancePlan).where(MaintenancePlan.id == plan_id)
    if master_section_id is not None:
        statement = statement.join(
            FixedAsset, FixedAsset.id == MaintenancePlan.asset_id
        ).where(FixedAsset.section_id == master_section_id)
    if lock:
        statement = statement.with_for_update(of=MaintenancePlan)
    return (await db.execute(statement)).scalar_one_or_none()


async def get_plan_for_trigger(
    db: AsyncSession,
    asset_id: UUID,
    interval_id: UUID,
    trigger_mileage: Decimal | None,
    *,
    master_section_id: UUID | None = None,
) -> MaintenancePlan | None:
    statement = select(MaintenancePlan).where(
        MaintenancePlan.asset_id == asset_id,
        MaintenancePlan.interval_id == interval_id,
    )
    if master_section_id is not None:
        statement = statement.join(
            FixedAsset, FixedAsset.id == MaintenancePlan.asset_id
        ).where(FixedAsset.section_id == master_section_id)
    if trigger_mileage is None:
        statement = statement.where(
            MaintenancePlan.trigger_mileage.is_(None),
            MaintenancePlan.status.in_(("scheduled", "in_progress")),
        )
    else:
        statement = statement.where(MaintenancePlan.trigger_mileage == trigger_mileage)
    return (await db.execute(statement.with_for_update())).scalar_one_or_none()


async def upsert_scheduled_plan(
    db: AsyncSession,
    *,
    asset_id: UUID,
    interval_id: UUID,
    trigger_mileage: Decimal | None,
    scheduled_date: date,
) -> MaintenancePlan:
    plan = await get_plan_for_trigger(
        db, asset_id, interval_id, trigger_mileage
    )
    if plan is None:
        plan = MaintenancePlan(
            asset_id=asset_id,
            interval_id=interval_id,
            trigger_mileage=trigger_mileage,
            scheduled_date=scheduled_date,
            status="scheduled",
        )
        db.add(plan)
        await db.flush()
        return plan
    if plan.status == "scheduled":
        plan.scheduled_date = scheduled_date
        plan.updated_at = datetime.now(timezone.utc)
    return plan


def _plan_statement() -> Select[Any]:
    return (
        select(
            MaintenancePlan,
            FixedAsset.name.label("asset_name"),
            FixedAsset.inv_number.label("asset_inv_number"),
            FixedAsset.mileage.label("mileage"),
            FixedAsset.section_id.label("section_id"),
            Section.name.label("section_name"),
            MaintenanceInterval.code.label("interval_code"),
            MaintenanceInterval.name.label("interval_name"),
            MaintenanceInterval.work_type_id.label("work_type_id"),
        )
        .join(FixedAsset, FixedAsset.id == MaintenancePlan.asset_id)
        .join(MaintenanceInterval, MaintenanceInterval.id == MaintenancePlan.interval_id)
        .outerjoin(Section, Section.id == FixedAsset.section_id)
    )


async def list_plans(
    db: AsyncSession,
    *,
    asset_id: UUID | None,
    status_filter: str | None,
    month_start: date | None,
    month_end: date | None,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    filters: list[Any] = []
    if asset_id is not None:
        filters.append(MaintenancePlan.asset_id == asset_id)
    if status_filter is not None:
        filters.append(MaintenancePlan.status == status_filter)
    if month_start is not None and month_end is not None:
        filters.extend(
            (
                MaintenancePlan.scheduled_date >= month_start,
                MaintenancePlan.scheduled_date < month_end,
            )
        )
    if master_section_id is not None:
        filters.append(
            MaintenancePlan.asset_id.in_(
                select(FixedAsset.id).where(
                    FixedAsset.section_id == master_section_id
                )
            )
        )

    count_query = select(func.count()).select_from(MaintenancePlan)
    statement = _plan_statement()
    if filters:
        count_query = count_query.where(*filters)
        statement = statement.where(*filters)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            statement.order_by(
                MaintenancePlan.scheduled_date.asc().nullslast(),
                MaintenancePlan.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        {
            "plan": row[0],
            "asset_name": row.asset_name,
            "asset_inv_number": row.asset_inv_number,
            "mileage": row.mileage,
            "section_id": row.section_id,
            "section_name": row.section_name,
            "interval_code": row.interval_code,
            "interval_name": row.interval_name,
            "work_type_id": row.work_type_id,
        }
        for row in rows
    ], total


async def list_work_orders_for_schedule(
    db: AsyncSession,
    *,
    start: date,
    end: date,
    master_section_id: UUID | None = None,
) -> list[dict[str, Any]]:
    statement = (
        select(
            WorkOrder,
            FixedAsset.name.label("asset_name"),
            FixedAsset.inv_number.label("asset_inv_number"),
            FixedAsset.mileage.label("mileage"),
            FixedAsset.section_id.label("asset_section_id"),
            Section.name.label("section_name"),
            Employee.full_name.label("executor_name"),
        )
        .join(FixedAsset, FixedAsset.id == WorkOrder.fixed_asset_id)
        .outerjoin(Section, Section.id == WorkOrder.section_id)
        .outerjoin(Employee, Employee.id == WorkOrder.executor_id)
        .where(
            func.coalesce(WorkOrder.date_start, WorkOrder.created_at) < end,
            func.coalesce(
                WorkOrder.date_end, WorkOrder.date_start, WorkOrder.created_at
            )
            >= start,
        )
        .order_by(
            func.coalesce(WorkOrder.date_start, WorkOrder.created_at).asc(),
            WorkOrder.created_at.asc(),
        )
    )
    if master_section_id is not None:
        statement = statement.where(
            WorkOrder.section_id == master_section_id,
            FixedAsset.section_id == master_section_id,
        )
    rows = (await db.execute(statement)).all()
    work_order_ids = [row[0].id for row in rows]
    work_types_by_order: dict[UUID, list[tuple[UUID, str]]] = {}
    if work_order_ids:
        repair_rows = (
            await db.execute(
                select(
                    WorkOrderRepair.work_order_id,
                    WorkOrderRepair.work_type_id,
                    WorkType.code,
                )
                .join(WorkType, WorkType.id == WorkOrderRepair.work_type_id)
                .where(WorkOrderRepair.work_order_id.in_(work_order_ids))
            )
        ).all()
        for order_id, work_type_id, type_code in repair_rows:
            work_types_by_order.setdefault(order_id, []).append(
                (work_type_id, type_code)
            )
    return [
        {
            "order": row[0],
            "asset_name": row.asset_name,
            "asset_inv_number": row.asset_inv_number,
            "mileage": row.mileage,
            "asset_section_id": row.asset_section_id,
            "section_name": row.section_name,
            "executor_name": row.executor_name,
            "work_types": work_types_by_order.get(row[0].id, []),
        }
        for row in rows
    ]


async def get_linked_plan(
    db: AsyncSession, work_order_id: UUID, *, lock: bool = False
) -> MaintenancePlan | None:
    statement = select(MaintenancePlan).where(
        MaintenancePlan.work_order_id == work_order_id
    )
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def complete_plan_for_order(
    db: AsyncSession, work_order_id: UUID, completed_date: date
) -> None:
    plan = await get_linked_plan(db, work_order_id, lock=True)
    if plan is not None and plan.status != "completed":
        plan.status = "completed"
        plan.completed_date = completed_date
        plan.updated_at = datetime.now(timezone.utc)


async def list_asset_interval_plans(
    db: AsyncSession, *, master_section_id: UUID | None = None
) -> dict[tuple[UUID, UUID], list[MaintenancePlan]]:
    statement = select(MaintenancePlan)
    if master_section_id is not None:
        statement = statement.join(
            FixedAsset, FixedAsset.id == MaintenancePlan.asset_id
        ).where(FixedAsset.section_id == master_section_id)
    result = await db.execute(
        statement.order_by(
            MaintenancePlan.asset_id,
            MaintenancePlan.interval_id,
            MaintenancePlan.trigger_mileage.desc().nullslast(),
            MaintenancePlan.scheduled_date.desc().nullslast(),
        )
    )
    grouped: dict[tuple[UUID, UUID], list[MaintenancePlan]] = {}
    for plan in result.scalars().all():
        grouped.setdefault((plan.asset_id, plan.interval_id), []).append(plan)
    return grouped
