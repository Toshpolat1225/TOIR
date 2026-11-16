"""Lifecycle of the 'Tirik reja' model: completion and the rank cascade, block / unblock / waive,
disruptions, baselines, the decision log, KPIs, the invariant check and the periodic job.

Rule of the model: an obligation is never lost. Plans change state, they are not thrown away:
blocking, covering and waiving all keep the row and leave a decision behind.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.localization import FixedAssetStatus
from app.models.maintenance import (
    AssetMaintenanceBaseline,
    AssetMeterDaily,
    MaintenanceDecision,
    MaintenanceDisruption,
    MaintenanceInterval,
    MaintenancePlan,
)
from app.models.wialon_units import WialonUnitRecord
from app.models.work_orders import WorkOrder
from app.repositories import maintenance as repository
from app.schemas.maintenance import (
    MaintenanceBaselineRead,
    MaintenanceBaselineUpsert,
    MaintenanceDisruptionCreate,
    MaintenanceDisruptionRead,
    MaintenanceHealthIssue,
    MaintenanceHealthRead,
    MaintenanceKpiRead,
    MaintenancePlanBlock,
    MaintenancePlanWaive,
)
from app.services import maintenance_obligations as obligations
from app.services.maintenance_engine import covered_interval_ids

logger = logging.getLogger(__name__)

CLOSED_STATUSES = ("completed", "covered", "waived", "cancelled")
OPEN_STATUSES = ("scheduled", "in_progress", "blocked")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid(user: User | None) -> UUID | None:
    return getattr(user, "id", None) if user is not None else None


def _clean(text: str | None) -> str | None:
    cleaned = (text or "").strip()
    return cleaned or None


def _clear_block(plan: MaintenancePlan) -> None:
    plan.blocked_reason = None
    plan.blocked_until = None
    plan.blocked_note = None
    plan.blocked_by_disruption_id = None


async def log_decision(
    db: AsyncSession,
    plan: MaintenancePlan,
    kind: str,
    *,
    reason_code: str | None = None,
    note: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    user: User | None = None,
    approver: User | None = None,
) -> None:
    db.add(
        MaintenanceDecision(
            plan_id=plan.id,
            kind=kind,
            reason_code=reason_code,
            note=_clean(note),
            from_date=from_date,
            to_date=to_date,
            requested_by=_uid(user),
            approved_by=_uid(approver),
        )
    )


async def upsert_baseline(
    db: AsyncSession,
    *,
    asset_id: UUID,
    interval_id: UUID,
    done_at: date | None,
    km: Decimal,
    hours: Decimal | None,
    source: str,
    note: str | None = None,
    work_order_id: UUID | None = None,
    user_id: UUID | None = None,
) -> None:
    values = dict(
        asset_id=asset_id, interval_id=interval_id, done_at=done_at, km=km, hours=hours, source=source,
        note=_clean(note), work_order_id=work_order_id, updated_by=user_id, updated_at=_now(),
    )
    await db.execute(
        insert(AssetMaintenanceBaseline)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["asset_id", "interval_id"],
            set_={key: value for key, value in values.items() if key not in ("asset_id", "interval_id")},
        )
    )


async def _current_hours(db: AsyncSession, asset_id: UUID) -> Decimal | None:
    value = await db.scalar(
        select(func.max(WialonUnitRecord.cneh))
        .join(AssetSourceLink, AssetSourceLink.external_id == WialonUnitRecord.unit_id)
        .where(
            AssetSourceLink.asset_id == asset_id,
            AssetSourceLink.source == "wialon",
            AssetSourceLink.status == "active",
        )
    )
    return Decimal(value) if value is not None and value > 0 else None


# ── completion and the rank cascade ──────────────────────────────────────────

async def finalize_completion(
    db: AsyncSession,
    plan: MaintenancePlan,
    *,
    completed_on: date,
    work_order_id: UUID | None = None,
    user: User | None = None,
) -> list[MaintenancePlan]:
    """Close a plan as done: the next cycle counts from NOW, and every lower rank is covered by it.

    Returns the plans that were covered by this completion.
    """
    asset = await db.get(FixedAsset, plan.asset_id)
    interval = await db.get(MaintenanceInterval, plan.interval_id)
    mileage = Decimal(asset.mileage) if asset is not None and asset.mileage is not None else Decimal("0")
    hours = await _current_hours(db, plan.asset_id)
    plan.status = "completed"
    plan.completed_date = completed_on
    plan.completed_km = mileage
    plan.completed_hours = hours
    _clear_block(plan)
    plan.updated_at = _now()
    covered: list[MaintenancePlan] = []
    if interval is None:
        return covered
    await upsert_baseline(
        db, asset_id=plan.asset_id, interval_id=plan.interval_id, done_at=completed_on, km=mileage, hours=hours,
        source="completed", work_order_id=work_order_id or plan.work_order_id, user_id=_uid(user),
    )
    if interval.rank is None or asset is None:
        return covered  # an unranked interval is independent of the others
    siblings = await repository.list_active_intervals(db, asset.asset_type)
    ranks = {sibling.id: sibling.rank for sibling in siblings}
    for covered_id in covered_interval_ids(ranks, interval.id):
        if covered_id == interval.id:
            continue
        await upsert_baseline(
            db, asset_id=plan.asset_id, interval_id=covered_id, done_at=completed_on, km=mileage, hours=hours,
            source="completed", note=f"перекрыто {interval.code}", user_id=_uid(user),
        )
        open_plans = (
            await db.execute(
                select(MaintenancePlan).where(
                    MaintenancePlan.asset_id == plan.asset_id,
                    MaintenancePlan.interval_id == covered_id,
                    MaintenancePlan.status.in_(("scheduled", "blocked")),
                )
            )
        ).scalars().all()
        for lower in open_plans:
            lower.status = "covered"
            lower.covered_by_plan_id = plan.id
            lower.completed_date = completed_on
            _clear_block(lower)
            lower.updated_at = _now()
            await log_decision(
                db, lower, "cover", note=f"Выполнено {interval.code}: нижний уровень перекрыт", user=user
            )
            covered.append(lower)
    return covered


async def complete_plan_for_order(
    db: AsyncSession, order: WorkOrder, completed_on: date, *, user: User | None = None
) -> MaintenancePlan | None:
    plan = await repository.get_linked_plan(db, order.id, lock=True)
    if plan is None or plan.status in ("completed", "covered", "waived"):
        return None
    await finalize_completion(db, plan, completed_on=completed_on, work_order_id=order.id, user=user)
    return plan


async def release_plan_for_order(db: AsyncSession, order_id: UUID, *, note: str) -> MaintenancePlan | None:
    """The order behind a running plan was cancelled/deleted: the obligation goes back to 'scheduled'."""
    plan = await repository.get_linked_plan(db, order_id, lock=True)
    if plan is None or plan.status != "in_progress":
        return None
    plan.status = "scheduled"
    plan.work_order_id = None
    plan.updated_at = _now()
    await log_decision(db, plan, "release", reason_code="order_released", note=note)
    return plan


# ── block / unblock / waive ──────────────────────────────────────────────────

async def block_plan(db: AsyncSession, plan: MaintenancePlan, payload: MaintenancePlanBlock, user: User) -> None:
    if plan.status != "scheduled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only scheduled maintenance plans can be blocked")
    if payload.until is not None and payload.until < date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The block cannot end in the past")
    plan.status = "blocked"
    plan.blocked_reason = payload.reason_code
    plan.blocked_until = payload.until
    plan.blocked_note = _clean(payload.note)
    plan.blocked_by_disruption_id = None
    plan.updated_at = _now()
    await log_decision(db, plan, "block", reason_code=payload.reason_code, note=payload.note, to_date=payload.until, user=user)


async def unblock_plan(db: AsyncSession, plan: MaintenancePlan, user: User | None, *, note: str | None = None) -> None:
    if plan.status != "blocked":
        raise HTTPException(status.HTTP_409_CONFLICT, "The maintenance plan is not blocked")
    reason = plan.blocked_reason
    plan.status = "scheduled"
    _clear_block(plan)
    plan.updated_at = _now()
    await log_decision(db, plan, "unblock", reason_code=reason, note=note, user=user)


async def waive_plan(db: AsyncSession, plan: MaintenancePlan, payload: MaintenancePlanWaive, user: User) -> None:
    """Admin-only: this cycle is not needed. The next one counts from this cycle's threshold."""
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can waive a maintenance cycle")
    if plan.status not in ("scheduled", "blocked"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only scheduled or blocked plans can be waived")
    asset = await db.get(FixedAsset, plan.asset_id)
    mileage = Decimal(asset.mileage) if asset is not None and asset.mileage is not None else Decimal("0")
    plan.status = "waived"
    plan.completed_date = date.today()
    _clear_block(plan)
    plan.updated_at = _now()
    await upsert_baseline(
        db, asset_id=plan.asset_id, interval_id=plan.interval_id, done_at=date.today(),
        km=plan.trigger_mileage if plan.trigger_mileage is not None else mileage,
        hours=await _current_hours(db, plan.asset_id), source="waived", note=payload.reason, user_id=_uid(user),
    )
    await log_decision(db, plan, "waive", note=payload.reason, user=user, approver=user)


# ── disruptions ──────────────────────────────────────────────────────────────

async def _plans_in_scope(db: AsyncSession, disruption: MaintenanceDisruption) -> list[MaintenancePlan]:
    statement = (
        select(MaintenancePlan)
        .join(FixedAsset, FixedAsset.id == MaintenancePlan.asset_id)
        .where(MaintenancePlan.status == "scheduled", MaintenancePlan.scheduled_date >= disruption.starts_on)
        .with_for_update(of=MaintenancePlan)
    )
    if disruption.ends_on is not None:
        statement = statement.where(MaintenancePlan.scheduled_date <= disruption.ends_on)
    if disruption.scope == "asset":
        statement = statement.where(MaintenancePlan.asset_id == disruption.asset_id)
    elif disruption.scope == "section":
        statement = statement.where(FixedAsset.section_id == disruption.section_id)
    return list((await db.execute(statement)).scalars().all())


async def create_disruption(
    db: AsyncSession, payload: MaintenanceDisruptionCreate, user: User
) -> MaintenanceDisruptionRead:
    if payload.scope == "asset" and (payload.asset_id is None or payload.section_id is not None):
        raise HTTPException(422, "scope 'asset' needs asset_id (and no section_id)")
    if payload.scope == "section" and (payload.section_id is None or payload.asset_id is not None):
        raise HTTPException(422, "scope 'section' needs section_id (and no asset_id)")
    if payload.scope == "all" and (payload.asset_id is not None or payload.section_id is not None):
        raise HTTPException(422, "scope 'all' takes neither asset_id nor section_id")
    starts_on = payload.starts_on or date.today()
    if payload.ends_on is not None and payload.ends_on < starts_on:
        raise HTTPException(422, "ends_on cannot be before starts_on")
    disruption = MaintenanceDisruption(
        kind=payload.kind, scope=payload.scope, asset_id=payload.asset_id, section_id=payload.section_id,
        starts_on=starts_on, ends_on=payload.ends_on, status="open", note=_clean(payload.note), created_by=_uid(user),
    )
    db.add(disruption)
    await db.flush()
    affected = 0
    if payload.kind != "sensor_failure":  # a faulty sensor makes the forecast uncertain, it does not stop the work
        for plan in await _plans_in_scope(db, disruption):
            plan.status = "blocked"
            plan.blocked_reason = payload.kind
            plan.blocked_until = payload.ends_on
            plan.blocked_note = _clean(payload.note)
            plan.blocked_by_disruption_id = disruption.id
            plan.updated_at = _now()
            await log_decision(db, plan, "block", reason_code=payload.kind, note=payload.note, to_date=payload.ends_on, user=user)
            affected += 1
    await db.commit()
    return _disruption_read(disruption, affected)


def _disruption_read(disruption: MaintenanceDisruption, affected: int = 0) -> MaintenanceDisruptionRead:
    return MaintenanceDisruptionRead(
        id=disruption.id, kind=disruption.kind, scope=disruption.scope, asset_id=disruption.asset_id,
        section_id=disruption.section_id, starts_on=disruption.starts_on, ends_on=disruption.ends_on,
        status=disruption.status, note=disruption.note, affected_plans=affected,
    )


async def _release_disruption(db: AsyncSession, disruption: MaintenanceDisruption, user: User | None) -> int:
    disruption.status = "closed"
    disruption.closed_at = _now()
    plans = (
        await db.execute(
            select(MaintenancePlan)
            .where(MaintenancePlan.blocked_by_disruption_id == disruption.id, MaintenancePlan.status == "blocked")
            .with_for_update()
        )
    ).scalars().all()
    for plan in plans:
        plan.status = "scheduled"
        _clear_block(plan)
        plan.updated_at = _now()
        await log_decision(db, plan, "release", reason_code=disruption.kind, note="ограничение снято", user=user)
    return len(plans)


async def close_disruption(db: AsyncSession, disruption_id: UUID, user: User) -> MaintenanceDisruptionRead:
    disruption = await db.scalar(select(MaintenanceDisruption).where(MaintenanceDisruption.id == disruption_id).with_for_update())
    if disruption is None:
        raise HTTPException(404, "Disruption not found")
    if disruption.status == "closed":
        raise HTTPException(409, "The disruption is already closed")
    released = await _release_disruption(db, disruption, user)
    await db.commit()
    return _disruption_read(disruption, released)


async def list_disruptions(db: AsyncSession, *, only_open: bool) -> list[MaintenanceDisruptionRead]:
    statement = select(MaintenanceDisruption).order_by(MaintenanceDisruption.created_at.desc())
    if only_open:
        statement = statement.where(MaintenanceDisruption.status == "open")
    rows = (await db.execute(statement.limit(200))).scalars().all()
    counts = {
        disruption_id: count
        for disruption_id, count in (
            await db.execute(
                select(MaintenancePlan.blocked_by_disruption_id, func.count())
                .where(MaintenancePlan.blocked_by_disruption_id.is_not(None), MaintenancePlan.status == "blocked")
                .group_by(MaintenancePlan.blocked_by_disruption_id)
            )
        ).all()
    }
    return [_disruption_read(row, counts.get(row.id, 0)) for row in rows]


# ── baselines ────────────────────────────────────────────────────────────────

async def _odometer_offset(db: AsyncSession, asset_id: UUID) -> Decimal | None:
    """Wialon's absolute odometer minus the TOIR mileage (TOIR counts from when tracking began)."""
    cnm = await db.scalar(
        select(func.max(WialonUnitRecord.cnm))
        .join(AssetSourceLink, AssetSourceLink.external_id == WialonUnitRecord.unit_id)
        .where(
            AssetSourceLink.asset_id == asset_id,
            AssetSourceLink.source == "wialon",
            AssetSourceLink.status == "active",
        )
    )
    mileage = await db.scalar(select(FixedAsset.mileage).where(FixedAsset.id == asset_id))
    if cnm is None or mileage is None:
        return None
    return Decimal(cnm) - Decimal(mileage)


async def resolve_baseline_km(
    db: AsyncSession, asset: FixedAsset, *, km: Decimal | None, odometer_km: Decimal | None
) -> Decimal:
    if km is not None and odometer_km is not None:
        raise HTTPException(422, "Give km (TOIR scale) or odometer_km, not both")
    if km is not None:
        return km
    if odometer_km is None:
        raise HTTPException(422, "Give km (TOIR scale) or odometer_km")
    offset = await _odometer_offset(db, asset.id)
    if offset is None:
        raise HTTPException(422, "This asset has no Wialon odometer, so give km in the TOIR scale")
    return odometer_km - offset


async def set_baseline(
    db: AsyncSession, payload: MaintenanceBaselineUpsert, user: User, *, source: str = "manual",
    master_section_id: UUID | None = None,
) -> MaintenanceBaselineRead:
    asset = await db.get(FixedAsset, payload.asset_id)
    if asset is None or (master_section_id is not None and asset.section_id != master_section_id):
        raise HTTPException(404, "Asset not found")
    interval = await db.get(MaintenanceInterval, payload.interval_id)
    if interval is None or not interval.is_active or asset.asset_type not in interval.asset_types:
        raise HTTPException(422, "This maintenance interval does not apply to the asset")
    if payload.done_at > date.today():
        raise HTTPException(422, "done_at cannot be in the future")
    if payload.km is None and payload.odometer_km is None and interval.interval_km is None:
        km = Decimal(asset.mileage or 0)  # a purely calendar/hours interval: the km value is not used
    else:
        km = await resolve_baseline_km(db, asset, km=payload.km, odometer_km=payload.odometer_km)
    await upsert_baseline(
        db, asset_id=asset.id, interval_id=interval.id, done_at=payload.done_at, km=km, hours=payload.hours,
        source=source, note=payload.note, user_id=_uid(user),
    )
    await obligations.reconcile_asset(db, asset)
    await db.commit()
    row = await db.get(AssetMaintenanceBaseline, (asset.id, interval.id), populate_existing=True)
    return MaintenanceBaselineRead.model_validate(row)


async def list_baselines(
    db: AsyncSession, *, asset_id: UUID, master_section_id: UUID | None = None
) -> list[MaintenanceBaselineRead]:
    statement = select(AssetMaintenanceBaseline).where(AssetMaintenanceBaseline.asset_id == asset_id)
    if master_section_id is not None:
        statement = statement.join(FixedAsset, FixedAsset.id == AssetMaintenanceBaseline.asset_id).where(
            FixedAsset.section_id == master_section_id
        )
    return [MaintenanceBaselineRead.model_validate(row) for row in (await db.execute(statement)).scalars().all()]


async def list_decisions(db: AsyncSession, plan_id: UUID) -> list[MaintenanceDecision]:
    result = await db.execute(
        select(MaintenanceDecision).where(MaintenanceDecision.plan_id == plan_id).order_by(MaintenanceDecision.created_at.desc())
    )
    return list(result.scalars().all())


# ── all-asset evaluation, KPIs ───────────────────────────────────────────────

async def evaluate_all(
    db: AsyncSession, *, today: date | None = None, master_section_id: UUID | None = None
) -> tuple[obligations.Context, list[obligations.Obligation]]:
    assets = await repository.list_schedule_assets(db, master_section_id=master_section_id)
    ctx = await obligations.load_context(db, assets, today=today)
    by_type: dict[str, list[MaintenanceInterval]] = {}
    result: list[obligations.Obligation] = []
    for asset in assets:
        if asset.asset_type not in by_type:
            by_type[asset.asset_type] = await repository.list_active_intervals(db, asset.asset_type)
        if by_type[asset.asset_type]:
            result.extend(obligations.evaluate_asset(asset, by_type[asset.asset_type], ctx))
    return ctx, result


async def compute_kpis(db: AsyncSession, *, master_section_id: UUID | None = None) -> MaintenanceKpiRead:
    ctx, obs = await evaluate_all(db, master_section_id=master_section_id)
    today = ctx.today
    plan_filter = []
    if master_section_id is not None:
        plan_filter.append(MaintenancePlan.asset_id.in_(select(FixedAsset.id).where(FixedAsset.section_id == master_section_id)))
    open_rows = (
        await db.execute(
            select(MaintenancePlan.status, MaintenancePlan.scheduled_date_manual, MaintenancePlan.deferral_count).where(
                MaintenancePlan.status.in_(OPEN_STATUSES), *plan_filter
            )
        )
    ).all()
    since = today - timedelta(days=90)
    done_rows = (
        await db.execute(
            select(MaintenancePlan.completed_date, MaintenancePlan.scheduled_date).where(
                MaintenancePlan.status == "completed", MaintenancePlan.completed_date >= since, *plan_filter
            )
        )
    ).all()
    on_time = sum(1 for completed, scheduled in done_rows if scheduled is None or completed <= scheduled + timedelta(days=3))
    return MaintenanceKpiRead(
        as_of=today,
        obligations=len(obs),
        over_limit=sum(1 for ob in obs if ob.markers.state == "over_limit"),
        over_tolerance=sum(1 for ob in obs if ob.markers.state == "over_tolerance"),
        due_soon=sum(1 for ob in obs if ob.markers.state == "due_soon"),
        blocked=sum(1 for row in open_rows if row[0] == "blocked"),
        low_confidence=sum(1 for ob in obs if ob.confidence in ("low", "stale")),
        provisional_baseline=sum(1 for ob in obs if ob.baseline_source == "provisional"),
        open_plans=len(open_rows),
        manual_dates=sum(1 for row in open_rows if row[1]),
        avg_deferrals=round(sum(row[2] for row in open_rows) / len(open_rows), 2) if open_rows else 0.0,
        completed_last_90d=len(done_rows),
        on_time_last_90d=on_time,
        on_time_pct=round(on_time * 100 / len(done_rows), 1) if done_rows else None,
    )


# ── invariants ───────────────────────────────────────────────────────────────

async def run_health(db: AsyncSession, *, fix: bool = False) -> MaintenanceHealthRead:
    today = date.today()
    issues: list[MaintenanceHealthIssue] = []

    def add(code: str, count: int, detail: str, fixed: int = 0) -> None:
        if count:
            issues.append(MaintenanceHealthIssue(code=code, count=count, detail=detail, fixed=fixed))

    # 1. a running plan must point at a live order
    zombies = (
        await db.execute(
            select(MaintenancePlan, WorkOrder.status)
            .outerjoin(WorkOrder, WorkOrder.id == MaintenancePlan.work_order_id)
            .where(MaintenancePlan.status == "in_progress", or_(WorkOrder.id.is_(None), WorkOrder.status.in_(("completed", "cancelled"))))
            .with_for_update(of=MaintenancePlan)
        )
    ).all()
    fixed = 0
    if fix:
        for plan, order_status in zombies:
            if order_status == "completed":
                await finalize_completion(db, plan, completed_on=plan.completed_date or today)
            else:
                plan.status = "scheduled"
                plan.work_order_id = None
                plan.updated_at = _now()
                await log_decision(db, plan, "release", reason_code="health_fix", note="наряд отсутствует или отменён")
            fixed += 1
    add("running_plan_without_live_order", len(zombies), "in_progress plan whose work order is missing, cancelled or completed", fixed)

    # 2. plans of withdrawn assets should not stay open
    behaviors = {
        code: behavior for code, behavior in (await db.execute(select(FixedAssetStatus.code, FixedAssetStatus.behavior))).all()
    }
    withdrawn_codes = [code for code, behavior in behaviors.items() if behavior == "out_of_service"]
    withdrawn = (
        await db.execute(
            select(MaintenancePlan)
            .join(FixedAsset, FixedAsset.id == MaintenancePlan.asset_id)
            .where(
                MaintenancePlan.status.in_(("scheduled", "blocked")),
                or_(FixedAsset.status.in_(withdrawn_codes), FixedAsset.decommissioned_at.is_not(None)),
            )
            .with_for_update(of=MaintenancePlan)
        )
    ).scalars().all()
    fixed = 0
    if fix:
        for plan in withdrawn:
            plan.status = "cancelled"
            _clear_block(plan)
            plan.updated_at = _now()
            await log_decision(db, plan, "release", reason_code="asset_withdrawn", note="техника выведена из эксплуатации")
            fixed += 1
    add("open_plan_of_withdrawn_asset", len(withdrawn), "open plan of an out-of-service or decommissioned asset", fixed)

    # 3. more than one open plan for the same asset and interval
    dupes = (
        await db.execute(
            select(MaintenancePlan.asset_id, MaintenancePlan.interval_id, func.count())
            .where(MaintenancePlan.status.in_(OPEN_STATUSES))
            .group_by(MaintenancePlan.asset_id, MaintenancePlan.interval_id)
            .having(func.count() > 1)
        )
    ).all()
    add("duplicate_open_plans", len(dupes), "several open plans for one asset and interval (reported, not auto-fixed)")

    # 4. expired blocks and disruptions
    expired_blocks = (
        await db.execute(
            select(MaintenancePlan).where(
                MaintenancePlan.status == "blocked", MaintenancePlan.blocked_until < today
            ).with_for_update(of=MaintenancePlan)
        )
    ).scalars().all()
    fixed = 0
    if fix:
        for plan in expired_blocks:
            await unblock_plan(db, plan, None, note="срок блокировки истёк")
            fixed += 1
    add("expired_block", len(expired_blocks), "blocked plan whose 'until' date has passed", fixed)

    stale_disruptions = (
        await db.execute(
            select(MaintenanceDisruption).where(
                MaintenanceDisruption.status == "open", MaintenanceDisruption.ends_on < today
            ).with_for_update()
        )
    ).scalars().all()
    fixed = 0
    if fix:
        for disruption in stale_disruptions:
            await _release_disruption(db, disruption, None)
            fixed += 1
    add("expired_disruption", len(stale_disruptions), "open disruption whose end date has passed", fixed)

    if fix:
        await db.flush()
    return MaintenanceHealthRead(as_of=today, ok=not issues, issues=issues)


# ── the periodic job ─────────────────────────────────────────────────────────

async def snapshot_meters(db: AsyncSession, day: date) -> int:
    """Remember today's km/hours of every tracked asset: the history the pace is learned from."""
    rows = (
        await db.execute(
            select(FixedAsset.id, FixedAsset.mileage, func.max(WialonUnitRecord.cneh))
            .join(AssetSourceLink, and_(AssetSourceLink.asset_id == FixedAsset.id, AssetSourceLink.source == "wialon", AssetSourceLink.status == "active"))
            .join(WialonUnitRecord, WialonUnitRecord.unit_id == AssetSourceLink.external_id)
            .group_by(FixedAsset.id, FixedAsset.mileage)
        )
    ).all()
    for asset_id, mileage, hours in rows:
        values = dict(asset_id=asset_id, day=day, km=mileage, hours=hours if hours is not None and hours > 0 else None)
        await db.execute(
            insert(AssetMeterDaily).values(**values).on_conflict_do_update(index_elements=["asset_id", "day"], set_={"km": values["km"], "hours": values["hours"]})
        )
    return len(rows)


async def reconcile_all(db: AsyncSession) -> int:
    assets = await repository.list_schedule_assets(db)
    ctx = await obligations.load_context(db, assets)
    by_type: dict[str, list[MaintenanceInterval]] = {}
    created = 0
    for asset in assets:
        if asset.asset_type not in by_type:
            by_type[asset.asset_type] = await repository.list_active_intervals(db, asset.asset_type)
        if not by_type[asset.asset_type]:
            continue
        evaluated = obligations.evaluate_asset(asset, by_type[asset.asset_type], ctx)
        try:
            async with db.begin_nested():
                created += await obligations.persist_obligations(db, evaluated, ctx.today)
        except Exception:
            logger.exception("Could not reconcile maintenance plans for asset %s", asset.id)
    return created


_CYCLE_LOCK_KEY = "maintenance-cycle"


async def run_cycle(db: AsyncSession) -> dict[str, int]:
    """One pass of the hourly job: snapshots, expiry/zombie repair, then re-plan every asset.

    Everything runs in ONE transaction guarded by an advisory lock, so several app workers cannot
    run the pass at the same time (the others just skip it).
    """
    locked = await db.scalar(select(func.pg_try_advisory_xact_lock(func.hashtextextended(_CYCLE_LOCK_KEY, 0))))
    if not locked:
        return {"skipped": 1}
    today = date.today()
    snapshots = await snapshot_meters(db, today)
    obligations.reset_pace_book()
    health = await run_health(db, fix=True)
    created = await reconcile_all(db)
    await db.commit()
    return {"snapshots": snapshots, "health_fixed": sum(issue.fixed for issue in health.issues), "plans_created": created}


async def run_periodic_maintenance() -> None:
    """Background task started by the app: plans stay alive without anybody opening the page."""
    if not settings.maintenance_job_enabled:
        return
    interval = max(1, settings.maintenance_job_interval_minutes) * 60
    await asyncio.sleep(90)  # let the app and the Wialon/GTK pulls settle first
    while True:
        try:
            async with SessionFactory() as db:
                report = await run_cycle(db)
            logger.info("Maintenance cycle finished: %s", report)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Maintenance cycle failed; it will be retried")
        await asyncio.sleep(interval)


# ── bulk baseline import (passport / 1C data) ────────────────────────────────

async def import_baselines(db: AsyncSession, rows: list[dict[str, str]], *, apply: bool) -> dict:
    """Validate (and with apply=True write) baseline rows: inv_number, interval_code, done_at, odometer_km|km, hours, note.

    Dry-run by default: nothing is written, every row says what would happen. Rows are independent:
    a bad row is reported and skipped.
    """
    report: dict = {"rows": len(rows), "ok": 0, "errors": [], "applied": apply, "details": []}
    touched: dict[UUID, FixedAsset] = {}
    for number, row in enumerate(rows, start=2):  # row 1 of the file is the header
        def fail(reason: str) -> None:
            report["errors"].append({"row": number, "inv_number": row.get("inv_number"), "reason": reason})

        inv = (row.get("inv_number") or "").strip()
        code = (row.get("interval_code") or "").strip()
        if not inv or not code:
            fail("inv_number va interval_code majburiy")
            continue
        assets = (await db.execute(select(FixedAsset).where(FixedAsset.inv_number == inv))).scalars().all()
        if len(assets) != 1:
            fail("inventar raqam topilmadi" if not assets else "inventar raqam bir necha texnikaga mos")
            continue
        asset = assets[0]
        interval = next((i for i in await repository.list_active_intervals(db, asset.asset_type) if i.code == code), None)
        if interval is None:
            fail(f"'{code}' intervali bu texnika turiga mos emas")
            continue
        try:
            done_at = date.fromisoformat((row.get("done_at") or "").strip())
            km = Decimal(row["km"]) if (row.get("km") or "").strip() else None
            odometer = Decimal(row["odometer_km"]) if (row.get("odometer_km") or "").strip() else None
            hours = Decimal(row["hours"]) if (row.get("hours") or "").strip() else None
        except (ValueError, ArithmeticError):
            fail("done_at (YYYY-MM-DD) yoki son noto'g'ri")
            continue
        if done_at > date.today():
            fail("done_at kelajakda bo'lishi mumkin emas")
            continue
        try:
            if km is None and odometer is None and interval.interval_km is None:
                resolved = Decimal(asset.mileage or 0)
            else:
                resolved = await resolve_baseline_km(db, asset, km=km, odometer_km=odometer)
        except HTTPException as exc:
            fail(str(exc.detail))
            continue
        report["ok"] += 1
        report["details"].append(
            {"inv_number": inv, "interval": code, "done_at": done_at.isoformat(), "toir_km": str(resolved),
             "used_since": str(Decimal(asset.mileage or 0) - resolved)}
        )
        if apply:
            await upsert_baseline(
                db, asset_id=asset.id, interval_id=interval.id, done_at=done_at, km=resolved, hours=hours,
                source="import", note=row.get("note"),
            )
            touched[asset.id] = asset
    if apply:
        for asset in touched.values():
            await obligations.reconcile_asset(db, asset)
        await db.commit()
    return report


# ── shadow report: what the engine sees, without writing anything ─────────────

async def shadow_report(db: AsyncSession) -> dict:
    ctx, obs = await evaluate_all(db)
    from collections import Counter

    existing = {
        (asset_id, interval_id)
        for asset_id, interval_id in (
            await db.execute(select(MaintenancePlan.asset_id, MaintenancePlan.interval_id).where(MaintenancePlan.status.in_(OPEN_STATUSES)))
        ).all()
    }
    paces = sorted(float(ob.pace_km.p50) for ob in obs if ob.pace_km is not None and ob.pace_km.reliable)
    would_create = [ob for ob in obs if ob.plan is None and ob.markers.state != "forecast" and not ob.paused]
    soon = sorted(
        (ob for ob in obs if ob.markers.date_p75 is not None and ob.markers.state != "forecast"),
        key=lambda ob: -ob.priority.score,
    )
    return {
        "as_of": ctx.today.isoformat(),
        "obligations": len(obs),
        "assets_with_obligations": len({ob.asset.id for ob in obs}),
        "by_state": dict(Counter(ob.markers.state for ob in obs)),
        "by_confidence": dict(Counter(ob.confidence for ob in obs)),
        "by_baseline_source": dict(Counter(ob.baseline_source for ob in obs)),
        "by_pace_source": dict(Counter(ob.pace_km.source for ob in obs if ob.pace_km is not None)),
        "by_interval": dict(Counter(ob.interval.code for ob in obs)),
        "limiting_meter": dict(Counter(ob.markers.limiting for ob in obs)),
        "paused_in_shop": sum(1 for ob in obs if ob.paused),
        "open_plans_now": len(existing),
        "plans_the_engine_would_create_now": len(would_create),
        "median_reliable_pace_km_per_day": round(paces[len(paces) // 2], 1) if paces else None,
        "reliable_pace_assets": len(paces),
        "default_pace_km_per_day": str(ctx.default_pace),
        "top_priority": [
            {
                "inv_number": ob.asset.inv_number, "interval": ob.interval.code, "state": ob.markers.state,
                "priority": ob.priority.score, "date_early": ob.markers.date_p75.isoformat(),
                "confidence": ob.confidence, "why": ob.priority.why[:3],
            }
            for ob in soon[:15]
        ],
    }
