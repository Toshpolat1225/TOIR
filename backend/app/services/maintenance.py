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
from app.schemas.maintenance import (
    MaintenanceDecisionRead,
    MaintenancePlanBlock,
    MaintenancePlanWaive,
    MaintenancePlanFromForecast,
    MaintenancePlanRead,
    MaintenancePlanUpdate,
    MaintenanceScheduleItem,
    MaintenanceScheduleRead,
    MaintenanceSettingsRead,
    MaintenanceSettingsUpdate,
    MaintenanceUnforecasted,
)
from app.services import maintenance_lifecycle as lifecycle
from app.services import maintenance_obligations as obligations
from app.services.maintenance_planning import maintenance_urgency

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
    if plan.status in ("completed", "covered", "waived"):
        return "completed"
    if plan.status == "blocked":
        return "blocked"
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


async def reconcile_asset_plans(
    db: AsyncSession, asset: FixedAsset, mileage: Decimal
) -> int:
    """Re-plan one asset with the living-plan engine; returns the number of NEW plans.

    `mileage` is the value the caller has just learned (it wins over `asset.mileage`).
    Wagon km obligations exist only for wagons whose mileage is CONFIRMED (see the obligations loader).
    """
    return await obligations.reconcile_asset(db, asset, mileage)


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
        blocked_reason=plan.blocked_reason,
        blocked_until=plan.blocked_until,
        blocked_note=plan.blocked_note,
        deferral_count=plan.deferral_count or 0,
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
    if requested_status == "cancelled":
        raise _conflict(
            "A maintenance obligation is never cancelled: block the plan (POST .../block) "
            "or ask an administrator to waive the cycle (POST .../waive)"
        )
    if requested_status is not None and requested_status != plan.status:
        allowed = {
            "scheduled": {"in_progress"},
            "in_progress": {"completed"},
        }
        if requested_status not in allowed.get(plan.status, set()):
            raise _conflict(
                f"Invalid maintenance plan status transition: {plan.status} -> {requested_status}"
            )
    await _apply_reschedule(db, plan, values, user)
    if requested_status == "completed" and plan.status != "completed":
        completed_on = values.pop("completed_date", None) or date.today()
        values.pop("status")
        await lifecycle.finalize_completion(
            db, plan, completed_on=completed_on, work_order_id=values.get("work_order_id"), user=user
        )
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


async def _obligation_of(
    db: AsyncSession, plan: MaintenancePlan
) -> obligations.Obligation | None:
    asset = await db.get(FixedAsset, plan.asset_id)
    if asset is None:
        return None
    _, evaluated = await obligations.evaluate_for_asset(db, asset)
    for ob in evaluated:
        if ob.interval.id == plan.interval_id:
            return ob
    return None


async def _recommended_date_now(
    db: AsyncSession, plan: MaintenancePlan, today: date
) -> date | None:
    """The date the system would plan today for this plan's obligation, if it can tell."""
    ob = await _obligation_of(db, plan)
    return ob.planned_date if ob is not None else None


async def _require_approval_if_needed(
    db: AsyncSession, plan: MaintenancePlan, new_date: date, user: User
) -> None:
    """Operators may move a date inside the tolerance; anything bigger needs an administrator."""
    if user.role == "admin":
        return
    deferring = plan.scheduled_date is not None and new_date > plan.scheduled_date
    if deferring and (plan.deferral_count or 0) >= settings.maintenance_deferral_escalation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Administrator approval required: this plan was already deferred "
                f"{plan.deferral_count} times"
            ),
        )
    if deferring:
        ob = await _obligation_of(db, plan)
        if ob is not None and ob.markers.beyond_tolerance_on(new_date):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrator approval required: the new date is beyond the tolerance of the limit",
            )


async def _apply_reschedule(
    db: AsyncSession,
    plan: MaintenancePlan,
    values: dict[str, Any],
    user: User | None = None,
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
    if plan.status == "blocked":
        raise _conflict("Unblock the maintenance plan before rescheduling it")
    if plan.status != "scheduled":
        raise _conflict("Only scheduled maintenance plans can be rescheduled")
    today = date.today()
    previous = plan.scheduled_date
    if moving:
        if new_date is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="scheduled_date must be a date (use reset_schedule to return to the recommendation)",
            )
        _validate_reschedule_date(new_date, today)
        if user is not None:
            await _require_approval_if_needed(db, plan, new_date, user)
        if not plan.scheduled_date_manual:
            plan.recommended_date = plan.scheduled_date
        if previous is not None and new_date > previous:
            plan.deferral_count = (plan.deferral_count or 0) + 1
        plan.scheduled_date = new_date
        plan.scheduled_date_manual = True
        plan.reschedule_reason = _clean_reason(reason)
        if user is not None:
            await lifecycle.log_decision(
                db, plan, "reschedule", note=plan.reschedule_reason, from_date=previous, to_date=new_date,
                user=user, approver=user if user.role == "admin" else None,
            )
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
    if user is not None:
        await lifecycle.log_decision(
            db, plan, "reschedule", note="возврат к рекомендованной дате", from_date=previous,
            to_date=recommended, user=user,
        )


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
    _, evaluated = await obligations.evaluate_for_asset(db, asset)
    obligation = next((ob for ob in evaluated if ob.interval.id == interval.id), None)
    if obligation is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "There is no trusted forecast for this interval yet (untrusted mileage or no baseline), "
                "so a plan cannot be created"
            ),
        )
    if obligation.plan is not None:
        raise _conflict(
            "A plan for this threshold already exists; reschedule that plan instead"
        )
    plan = MaintenancePlan(
        asset_id=asset.id,
        interval_id=interval.id,
        status="scheduled",
        trigger_mileage=obligation.due_km,
        scheduled_date=payload.scheduled_date,
        scheduled_date_manual=True,
        recommended_date=obligation.planned_date or today,
        reschedule_reason=_clean_reason(payload.reschedule_reason),
    )
    db.add(plan)
    try:
        await db.flush()
        await lifecycle.log_decision(
            db, plan, "reschedule", note=plan.reschedule_reason, from_date=plan.recommended_date,
            to_date=payload.scheduled_date, user=user, approver=user if user.role == "admin" else None,
        )
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


# ── block / unblock / waive / decisions ──────────────────────────────────────

async def _load_plan_for_action(
    db: AsyncSession, user: User, plan_id: UUID
) -> tuple[MaintenancePlan, UUID | None]:
    master_section_id = _master_section_scope(user)
    plan = await repository.get_plan(
        db, plan_id, master_section_id=master_section_id, lock=True
    )
    if plan is None:
        raise _not_found()
    return plan, master_section_id


async def _commit_and_read(
    db: AsyncSession, plan_id: UUID, master_section_id: UUID | None
) -> MaintenancePlanRead:
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


async def block_plan(
    db: AsyncSession, user: User, plan_id: UUID, payload: MaintenancePlanBlock
) -> MaintenancePlanRead:
    plan, master = await _load_plan_for_action(db, user, plan_id)
    await lifecycle.block_plan(db, plan, payload, user)
    return await _commit_and_read(db, plan_id, master)


async def unblock_plan(
    db: AsyncSession, user: User, plan_id: UUID
) -> MaintenancePlanRead:
    plan, master = await _load_plan_for_action(db, user, plan_id)
    await lifecycle.unblock_plan(db, plan, user)
    return await _commit_and_read(db, plan_id, master)


async def waive_plan(
    db: AsyncSession, user: User, plan_id: UUID, payload: MaintenancePlanWaive
) -> MaintenancePlanRead:
    plan, master = await _load_plan_for_action(db, user, plan_id)
    await lifecycle.waive_plan(db, plan, payload, user)
    return await _commit_and_read(db, plan_id, master)


async def list_plan_decisions(
    db: AsyncSession, user: User, plan_id: UUID
) -> list[MaintenanceDecisionRead]:
    master_section_id = _master_section_scope(user)
    plan = await repository.get_plan(db, plan_id, master_section_id=master_section_id)
    if plan is None:
        raise _not_found()
    return [
        MaintenanceDecisionRead.model_validate(row)
        for row in await lifecycle.list_decisions(db, plan_id)
    ]


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


def _model_fields(ob: "obligations.Obligation | None") -> dict[str, Any]:
    """The living-plan facts of one obligation, in the names of the schedule item."""
    if ob is None:
        return {}
    markers = ob.markers
    km_pace = ob.pace_km
    return {
        "state": markers.state,
        "rank": ob.interval.rank,
        "limiting": markers.limiting,
        "limitingUsed": markers.used,
        "limitingLimit": markers.limit,
        "tolerance": markers.tolerance,
        "windowOpen": markers.window_open,
        "dateEarly": markers.date_p75,
        "dateTypical": markers.date_p50,
        "dateLate": markers.date_p25,
        "paceKmPerDay": km_pace.p50 if km_pace is not None else None,
        "paceFastKmPerDay": km_pace.p75 if km_pace is not None else None,
        "paceSource": km_pace.source if km_pace is not None else None,
        "paceDays": km_pace.n_days if km_pace is not None else None,
        "confidence": ob.confidence,
        "baselineSource": ob.baseline_source,
        "priority": ob.priority.score,
        "priorityWhy": list(ob.priority.why),
        "mergedInto": ob.merged_into,
        "opportunistic": ob.opportunistic,
        "paused": ob.paused,
        "mileageEstimated": ob.mileage_estimated,
        "urgency": ob.urgency,
    }


_UNFORECASTED_CAP = 300


def _unforecasted_units(
    assets: list[FixedAsset],
    intervals_by_type: dict[str, list[MaintenanceInterval]],
    by_key: dict[tuple[UUID, UUID], obligations.Obligation],
    ctx: obligations.Context,
    today: date,
) -> list[MaintenanceUnforecasted]:
    """Units whose maintenance cannot be dated, with the reason, so an empty chart is never a silent gap.

    * no_movement: the obligation exists but the unit does not move, so no date can be forecast.
    * no_pace_data: the unit has no GPS mileage history of its own, so its pace is unknown (never guessed).
    * no_mileage_baseline: a wagon without an approved opening balance (its km are not trusted yet).
    * no_mileage: no odometer value at all.
    * no_data: the intervals need a baseline (hours / calendar) nobody has entered.
    """
    dated: set[UUID] = set()
    undated: dict[UUID, int] = {}
    for ob in by_key.values():
        visible = (
            ob.plan is not None
            or ob.markers.state in {"over_limit", "over_tolerance"}
            or ob.planned_date is not None
        )
        if visible:
            dated.add(ob.asset.id)
        else:
            undated[ob.asset.id] = undated.get(ob.asset.id, 0) + 1
    with_obligations = dated | set(undated)
    result: list[MaintenanceUnforecasted] = []
    for asset in assets:
        if ctx.behavior(asset) in obligations.WITHDRAWN_BEHAVIORS or asset.decommissioned_at is not None:
            continue
        applicable = [
            interval
            for interval in intervals_by_type.get(asset.asset_type, [])
            if interval.is_active and asset.asset_type in interval.asset_types
        ]
        if not applicable:
            continue
        if asset.id in undated:
            no_pace = any(ob.pace_km.source == "none" for ob in by_key.values() if ob.asset.id == asset.id)
            reason, count = ("no_pace_data" if no_pace else "no_movement"), undated[asset.id]
        elif asset.id not in with_obligations:
            if asset.asset_type == "wagon" and asset.id not in ctx.trusted_wagons:
                reason = "no_mileage_baseline"
            elif asset.mileage is None:
                reason = "no_mileage"
            else:
                reason = "no_data"
            count = len(applicable)
        else:
            continue
        result.append(
            MaintenanceUnforecasted(
                asset_id=asset.id,
                unit=f"{asset.name} · {asset.inv_number}",
                asset_type=asset.asset_type,
                reason=reason,
                intervals=count,
            )
        )
    result.sort(key=lambda item: (item.reason, item.unit))
    return result


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

    today = date.today()
    assets = await repository.list_schedule_assets(
        db, master_section_id=master_section_id
    )
    ctx = await obligations.load_context(db, assets, today=today)
    intervals_by_type: dict[str, list[MaintenanceInterval]] = {}
    by_key: dict[tuple[UUID, UUID], obligations.Obligation] = {}
    for asset in assets:
        if asset.asset_type not in intervals_by_type:
            intervals_by_type[asset.asset_type] = await repository.list_active_intervals(
                db, asset.asset_type
            )
        if not intervals_by_type[asset.asset_type]:
            continue
        for ob in obligations.evaluate_asset(asset, intervals_by_type[asset.asset_type], ctx):
            by_key[ob.key] = ob

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
            and order.date_end.date() < today
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
        today=today,
        master_section_id=master_section_id,
    )
    for row in plan_rows:
        plan = row["plan"]
        if plan.status == "cancelled":
            continue
        mileage = row["mileage"]
        ob = by_key.get((plan.asset_id, plan.interval_id))
        if ob is not None and ob.plan is not plan:
            ob = None  # that obligation belongs to another cycle of the same interval
        if plan.status not in {"scheduled", "in_progress", "blocked"}:
            ob = None
        fields = _model_fields(ob)
        urgency = fields.pop("urgency", None) if ob is not None else _plan_urgency(row)
        due_km = ob.due_km if ob is not None and ob.due_km is not None else plan.trigger_mileage
        schedule.append(
            MaintenanceScheduleItem(
                id=str(plan.id),
                entity_type="maintenance_plan",
                unit=f"{row['asset_name']} · {row['asset_inv_number']}",
                type=f"{row['interval_code']} — {row['interval_name']}",
                startDate=plan.scheduled_date or today,
                depot=row["section_name"] or "",
                tech="",
                status=_plan_status(plan),
                mileage=mileage,
                remainingKm=due_km - mileage if due_km is not None else None,
                nextThreshold=due_km,
                intervalKm=row.get("interval_km"),
                asset_id=plan.asset_id,
                section_id=row["section_id"],
                interval_id=plan.interval_id,
                work_type_id=row["work_type_id"],
                urgency=urgency,
                plan_id=plan.id,
                work_order_id=plan.work_order_id,
                dateManual=plan.scheduled_date_manual,
                recommendedDate=plan.recommended_date,
                rescheduleReason=plan.reschedule_reason,
                planStatus=plan.status,
                blockedReason=plan.blocked_reason,
                blockedUntil=plan.blocked_until,
                blockedNote=plan.blocked_note,
                deferralCount=plan.deferral_count or 0,
                **fields,
            )
        )

    assets_by_id = {asset.id: asset for asset in assets}
    for ob in by_key.values():
        if ob.plan is not None:
            continue  # shown as its plan
        planned = ob.planned_date
        overdue = ob.markers.state in {"over_limit", "over_tolerance"} or (
            planned is not None and planned < today
        )
        if not overdue and not _in_month(planned, month_start, month_end):
            continue
        asset = assets_by_id[ob.asset.id]
        start_date = planned or today
        trusted = asset.asset_type != "wagon" or asset.id in ctx.trusted_wagons
        fields = _model_fields(ob)
        urgency = fields.pop("urgency")
        schedule.append(
            MaintenanceScheduleItem(
                id=f"forecast:{asset.id}:{ob.interval.id}",
                entity_type="forecast",
                unit=f"{asset.name} · {asset.inv_number}",
                type=f"{ob.interval.code} — {ob.interval.name}",
                startDate=start_date,
                depot=asset.depot or "",
                tech="",
                status="overdue" if (start_date < today or overdue) else "upcoming",  # over the limit with an unknown pace has no past date but is still overdue
                mileage=asset.mileage if trusted else None,
                remainingKm=ob.due_km - asset.mileage if ob.due_km is not None else None,
                nextThreshold=ob.due_km,
                intervalKm=ob.interval.interval_km,
                asset_id=asset.id,
                section_id=asset.section_id,
                interval_id=ob.interval.id,
                work_type_id=ob.interval.work_type_id,
                urgency=urgency,
                **fields,
            )
        )
    asset_info = await repository.list_asset_display_info(
        db, master_section_id=master_section_id
    )
    schedule = [_with_asset_display(item, asset_info.get(item.asset_id)) for item in schedule]
    schedule.sort(key=lambda item: (item.startDate, item.unit, item.type))
    unforecasted = _unforecasted_units(assets, intervals_by_type, by_key, ctx, today)
    counts: dict[str, int] = {}
    for item in unforecasted:
        counts[item.reason] = counts.get(item.reason, 0) + 1
    return MaintenanceScheduleRead(
        schedule=schedule,
        daily_average_km=ctx.default_pace,
        unforecasted=unforecasted[:_UNFORECASTED_CAP],
        unforecasted_total=len(unforecasted),
        unforecasted_counts=counts,
    )
