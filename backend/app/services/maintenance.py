import math
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.maintenance import MaintenanceInterval, MaintenancePlan
from app.repositories import maintenance as repository
from app.schemas.maintenance import (
    MaintenancePlanRead,
    MaintenancePlanUpdate,
    MaintenanceScheduleItem,
    MaintenanceScheduleRead,
    MaintenanceSettingsRead,
    MaintenanceSettingsUpdate,
)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance plan not found"
    )


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _master_section_scope(user: User) -> UUID | None:
    if user.role != "master":
        return None
    if user.section_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master user must be assigned to a section",
        )
    return user.section_id


def _ceil_days(distance_km: Decimal, daily_average_km: Decimal) -> int:
    return math.ceil(distance_km / daily_average_km)


def estimate_date(
    today: date, remaining_km: Decimal, daily_average_km: Decimal
) -> date:
    if remaining_km >= 0:
        return today + timedelta(days=_ceil_days(remaining_km, daily_average_km))
    return today - timedelta(days=_ceil_days(abs(remaining_km), daily_average_km))


def _next_km_trigger(
    mileage: Decimal, interval_km: Decimal, plans: list[MaintenancePlan]
) -> Decimal:
    completed_triggers = [
        plan.trigger_mileage
        for plan in plans
        if plan.status == "completed" and plan.trigger_mileage is not None
    ]
    last_completed = max(completed_triggers, default=None)
    outstanding = [
        plan
        for plan in plans
        if plan.status in {"scheduled", "in_progress"}
        and plan.trigger_mileage is not None
        and (last_completed is None or plan.trigger_mileage > last_completed)
    ]
    if outstanding:
        return min(plan.trigger_mileage for plan in outstanding if plan.trigger_mileage is not None)

    if last_completed is not None:
        next_after_completion = last_completed + interval_km
        if mileage > next_after_completion:
            crossed = (mileage // interval_km) * interval_km
            return max(crossed, next_after_completion)
        return next_after_completion

    if mileage > 0:
        crossed = (mileage // interval_km) * interval_km
        if crossed > 0:
            return crossed
    return (mileage // interval_km + 1) * interval_km


def _plan_status(plan: MaintenancePlan, mileage: Decimal) -> str:
    if plan.status == "scheduled":
        if plan.trigger_mileage is not None and mileage >= plan.trigger_mileage:
            return "overdue"
        if plan.scheduled_date is not None and plan.scheduled_date < date.today():
            return "overdue"
        return "upcoming"
    return plan.status


def _in_month(scheduled_date: date | None, start: date, end: date) -> bool:
    return scheduled_date is not None and start <= scheduled_date < end


async def get_daily_average_km(db: AsyncSession) -> Decimal | None:
    settings_row = await repository.get_settings(db)
    return settings_row.daily_average_km if settings_row else None


async def get_settings(db: AsyncSession) -> MaintenanceSettingsRead:
    return MaintenanceSettingsRead(daily_average_km=await get_daily_average_km(db))


async def update_settings(
    db: AsyncSession, payload: MaintenanceSettingsUpdate
) -> MaintenanceSettingsRead:
    try:
        result = await repository.save_daily_average_km(db, payload.daily_average_km)
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Could not save the daily mileage estimate") from exc
    return MaintenanceSettingsRead(daily_average_km=result.daily_average_km)


async def reconcile_asset_plans(
    db: AsyncSession, asset: FixedAsset, mileage: Decimal
) -> None:
    daily_average_km = await get_daily_average_km(db)
    today = date.today()
    intervals = await repository.list_active_intervals(db, asset.asset_type)
    for interval in intervals:
        plans = await repository.plans_for_interval(db, asset.id, interval.id)
        if interval.interval_km is not None:
            if daily_average_km is None:
                continue
            trigger = _next_km_trigger(mileage, interval.interval_km, plans)
            remaining = trigger - mileage
            warning_distance = (
                interval.interval_km * interval.warn_percent / Decimal("100")
            )
            if remaining > warning_distance:
                continue
            scheduled_date = estimate_date(today, remaining, daily_average_km)
            await repository.upsert_scheduled_plan(
                db,
                asset_id=asset.id,
                interval_id=interval.id,
                trigger_mileage=trigger,
                scheduled_date=scheduled_date,
            )
            continue

        if interval.interval_days is None:
            continue
        completed_dates = [
            plan.completed_date
            for plan in plans
            if plan.status == "completed" and plan.completed_date is not None
        ]
        base_date = max(completed_dates, default=today)
        scheduled_date = base_date + timedelta(days=interval.interval_days)
        outstanding = [
            plan
            for plan in plans
            if plan.status in {"scheduled", "in_progress"}
            and plan.trigger_mileage is None
        ]
        if outstanding:
            scheduled_date = min(
                (plan.scheduled_date for plan in outstanding if plan.scheduled_date),
                default=scheduled_date,
            )
        days_remaining = (scheduled_date - today).days
        warning_days = Decimal(interval.interval_days) * interval.warn_percent / Decimal("100")
        if Decimal(days_remaining) > warning_days:
            continue
        await repository.upsert_scheduled_plan(
            db,
            asset_id=asset.id,
            interval_id=interval.id,
            trigger_mileage=None,
            scheduled_date=scheduled_date,
        )


def _plan_read(row: dict[str, Any]) -> MaintenancePlanRead:
    plan = row["plan"]
    return MaintenancePlanRead(
        id=plan.id,
        asset_id=plan.asset_id,
        asset_name=row["asset_name"],
        asset_inv_number=row["asset_inv_number"],
        section_id=row["section_id"],
        interval_id=plan.interval_id,
        interval_code=row["interval_code"],
        interval_name=row["interval_name"],
        work_type_id=row["work_type_id"],
        status=plan.status,
        trigger_mileage=plan.trigger_mileage,
        scheduled_date=plan.scheduled_date,
        completed_date=plan.completed_date,
        work_order_id=plan.work_order_id,
    )


async def list_plans(
    db: AsyncSession,
    user: User,
    *,
    asset_id: UUID | None,
    status_filter: str | None,
    month: str | None,
    limit: int,
    offset: int,
) -> tuple[list[MaintenancePlanRead], int]:
    master_section_id = _master_section_scope(user)
    month_start: date | None = None
    month_end: date | None = None
    if month is not None:
        try:
            month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="month must use YYYY-MM format"
            ) from exc
        month_end = month_start.replace(
            day=monthrange(month_start.year, month_start.month)[1]
        ) + timedelta(days=1)
    rows, total = await repository.list_plans(
        db,
        asset_id=asset_id,
        status_filter=status_filter,
        month_start=month_start,
        month_end=month_end,
        master_section_id=master_section_id,
        limit=limit,
        offset=offset,
    )
    return [_plan_read(row) for row in rows], total


async def update_plan(
    db: AsyncSession, user: User, plan_id: UUID, payload: MaintenancePlanUpdate
) -> MaintenancePlanRead:
    master_section_id = _master_section_scope(user)
    plan = await repository.get_plan(
        db, plan_id, master_section_id=master_section_id, lock=True
    )
    if plan is None:
        raise _not_found()
    values = payload.model_dump(exclude_unset=True)
    if values.get("work_order_id") is not None:
        from app.repositories import work_orders as work_order_repository

        order = await work_order_repository.get_order(
            db,
            values["work_order_id"],
            master_section_id=master_section_id,
        )
        if order is None:
            if master_section_id is not None:
                raise _not_found()
            raise HTTPException(
                status_code=422,
                detail="Linked work order must exist and use the same fixed asset",
            )
        if order.fixed_asset_id != plan.asset_id:
            raise HTTPException(
                status_code=422,
                detail="Linked work order must exist and use the same fixed asset",
            )

    requested_status = values.get("status")
    if requested_status is not None and requested_status != plan.status:
        allowed = {
            "scheduled": {"in_progress", "cancelled"},
            "in_progress": {"completed", "cancelled"},
        }
        if requested_status not in allowed.get(plan.status, set()):
            raise _conflict(
                f"Invalid maintenance plan status transition: {plan.status} -> {requested_status}"
            )
    if requested_status == "completed" and "completed_date" not in values:
        values["completed_date"] = date.today()
    for field, value in values.items():
        setattr(plan, field, value)
    plan.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Maintenance plan references an invalid record") from exc
    fresh = await repository.get_plan(
        db, plan_id, master_section_id=master_section_id
    )
    if fresh is None:
        raise _not_found()
    rows, _ = await repository.list_plans(
        db,
        asset_id=fresh.asset_id,
        status_filter=None,
        month_start=None,
        month_end=None,
        master_section_id=master_section_id,
        limit=1000,
        offset=0,
    )
    match = next((row for row in rows if row["plan"].id == plan_id), None)
    if match is None:
        raise _not_found()
    return _plan_read(match)


async def _interval_target(
    asset: FixedAsset,
    interval: MaintenanceInterval,
    plans_by_key: dict[tuple[UUID, UUID], list[MaintenancePlan]],
    daily_average_km: Decimal | None,
    today: date,
) -> tuple[Decimal | None, date]:
    plans = plans_by_key.get((asset.id, interval.id), [])
    if interval.interval_km is not None:
        if daily_average_km is None:
            return None, today
        trigger = _next_km_trigger(asset.mileage, interval.interval_km, plans)
        remaining = trigger - asset.mileage
        return trigger, estimate_date(today, remaining, daily_average_km)
    if interval.interval_days is not None:
        completed_dates = [
            plan.completed_date
            for plan in plans
            if plan.status == "completed" and plan.completed_date is not None
        ]
        outstanding_dates = [
            plan.scheduled_date
            for plan in plans
            if plan.status in {"scheduled", "in_progress"}
            and plan.scheduled_date is not None
        ]
        target = min(outstanding_dates) if outstanding_dates else (
            max(completed_dates, default=today) + timedelta(days=interval.interval_days)
        )
        return None, target
    return None, today


async def get_schedule(
    db: AsyncSession, user: User, month: str
) -> MaintenanceScheduleRead:
    master_section_id = _master_section_scope(user)
    try:
        month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="month must use YYYY-MM format") from exc
    month_end = month_start.replace(
        day=monthrange(month_start.year, month_start.month)[1]
    ) + timedelta(days=1)

    daily_average_km = await get_daily_average_km(db)
    schedule: list[MaintenanceScheduleItem] = []
    work_orders = await repository.list_work_orders_for_schedule(
        db,
        start=month_start,
        end=month_end,
        master_section_id=master_section_id,
    )
    for row in work_orders:
        order = row["order"]
        start_date = order.date_start.date() if order.date_start else order.created_at.date()
        display_status = (
            "overdue"
            if order.status in {"pending", "in_progress"}
            and order.date_end is not None
            and order.date_end.date() < date.today()
            else {
                "pending": "upcoming",
                "in_progress": "in_progress",
                "completed": "completed",
            }.get(order.status, "upcoming")
        )
        if start_date >= month_end or (
            order.date_end is not None and order.date_end.date() < month_start
        ):
            continue
        schedule.append(
            MaintenanceScheduleItem(
                id=str(order.id),
                entity_type="work_order",
                unit=f"{row['asset_name']} · {row['asset_inv_number']}",
                type=", ".join(code for _, code in row["work_types"] if code)
                or order.description,
                startDate=start_date,
                depot=row["section_name"] or "",
                tech=row["executor_name"] or "",
                status=display_status,
                note=order.note,
                mileage=row["mileage"],
                asset_id=order.fixed_asset_id,
                section_id=order.section_id,
                work_order_id=order.id,
                work_type_id=row["work_types"][0][0] if row["work_types"] else None,
            )
        )

    plan_rows, _ = await repository.list_plans(
        db,
        asset_id=None,
        status_filter=None,
        month_start=None,
        month_end=None,
        master_section_id=master_section_id,
        limit=10000,
        offset=0,
    )
    plans_by_key = await repository.list_asset_interval_plans(
        db, master_section_id=master_section_id
    )
    for row in plan_rows:
        plan = row["plan"]
        if plan.status == "cancelled":
            continue
        mileage = row["mileage"]
        displayed_status = _plan_status(plan, mileage)
        if not _in_month(plan.scheduled_date, month_start, month_end) and displayed_status != "overdue":
            continue
        schedule.append(
            MaintenanceScheduleItem(
                id=str(plan.id),
                entity_type="maintenance_plan",
                unit=f"{row['asset_name']} · {row['asset_inv_number']}",
                type=f"{row['interval_code']} — {row['interval_name']}",
                startDate=plan.scheduled_date or date.today(),
                depot=row["section_name"] or "",
                tech="",
                status=displayed_status,
                mileage=mileage,
                remainingKm=(
                    plan.trigger_mileage - mileage
                    if plan.trigger_mileage is not None
                    else None
                ),
                nextThreshold=plan.trigger_mileage,
                asset_id=plan.asset_id,
                section_id=row["section_id"],
                interval_id=plan.interval_id,
                work_type_id=row["work_type_id"],
                plan_id=plan.id,
                work_order_id=plan.work_order_id,
            )
        )

    today = date.today()
    assets = await repository.list_schedule_assets(
        db, master_section_id=master_section_id
    )
    for asset in assets:
        intervals = await repository.list_active_intervals(db, asset.asset_type)
        for interval in intervals:
            if interval.interval_km is not None and daily_average_km is None:
                continue
            plans = plans_by_key.get((asset.id, interval.id), [])
            trigger, scheduled_date = await _interval_target(
                asset,
                interval,
                plans_by_key,
                daily_average_km,
                today,
            )
            if any(
                plan.status in {"scheduled", "in_progress"}
                and (
                    plan.trigger_mileage == trigger
                    if trigger is not None
                    else plan.trigger_mileage is None
                )
                for plan in plans
            ):
                continue
            remaining = trigger - asset.mileage if trigger is not None else None
            display_status = (
                "overdue"
                if (
                    remaining is not None and remaining <= 0
                )
                or scheduled_date < today
                else "upcoming"
            )
            if not _in_month(scheduled_date, month_start, month_end) and display_status != "overdue":
                continue
            schedule.append(
                MaintenanceScheduleItem(
                    id=f"forecast:{asset.id}:{interval.id}",
                    entity_type="forecast",
                    unit=f"{asset.name} · {asset.inv_number}",
                    type=f"{interval.code} — {interval.name}",
                    startDate=scheduled_date,
                    depot=asset.depot or "",
                    tech="",
                    status=display_status,
                    mileage=asset.mileage,
                    remainingKm=remaining,
                    nextThreshold=trigger,
                    asset_id=asset.id,
                    section_id=asset.section_id,
                    interval_id=interval.id,
                    work_type_id=interval.work_type_id,
                )
            )
    schedule.sort(key=lambda item: (item.startDate, item.unit, item.type))
    return MaintenanceScheduleRead(
        schedule=schedule, daily_average_km=daily_average_km
    )
