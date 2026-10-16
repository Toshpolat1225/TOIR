import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.maintenance import MaintenancePlan
from app.models.work_orders import WorkOrder
from app.repositories import work_orders as repository
from app.repositories import maintenance as maintenance_repository
from app.schemas.work_orders import (
    NormCheckRequest,
    NormCheckResult,
    WorkOrderCreate,
    WorkOrderRead,
    WorkOrderUpdate,
)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Work order not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def _is_work_order_number_conflict(exc: IntegrityError) -> bool:
    current: BaseException | None = exc.orig
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        diagnostic = getattr(current, "diag", None)
        constraint_name = getattr(current, "constraint_name", None) or getattr(
            diagnostic, "constraint_name", None
        )
        sqlstate = getattr(current, "sqlstate", None) or getattr(
            current, "pgcode", None
        )
        if (
            constraint_name == "work_orders_number_key"
            and sqlstate in {None, "23505"}
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _read(row: dict[str, Any]) -> WorkOrderRead:
    order = row["order"]
    now = datetime.now(timezone.utc)
    return WorkOrderRead(
        **{
            key: getattr(order, key)
            for key in (
                "id", "number", "fixed_asset_id", "section_id", "department_id",
                "order_kind", "status", "priority", "executor_id", "chief_id",
                "description", "note", "date_start", "date_end", "closed_at",
                "mileage_at_creation", "mileage_threshold", "created_by",
                "created_at", "updated_at",
            )
        },
        asset_name=row["asset_name"],
        asset_inv_number=row["asset_inv_number"],
        executor_name=row["executor_name"],
        section_name=row["section_name"],
        is_overdue=bool(
            order.status in {"pending", "in_progress"}
            and order.date_end is not None
            and order.date_end < now
        ),
        repairs=row["repairs"],
    )


async def list_orders(
    db: AsyncSession,
    user: User,
    *,
    status_filter: str | None,
    open_only: bool,
    section_id: UUID | None,
    department_id: UUID | None,
    fixed_asset_id: UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    q: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[WorkOrderRead], int]:
    if user.role == "master" and user.section_id is None:
        raise _not_found()

    statuses: list[str] | None = None
    if open_only:
        statuses = ["pending", "in_progress"]
    elif status_filter:
        statuses = [value.strip() for value in status_filter.split(",") if value.strip()]
        allowed = {"pending", "in_progress", "completed", "cancelled"}
        if not statuses or any(value not in allowed for value in statuses):
            raise HTTPException(status_code=422, detail="Invalid status filter")
    try:
        rows, total = await repository.list_orders(
            db,
            statuses=statuses,
            section_id=section_id,
            department_id=department_id,
            fixed_asset_id=fixed_asset_id,
            date_from=date_from,
            date_to=date_to,
            q=q,
            master_section_id=user.section_id if user.role == "master" else None,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_read(row) for row in rows], total


async def get_order(db: AsyncSession, user: User, order_id: UUID) -> WorkOrderRead:
    if user.role == "master" and user.section_id is None:
        raise _not_found()
    row = await repository.get_order_row(
        db,
        order_id,
        master_section_id=user.section_id if user.role == "master" else None,
    )
    if row is None:
        raise _not_found()
    return _read(row)


async def _resolve_create_scope(
    db: AsyncSession, user: User, payload: WorkOrderCreate
) -> tuple[UUID, UUID | None, Decimal]:
    asset = await repository.get_asset(db, payload.fixed_asset_id)
    if asset is None:
        raise HTTPException(status_code=422, detail="Fixed asset does not exist")
    target_section_id = payload.section_id or asset.section_id
    if target_section_id is None:
        raise HTTPException(status_code=422, detail="A section is required for this work order")
    if user.role == "master":
        if user.section_id is None or target_section_id != user.section_id:
            raise HTTPException(status_code=403, detail="Cannot create work orders for another section")
        if asset.section_id != user.section_id:
            raise HTTPException(status_code=403, detail="Fixed asset is outside your section")
    section = await repository.get_section(db, target_section_id)
    if section is None:
        raise HTTPException(status_code=422, detail="Section does not exist")
    department_id = payload.department_id or section.department_id
    if user.role == "master" and department_id != section.department_id:
        raise HTTPException(status_code=403, detail="Department is outside your section")
    return target_section_id, department_id, asset.mileage


async def create_order(
    db: AsyncSession, user: User, payload: WorkOrderCreate
) -> WorkOrderRead:
    section_id, department_id, mileage = await _resolve_create_scope(db, user, payload)
    user_id = user.id
    maintenance_plan_id = payload.maintenance_plan_id
    maintenance_interval_id = payload.maintenance_interval_id
    if maintenance_plan_id is not None:
        plan = await maintenance_repository.get_plan(db, maintenance_plan_id)
        if plan is None or plan.asset_id != payload.fixed_asset_id:
            raise HTTPException(
                status_code=422,
                detail="Maintenance plan must exist and belong to the selected fixed asset",
            )
        if plan.work_order_id is not None:
            raise _conflict(
                "Maintenance plan is already linked to a work order"
            )
        if plan.status in {"completed", "cancelled"}:
            raise _conflict("A completed or cancelled maintenance plan cannot be reopened")
        if (
            maintenance_interval_id is not None
            and plan.interval_id != maintenance_interval_id
        ):
            raise HTTPException(
                status_code=422,
                detail="Maintenance plan does not match the selected maintenance interval",
            )
        maintenance_interval_id = plan.interval_id
        if (
            payload.maintenance_trigger_mileage is not None
            and plan.trigger_mileage != payload.maintenance_trigger_mileage
        ):
            raise HTTPException(
                status_code=422,
                detail="Maintenance plan does not match the selected mileage threshold",
            )
        interval = await maintenance_repository.get_interval(db, plan.interval_id)
        if interval is not None and interval.work_type_id is not None and all(
            repair.work_type_id != interval.work_type_id
            for repair in payload.repairs
        ):
            raise HTTPException(
                status_code=422,
                detail="Work order repair type does not match the maintenance plan",
            )
    elif maintenance_interval_id is not None:
        asset = await repository.get_asset(db, payload.fixed_asset_id)
        interval = await maintenance_repository.get_interval(
            db, maintenance_interval_id
        )
        if (
            asset is None
            or interval is None
            or not interval.is_active
            or asset.asset_type not in interval.asset_types
        ):
            raise HTTPException(
                status_code=422,
                detail="Maintenance interval is not active for the selected fixed asset",
            )
        if interval.work_type_id is not None and all(
            repair.work_type_id != interval.work_type_id
            for repair in payload.repairs
        ):
            raise HTTPException(
                status_code=422,
                detail="Work order repair type does not match the maintenance interval",
            )
    base_time = datetime.now(timezone.utc).replace(microsecond=0)
    for attempt in range(5):
        number = f"НЗ-{(base_time + timedelta(seconds=attempt)).strftime('%Y%m%d-%H%M%S')}"
        try:
            async with db.begin_nested():
                order = WorkOrder(
                    number=number,
                    fixed_asset_id=payload.fixed_asset_id,
                    section_id=section_id,
                    department_id=department_id,
                    order_kind=payload.order_kind,
                    status="pending",
                    priority=payload.priority,
                    executor_id=payload.executor_id,
                    chief_id=payload.chief_id,
                    description=payload.description,
                    note=payload.note,
                    date_start=payload.date_start,
                    date_end=payload.date_end,
                    mileage_at_creation=mileage,
                    created_by=user_id,
                )
                db.add(order)
                await db.flush()
                order_id = order.id
                await repository.add_repair_rows(db, order_id, payload.repairs)
                if maintenance_plan_id is not None or maintenance_interval_id is not None:
                    await maintenance_repository.lock_asset_mileage(
                        db, payload.fixed_asset_id
                    )
                    if maintenance_plan_id is not None:
                        plan = await maintenance_repository.get_plan(
                            db, maintenance_plan_id, lock=True
                        )
                    else:
                        plan = await maintenance_repository.get_plan_for_trigger(
                            db,
                            payload.fixed_asset_id,
                            maintenance_interval_id,
                            payload.maintenance_trigger_mileage,
                        )
                        if plan is None:
                            plan = MaintenancePlan(
                                asset_id=payload.fixed_asset_id,
                                interval_id=maintenance_interval_id,
                                trigger_mileage=payload.maintenance_trigger_mileage,
                                scheduled_date=(
                                    payload.date_start.date()
                                    if payload.date_start is not None
                                    else datetime.now(timezone.utc).date()
                                ),
                                status="scheduled",
                            )
                            db.add(plan)
                            await db.flush()
                    if plan is None or plan.asset_id != payload.fixed_asset_id:
                        raise HTTPException(
                            status_code=422,
                            detail="Maintenance plan must exist and belong to the selected fixed asset",
                        )
                    if plan.status in {"completed", "cancelled"}:
                        raise _conflict(
                            "A completed or cancelled maintenance plan cannot be reopened"
                        )
                    plan.work_order_id = order_id
                    plan.status = "in_progress"
                    plan.updated_at = datetime.now(timezone.utc)
            await db.commit()
            result = await repository.get_order_row(db, order_id)
            if result is None:
                raise RuntimeError("Created work order could not be reloaded")
            return _read(result)
        except IntegrityError as exc:
            number_conflict = _is_work_order_number_conflict(exc)
            await db.rollback()
            if not number_conflict:
                raise _conflict(
                    "Work order references an invalid asset, section, employee, "
                    "work type, or nomenclature item"
                ) from exc
            if attempt == 4:
                raise _conflict(
                    "Could not generate a unique work order number after several attempts"
                ) from exc
            await asyncio.sleep(random.uniform(0.01, 0.05))
        except Exception:
            await db.rollback()
            raise
    raise _conflict("Could not generate a unique work order number")


async def update_order(
    db: AsyncSession, user: User, order_id: UUID, payload: WorkOrderUpdate
) -> WorkOrderRead:
    if user.role == "master" and user.section_id is None:
        raise _not_found()
    order = await repository.get_order(
        db,
        order_id,
        master_section_id=user.section_id if user.role == "master" else None,
        lock=True,
    )
    if order is None:
        raise _not_found()
    if order.status in {"completed", "cancelled"}:
        raise _conflict("Completed or cancelled work orders cannot be modified")
    values = payload.model_dump(exclude_unset=True, exclude={"repairs"})
    requested_status = values.get("status")
    if requested_status is not None and requested_status != order.status:
        allowed = {
            "pending": {"in_progress", "cancelled"},
            "in_progress": {"completed", "cancelled"},
        }
        if requested_status not in allowed.get(order.status, set()):
            raise _conflict(f"Invalid status transition: {order.status} -> {requested_status}")

    target_section = values.get("section_id", order.section_id)
    if user.role == "master" and target_section != user.section_id:
        raise HTTPException(status_code=403, detail="Cannot move work orders to another section")
    if "fixed_asset_id" in values:
        asset = await repository.get_asset(db, values["fixed_asset_id"])
        if asset is None:
            raise HTTPException(status_code=422, detail="Fixed asset does not exist")
        if "section_id" not in values and asset.section_id is not None:
            values["section_id"] = asset.section_id
            target_section = asset.section_id
        if user.role == "master" and asset.section_id != user.section_id:
            raise HTTPException(status_code=403, detail="Fixed asset is outside your section")
        if "mileage_at_creation" not in values:
            values["mileage_at_creation"] = asset.mileage
    if "section_id" in values:
        section = await repository.get_section(db, values["section_id"])
        if section is None:
            raise HTTPException(status_code=422, detail="Section does not exist")
        if "department_id" not in values and section.department_id is not None:
            values["department_id"] = section.department_id
    if user.role == "master":
        section = await repository.get_section(db, target_section)
        if section is None or (
            "department_id" in values
            and values["department_id"] is not None
            and values["department_id"] != section.department_id
        ):
            raise HTTPException(status_code=403, detail="Department is outside your section")
    if requested_status == "completed":
        values["closed_at"] = datetime.now(timezone.utc)
    values["updated_at"] = datetime.now(timezone.utc)
    try:
        for field, value in values.items():
            setattr(order, field, value)
        if "repairs" in payload.model_fields_set:
            await repository.replace_repairs(db, order.id, payload.repairs or [])
        if requested_status == "completed":
            await maintenance_repository.complete_plan_for_order(
                db, order.id, datetime.now(timezone.utc).date()
            )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Work order references an invalid record or violates a database constraint") from exc
    except Exception:
        await db.rollback()
        raise
    return await get_order(db, user, order_id)


async def delete_order(db: AsyncSession, order_id: UUID) -> None:
    order = await repository.get_order(db, order_id, lock=True)
    if order is None:
        raise _not_found()
    await db.delete(order)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Work order is referenced by records and cannot be deleted") from exc


async def check_norms(
    db: AsyncSession, user: User, payload: NormCheckRequest
) -> list[NormCheckResult]:
    if user.role == "master":
        section = await repository.get_section(db, user.section_id) if user.section_id else None
        if section is None or section.department_id != payload.department_id:
            raise _not_found()
    keys = [(item.nomenclature_id, item.work_type_id) for item in payload.items]
    norms = await repository.find_norms(db, payload.department_id, keys)
    results: list[NormCheckResult] = []
    for item in payload.items:
        norm = norms.get((item.nomenclature_id, item.work_type_id))
        if norm is None:
            results.append(
                NormCheckResult(
                    nomenclature_id=item.nomenclature_id,
                    work_type_id=item.work_type_id,
                    qty=item.qty,
                    standard_quantity=None,
                    deviation_percent=None,
                    warning=False,
                    estimated_cost=None,
                )
            )
            continue
        if norm.standard_quantity == 0:
            deviation = None
            warning = item.qty > 0
        else:
            deviation = (
                (item.qty - norm.standard_quantity) / norm.standard_quantity * Decimal("100")
            )
            warning = deviation > Decimal("20")
        results.append(
            NormCheckResult(
                nomenclature_id=item.nomenclature_id,
                work_type_id=item.work_type_id,
                qty=item.qty,
                standard_quantity=norm.standard_quantity,
                deviation_percent=deviation,
                warning=warning,
                estimated_cost=item.qty * norm.avg_price,
            )
        )
    return results


async def list_template_items(
    db: AsyncSession, user: User, work_type_id: UUID, department_id: UUID
) -> list[dict[str, Any]]:
    if user.role == "master":
        section = await repository.get_section(db, user.section_id) if user.section_id else None
        if section is None or section.department_id != department_id:
            raise _not_found()
    return await repository.list_template_items(db, work_type_id, department_id)
