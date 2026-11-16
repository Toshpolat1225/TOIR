import logging
import math
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.maintenance import MaintenanceInterval, MaintenancePlan
from app.repositories import maintenance as repository
from app.repositories import mileage as mileage_repository
from app.schemas.maintenance import (
    MaintenancePlanFromForecast,
    MaintenancePlanRead,
    MaintenancePlanUpdate,
    MaintenanceScheduleItem,
    MaintenanceScheduleRead,
    MaintenanceSettingsRead,
    MaintenanceSettingsUpdate,
)
from app.services.maintenance_planning import (
    calculate_maintenance_target,
    maintenance_urgency,
    next_mileage_threshold,
)

logger = logging.getLogger(__name__)


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


def _plan_status(plan: MaintenancePlan) -> str:
    if plan.status == "completed":
        return "completed"
    if plan.scheduled_date is not None and plan.scheduled_date < date.today():
        return "overdue"
    if plan.status == "scheduled":
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


LOCOMOTIVE_TYPES = frozenset({"locomotive", "diesel"})
KM_PLANNED_TYPES = LOCOMOTIVE_TYPES | {"wagon"}

async def reconcile_asset_plans(
    db: AsyncSession, asset: FixedAsset, mileage: Decimal
) -> int:
    # Wagons need an approved projection. Locomotive/diesel mileage comes from
    # the gated Wialon pull (D10) and is trusted as is.
    if asset.asset_type == "wagon" and not await mileage_repository.has_confirmed_projection(
        db, asset.id
    ):
        return 0
    today = date.today()
    created = 0
    intervals = await repository.list_active_intervals(db, asset.asset_type)
    for interval in intervals:
        target = calculate_maintenance_target(
            asset_type=asset.asset_type,
            interval_asset_types=interval.asset_types,
            mileage=mileage,
            interval_km=interval.interval_km,
            warn_percent=interval.warn_percent,
            daily_km_estimate=settings.daily_km_estimate,
            today=today,
        )
        if target is None:
            continue
        _, was_created = await repository.upsert_scheduled_plan_with_created(
            db,
            asset_id=asset.id,
            interval_id=interval.id,
            trigger_mileage=target.trigger_mileage,
            scheduled_date=target.scheduled_date,
        )
        created += was_created
    return created


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
        urgency=_plan_urgency(row),
        status=plan.status,
        trigger_mileage=plan.trigger_mileage,
        scheduled_date=plan.scheduled_date,
        completed_date=plan.completed_date,
        work_order_id=plan.work_order_id,
        scheduled_date_manual=plan.scheduled_date_manual,
        recommended_date=plan.recommended_date,
        reschedule_reason=plan.reschedule_reason,
    )


def _plan_urgency(row: dict[str, Any]) -> str | None:
    plan = row["plan"]
    interval_km = row.get("interval_km")
    mileage = row.get("mileage")
    if (
        plan.status not in {"scheduled", "in_progress"}
        or plan.trigger_mileage is None
        or interval_km is None
        or interval_km <= 0
        or mileage is None
    ):
        return None
    remaining_percent = (
        (plan.trigger_mileage - mileage) / interval_km * Decimal("100")
    )
    return maintenance_urgency(
        remaining_percent, row.get("warn_percent", Decimal("0"))
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
    urgency_filter: str | None = None,
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
        urgency_filter=urgency_filter,
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
    await _apply_reschedule(db, plan, values)
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
    row = await repository.get_plan_read_row(
        db, plan_id, master_section_id=master_section_id
    )
    if row is None:
        raise _not_found()
    return _plan_read(row)


MAX_RESCHEDULE_DAYS = 366


def _validate_reschedule_date(new_date: date, today: date) -> None:
    if new_date < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maintenance cannot be rescheduled to a past date",
        )
    if new_date > today + timedelta(days=MAX_RESCHEDULE_DAYS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maintenance cannot be rescheduled more than {MAX_RESCHEDULE_DAYS} days ahead",
        )


def _clean_reason(reason: str | None) -> str | None:
    cleaned = (reason or "").strip()
    return cleaned or None


async def _recommended_date_now(
    db: AsyncSession, plan: MaintenancePlan, today: date
) -> date | None:
    """The date the system would plan today for this plan's threshold, if it can tell."""
    asset = await db.get(FixedAsset, plan.asset_id)
    if asset is None or plan.trigger_mileage is None or asset.mileage is None:
        return None
    remaining = plan.trigger_mileage - asset.mileage
    return estimate_date(today, remaining, Decimal(settings.daily_km_estimate))


async def _apply_reschedule(
    db: AsyncSession, plan: MaintenancePlan, values: dict[str, Any]
) -> None:
    """Handle `scheduled_date` / `reset_schedule` of a plan update (mutates `plan` and `values`)."""
    reset = bool(values.pop("reset_schedule", False))
    moving = "scheduled_date" in values
    new_date = values.pop("scheduled_date", None)
    reason = values.pop("reschedule_reason", None)
    if not moving and not reset:
        if reason is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="reschedule_reason is only valid together with scheduled_date",
            )
        return
    if moving and reset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Send either scheduled_date or reset_schedule, not both",
        )
    if values:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rescheduling cannot be combined with other plan changes",
        )
    if plan.status != "scheduled":
        raise _conflict("Only scheduled maintenance plans can be rescheduled")
    today = date.today()
    if moving:
        if new_date is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="scheduled_date must be a date (use reset_schedule to return to the recommendation)",
            )
        _validate_reschedule_date(new_date, today)
        if not plan.scheduled_date_manual:
            plan.recommended_date = plan.scheduled_date
        plan.scheduled_date = new_date
        plan.scheduled_date_manual = True
        plan.reschedule_reason = _clean_reason(reason)
        return
    if not plan.scheduled_date_manual:
        raise _conflict("The plan already uses the recommended date")
    recommended = (
        await _recommended_date_now(db, plan, today) or plan.recommended_date or plan.scheduled_date
    )
    plan.scheduled_date = recommended
    plan.scheduled_date_manual = False
    plan.recommended_date = None
    plan.reschedule_reason = None


async def create_plan_from_forecast(
    db: AsyncSession, user: User, payload: MaintenancePlanFromForecast
) -> MaintenancePlanRead:
    """Create a real plan for a forecast row on the date the planner chose."""
    master_section_id = _master_section_scope(user)
    asset = await db.get(FixedAsset, payload.asset_id)
    if asset is None or (
        master_section_id is not None and asset.section_id != master_section_id
    ):
        raise _not_found()
    interval = await db.get(MaintenanceInterval, payload.interval_id)
    if (
        interval is None
        or not interval.is_active
        or asset.asset_type not in interval.asset_types
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This maintenance interval does not apply to the asset",
        )
    today = date.today()
    _validate_reschedule_date(payload.scheduled_date, today)
    has_trusted_mileage = asset.asset_type in LOCOMOTIVE_TYPES or (
        asset.asset_type == "wagon"
        and await mileage_repository.has_confirmed_projection(db, asset.id)
    )
    if interval.interval_km is not None and not has_trusted_mileage:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The mileage of this asset is not trusted yet, so a km-based plan cannot be created",
        )
    plans_by_key = await repository.list_asset_interval_plans(
        db, master_section_id=master_section_id
    )
    trigger, recommended = await _interval_target(
        asset, interval, plans_by_key, Decimal(settings.daily_km_estimate), today
    )
    for existing in plans_by_key.get((asset.id, interval.id), []):
        if (trigger is not None and existing.trigger_mileage == trigger) or (
            trigger is None
            and existing.trigger_mileage is None
            and existing.status in {"scheduled", "in_progress"}
        ):
            raise _conflict(
                "A plan for this threshold already exists; reschedule that plan instead"
            )
    plan = MaintenancePlan(
        asset_id=asset.id,
        interval_id=interval.id,
        status="scheduled",
        trigger_mileage=trigger,
        scheduled_date=payload.scheduled_date,
        scheduled_date_manual=True,
        recommended_date=recommended,
        reschedule_reason=_clean_reason(payload.reschedule_reason),
    )
    db.add(plan)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("A plan for this threshold already exists") from exc
    row = await repository.get_plan_read_row(
        db, plan.id, master_section_id=master_section_id
    )
    if row is None:
        raise _not_found()
    return _plan_read(row)


async def _interval_target(
    asset: FixedAsset,
    interval: MaintenanceInterval,
    plans_by_key: dict[tuple[UUID, UUID], list[MaintenancePlan]],
    daily_average_km: Decimal | None,
    today: date,
) -> tuple[Decimal | None, date]:
    plans = plans_by_key.get((asset.id, interval.id), [])
    if interval.interval_km is not None:
        if asset.asset_type not in KM_PLANNED_TYPES:
            return None, today
        if daily_average_km is None:
            return None, today
        trigger = next_mileage_threshold(asset.mileage, interval.interval_km)
        if trigger is None:
            return None, today
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


def _with_asset_display(
    item: MaintenanceScheduleItem, info: dict[str, Any] | None
) -> MaintenanceScheduleItem:
    """Attach joined names to a schedule item and make `unit` identical for all of an asset's items.

    Forecast items used the raw type code ("diesel") and an empty section, because the ORM
    `name`/`depot` properties are only filled by other loaders; plans and work orders used
    the translated name. One source of truth removes the mismatch.
    """
    if info is None:
        return item
    type_label = info["type_name"] or info["asset_type"]
    inv_number = info["inv_number"]
    return item.model_copy(
        update={
            "unit": f"{type_label} {info['serial_number'] or ''}-{inv_number} · {inv_number}",
            "depot": item.depot or info["section_name"] or "",
            "asset_type": info["asset_type"],
            "asset_type_name": info["type_name"],
            "asset_model": info["model_name"],
            "asset_serial": info["serial_number"],
            "asset_inv_number": inv_number,
            "asset_status": info["status"],
            "asset_status_name": info["status_name"],
            "asset_online": info["wialon_online"],
        }
    )


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

    daily_average_km = Decimal(settings.daily_km_estimate)
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

    plan_rows = await repository.list_schedule_plans(
        db,
        start=month_start,
        end=month_end,
        today=date.today(),
        master_section_id=master_section_id,
    )
    plans_by_key = await repository.list_asset_interval_plans(
        db, master_section_id=master_section_id
    )
    for row in plan_rows:
        plan = row["plan"]
        if plan.status == "cancelled":
            continue
        mileage = row["mileage"]
        displayed_status = _plan_status(plan)
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
                intervalKm=row.get("interval_km"),
                asset_id=plan.asset_id,
                section_id=row["section_id"],
                interval_id=plan.interval_id,
                work_type_id=row["work_type_id"],
                urgency=_plan_urgency(row),
                plan_id=plan.id,
                work_order_id=plan.work_order_id,
                dateManual=plan.scheduled_date_manual,
                recommendedDate=plan.recommended_date,
                rescheduleReason=plan.reschedule_reason,
            )
        )

    today = date.today()
    assets = await repository.list_schedule_assets(
        db, master_section_id=master_section_id
    )
    for asset in assets:
        has_wagon_projection = (
            asset.asset_type == "wagon"
            and await mileage_repository.has_confirmed_projection(db, asset.id)
        ) or asset.asset_type in LOCOMOTIVE_TYPES
        intervals = await repository.list_active_intervals(db, asset.asset_type)
        for interval in intervals:
            if interval.interval_km is not None and not has_wagon_projection:
                continue
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
                (
                    trigger is not None
                    and plan.trigger_mileage == trigger
                )
                or (
                    trigger is None
                    and plan.trigger_mileage is None
                    and plan.status in {"scheduled", "in_progress"}
                )
                for plan in plans
            ):
                continue
            remaining = trigger - asset.mileage if trigger is not None else None
            display_status = (
                "overdue"
                if scheduled_date < today
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
                    mileage=asset.mileage if has_wagon_projection else None,
                    remainingKm=remaining,
                    nextThreshold=trigger,
                    intervalKm=interval.interval_km,
                    asset_id=asset.id,
                    section_id=asset.section_id,
                    interval_id=interval.id,
                    work_type_id=interval.work_type_id,
                )
            )
    asset_info = await repository.list_asset_display_info(
        db, master_section_id=master_section_id
    )
    schedule = [_with_asset_display(item, asset_info.get(item.asset_id)) for item in schedule]
    schedule.sort(key=lambda item: (item.startDate, item.unit, item.type))
    return MaintenanceScheduleRead(
        schedule=schedule, daily_average_km=daily_average_km
    )
