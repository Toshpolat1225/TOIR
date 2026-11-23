"""Loads the facts and evaluates every (asset x interval) obligation with the pure engine.

`load_context` reads once what the evaluation needs (pace history, baselines, open plans, data
freshness...); `evaluate_asset` is synchronous and deterministic; `persist_obligations` writes the
plans whose planning window is open. get_schedule and reconcile_asset_plans both build on this.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import and_, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import LOCAL_TZ, today_local
from app.core.config import settings
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset, MileageHistory
from app.models.maintenance import (
    AssetMaintenanceBaseline,
    AssetMeterDaily,
    MaintenanceDisruption,
    MaintenanceInterval,
    MaintenancePlan,
)
from app.models.wialon_units import WialonUnitRecord
from app.models.localization import FixedAssetStatus
from app.models.mileage import WagonMileageLedger, WagonMileageOpeningBalance, WialonRawReceipt
from app.models.work_orders import WorkOrder
from app.repositories import maintenance as repository
from app.repositories import mileage as mileage_repository
from app.services.maintenance_engine import (
    CalendarInput,
    Markers,
    MeterInput,
    ObligationDraft,
    Pace,
    Priority,
    compute_markers,
    confidence,
    daily_deltas,
    estimate_pace,
    group_pace,
    merge_visits,
    own_pace,
    partial_day_rates,
    priority_score,
)
from app.services import avg_daily_mileage
from app.services.maintenance_planning import next_mileage_threshold

ZERO = Decimal("0")


def _local_day(column):
    """The Tashkent calendar day of a timestamptz column. The zone is a SQL literal, not a bound parameter, so that
    the SELECT and GROUP BY expressions are textually identical (PostgreSQL would not match two different $n)."""
    return func.date(func.timezone(literal_column("'Asia/Tashkent'"), column))
REPAIR_BEHAVIORS = frozenset({"repair", "maintenance"})  # the unit is in the shop: planning pauses
WITHDRAWN_BEHAVIORS = frozenset({"out_of_service"})  # withdrawn from service: no obligations at all
OPEN_PLAN_STATUSES = ("scheduled", "in_progress", "blocked")
CLOSED_PLAN_STATUSES = ("completed", "covered", "waived")
_PACE_BOOK_TTL_SECONDS = 20 * 60
# A group needs this many observed days per member before it can stand in for a unit without data. Wagons only
# have the ledger (a few days), so a group of wagons is allowed to form earlier than a group of locomotives.
_GROUP_MIN_DAYS = {"wagon": 1}
_GROUP_MIN_DAYS_DEFAULT = 3


# ── pace history ─────────────────────────────────────────────────────────────

@dataclass
class PaceBook:
    day: date
    built_at: float
    km_deltas: dict[UUID, list[Decimal]]
    hours_deltas: dict[UUID, list[Decimal]]
    group_km: dict[str, Pace | None]
    group_hours: dict[str, Pace | None]
    section_norms: dict[tuple[UUID, str], Decimal] = field(default_factory=dict)  # (section, type) -> reliable avg km/day (>= 3 units with GPS data)


_book: PaceBook | None = None


def reset_pace_book() -> None:
    global _book
    _book = None


async def get_pace_book(db: AsyncSession, today: date, *, force: bool = False) -> PaceBook:
    global _book
    if (
        not force
        and _book is not None
        and _book.day == today
        and time.monotonic() - _book.built_at < _PACE_BOOK_TTL_SECONDS
    ):
        return _book
    _book = await _build_pace_book(db, today)
    return _book


async def _build_pace_book(db: AsyncSession, today: date) -> PaceBook:
    window = settings.maintenance_pace_window_days
    start = today - timedelta(days=window)
    anchor_day = start - timedelta(days=1)
    last_day = today - timedelta(days=1)  # today is a partial day and would bias the pace low
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=LOCAL_TZ)

    km_series: dict[UUID, list[tuple[date, Decimal]]] = {}
    hours_series: dict[UUID, list[tuple[date, Decimal]]] = {}

    history = await db.execute(
        select(
            MileageHistory.asset_id,
            _local_day(MileageHistory.recorded_at).label("day"),
            func.max(MileageHistory.mileage),
        )
        .where(MileageHistory.recorded_at >= start_dt)
        .group_by(MileageHistory.asset_id, _local_day(MileageHistory.recorded_at))
    )
    for asset_id, day, value in history.all():
        km_series.setdefault(asset_id, []).append((day, Decimal(value)))
    before = await db.execute(
        select(MileageHistory.asset_id, func.max(MileageHistory.mileage))
        .where(MileageHistory.recorded_at < start_dt)
        .group_by(MileageHistory.asset_id)
    )
    for asset_id, value in before.all():
        if asset_id in km_series:  # anchor the first in-window delta to the value just before the window
            km_series[asset_id].append((anchor_day, Decimal(value)))

    snapshots = await db.execute(
        select(AssetMeterDaily.asset_id, AssetMeterDaily.day, AssetMeterDaily.km, AssetMeterDaily.hours).where(
            AssetMeterDaily.day >= anchor_day
        )
    )
    for asset_id, day, km, hours in snapshots.all():
        if km is not None:
            km_series.setdefault(asset_id, []).append((day, Decimal(km)))
        if hours is not None:
            hours_series.setdefault(asset_id, []).append((day, Decimal(hours)))

    unobserved = await _unobserved_days(db, anchor_day, last_day)
    km_deltas = {
        asset_id: daily_deltas(series, first_day=anchor_day, last_day=last_day, unobserved_days=unobserved)
        for asset_id, series in km_series.items()
    }
    # Wagon mileage is a ledger projection, not a counter that is sampled: pace comes from the ledger.
    km_deltas.update(await _wagon_ledger_rates(db, start_dt))
    hours_deltas = {
        asset_id: daily_deltas(series, first_day=anchor_day, last_day=last_day, unobserved_days=unobserved)
        for asset_id, series in hours_series.items()
    }
    ids = set(km_deltas) | set(hours_deltas)
    types: dict[UUID, str] = {}
    if ids:
        types = {
            row[0]: row[1]
            for row in (
                await db.execute(select(FixedAsset.id, FixedAsset.asset_type).where(FixedAsset.id.in_(ids)))
            ).all()
        }

    def groups(deltas: dict[UUID, list[Decimal]], min_days: dict[str, int] | None = None) -> dict[str, Pace | None]:
        by_type: dict[str, list[Pace]] = {}
        for asset_id, values in deltas.items():
            own = own_pace(values)
            if own is not None and asset_id in types:
                by_type.setdefault(types[asset_id], []).append(own)
        return {
            asset_type: group_pace(paces, min_days=(min_days or {}).get(asset_type, _GROUP_MIN_DAYS_DEFAULT))
            for asset_type, paces in by_type.items()
        }

    norms = {
        (row["section_id"], row["asset_type"]): row["avg_daily_km"]
        for row in await avg_daily_mileage.compute(db)
        if row["avg_daily_km"] is not None and row["with_data_count"] >= avg_daily_mileage.MIN_NORM_UNITS
    }
    return PaceBook(
        day=today, built_at=time.monotonic(), km_deltas=km_deltas, hours_deltas=hours_deltas,
        group_km=groups(km_deltas, _GROUP_MIN_DAYS), group_hours=groups(hours_deltas), section_norms=norms,
    )


_MIN_COLLECTOR_HOURS = 12  # a day with Wialon data in fewer hours than this was not really observed


async def _unobserved_days(db: AsyncSession, first_day: date, last_day: date) -> frozenset[date]:
    """Days between the first one we ever received Wialon data and `last_day` on which the collector ran in
    fewer than _MIN_COLLECTOR_HOURS distinct hours (host switched off, network down...). Empty when there is
    no receipt history at all, so a fresh install or a push-only setup is judged as before."""
    start_dt = datetime.combine(first_day, datetime.min.time(), tzinfo=LOCAL_TZ)
    rows = (
        await db.execute(
            select(
                _local_day(WialonRawReceipt.received_at),
                func.count(func.distinct(func.date_trunc("hour", WialonRawReceipt.received_at))),
            )
            .where(WialonRawReceipt.received_at >= start_dt)
            .group_by(_local_day(WialonRawReceipt.received_at))
        )
    ).all()
    if not rows:
        return frozenset()
    hours_by_day = {day: int(hours) for day, hours in rows}
    first_seen = min(hours_by_day)
    result: set[date] = set()
    day = max(first_day, first_seen)
    while day <= last_day:
        if hours_by_day.get(day, 0) < _MIN_COLLECTOR_HOURS:
            result.add(day)
        day += timedelta(days=1)
    return frozenset(result)


async def _wagon_ledger_rates(db: AsyncSession, start_dt: datetime) -> dict[UUID, list[Decimal]]:
    """Daily km rates of every wagon with an approved projection, from the wagon ledger.

    The ledger covers [first computed period, last computed period]; time inside that window without km is
    idle, time outside it is unknown (not idle). Only eligible CONFIRMED/ESTIMATED km count, as in the
    projection itself.
    """
    approved = select(WagonMileageOpeningBalance.asset_id).where(WagonMileageOpeningBalance.status == "approved")
    coverage = (
        await db.execute(
            select(func.min(WagonMileageLedger.period_from), func.max(WagonMileageLedger.period_to)).where(
                WagonMileageLedger.period_from >= start_dt
            )
        )
    ).one()
    if coverage[0] is None:
        return {}
    day_km: dict[UUID, dict[date, Decimal]] = {}
    rows = await db.execute(
        select(
            WagonMileageLedger.wagon_asset_id,
            _local_day(WagonMileageLedger.period_from),
            func.sum(WagonMileageLedger.distance_km),
        )
        .where(
            WagonMileageLedger.status == "active",
            WagonMileageLedger.calculation_eligible.is_(True),
            WagonMileageLedger.classification.in_(("CONFIRMED", "ESTIMATED")),
            WagonMileageLedger.period_from >= start_dt,
            WagonMileageLedger.wagon_asset_id.in_(approved),
        )
        .group_by(WagonMileageLedger.wagon_asset_id, _local_day(WagonMileageLedger.period_from))
    )
    for wagon_id, day, km in rows.all():
        day_km.setdefault(wagon_id, {})[day] = Decimal(km)
    wagons = (await db.scalars(approved)).all()
    return {
        wagon_id: partial_day_rates(day_km.get(wagon_id, {}), coverage[0], coverage[1]) for wagon_id in wagons
    }


# ── context ──────────────────────────────────────────────────────────────────

@dataclass
class Context:
    today: date
    now: datetime
    default_pace: Decimal
    default_source: str
    book: PaceBook
    baselines: dict[tuple[UUID, UUID], AssetMaintenanceBaseline]
    open_plans: dict[tuple[UUID, UUID], MaintenancePlan]
    closed_triggers: dict[tuple[UUID, UUID], Decimal]
    last_data_at: dict[UUID, datetime | None]  # only assets that have an active Wialon link
    hours_current: dict[UUID, Decimal]
    trusted_wagons: set[UUID]
    assets_in_shop: set[UUID]  # assets that have an order being worked on right now
    sensor_failure: set[UUID]
    behavior_of_status: dict[str, str] = field(default_factory=dict)  # status code -> behavior
    estimated_wagons: set[UUID] = field(default_factory=set)  # wagon km that include ESTIMATED ledger km

    def behavior(self, asset: FixedAsset) -> str:
        return self.behavior_of_status.get(asset.status, "operational")

    def pace_km(self, asset: FixedAsset) -> Pace:
        deltas = self.book.km_deltas.get(asset.id, [])
        if not deltas:
            # no GPS history of its own: no invented pace -> no date (the unit stays in «Без прогноза»)
            return Pace(ZERO, ZERO, ZERO, 0, "none")
        norm = self.book.section_norms.get((asset.section_id, asset.asset_type)) if asset.section_id is not None else None
        group = Pace(norm, norm, norm, 0, "norm") if norm is not None else self.book.group_km.get(asset.asset_type)
        if group is None or len(deltas) >= settings.maintenance_pace_min_days:
            # enough own days (or nothing reliable to compare with): its own pace as it is - a parked unit is not pulled
            # toward the norm, and never toward a flat guess like 200 km/day
            own = own_pace(deltas)
            return Pace(own.p25, own.p50, own.p75, own.n_days, "asset" if own.n_days >= settings.maintenance_pace_min_days else "blend")
        return estimate_pace(
            deltas,
            group=group,
            fallback_per_day=self.default_pace,
            fallback_source=self.default_source,
            min_days=settings.maintenance_pace_min_days,
            shrink_k=settings.maintenance_pace_shrink_k,
        )

    def pace_hours(self, asset: FixedAsset) -> Pace | None:
        deltas = self.book.hours_deltas.get(asset.id, [])
        if not deltas:
            return None
        return estimate_pace(
            deltas,
            group=self.book.group_hours.get(asset.asset_type),
            fallback_per_day=Decimal("10"),
            fallback_source="default",
            min_days=settings.maintenance_pace_min_days,
            shrink_k=settings.maintenance_pace_shrink_k,
        )

    def is_stale(self, asset: FixedAsset) -> bool:
        if asset.id in self.sensor_failure:
            return True
        if asset.id not in self.last_data_at:
            return False  # no tracker, so no freshness signal to judge by
        last = self.last_data_at[asset.id]
        return last is None or self.now - last > timedelta(hours=settings.maintenance_stale_hours)


async def load_context(
    db: AsyncSession, assets: list[FixedAsset], *, today: date | None = None, now: datetime | None = None
) -> Context:
    today = today or today_local()
    now = now or datetime.now(timezone.utc)
    ids = [asset.id for asset in assets]
    setting_row = await repository.get_settings(db)
    if setting_row is not None and setting_row.daily_average_km is not None:
        default_pace, default_source = Decimal(setting_row.daily_average_km), "setting"
    else:
        default_pace, default_source = Decimal(settings.daily_km_estimate), "default"
    book = await get_pace_book(db, today)
    behavior_of_status = {
        code: behavior for code, behavior in (await db.execute(select(FixedAssetStatus.code, FixedAssetStatus.behavior))).all()
    }

    baselines: dict[tuple[UUID, UUID], AssetMaintenanceBaseline] = {}
    open_plans: dict[tuple[UUID, UUID], MaintenancePlan] = {}
    closed_triggers: dict[tuple[UUID, UUID], Decimal] = {}
    last_data_at: dict[UUID, datetime | None] = {}
    hours_current: dict[UUID, Decimal] = {}
    trusted_wagons: set[UUID] = set()
    estimated_wagons: set[UUID] = set()
    assets_in_shop: set[UUID] = set()
    sensor_failure: set[UUID] = set()
    if ids:
        for row in (await db.execute(select(AssetMaintenanceBaseline).where(AssetMaintenanceBaseline.asset_id.in_(ids)))).scalars():
            baselines[(row.asset_id, row.interval_id)] = row
        plans = (
            await db.execute(
                select(MaintenancePlan)
                .where(MaintenancePlan.asset_id.in_(ids), MaintenancePlan.status.in_(OPEN_PLAN_STATUSES))
                .order_by(MaintenancePlan.trigger_mileage.asc().nullslast(), MaintenancePlan.created_at.asc())
            )
        ).scalars()
        for plan in plans:
            open_plans.setdefault((plan.asset_id, plan.interval_id), plan)  # the oldest unfulfilled one
        for asset_id, interval_id, trigger in (
            await db.execute(
                select(MaintenancePlan.asset_id, MaintenancePlan.interval_id, func.max(MaintenancePlan.trigger_mileage))
                .where(
                    MaintenancePlan.asset_id.in_(ids),
                    MaintenancePlan.status.in_(CLOSED_PLAN_STATUSES),
                    MaintenancePlan.trigger_mileage.is_not(None),
                )
                .group_by(MaintenancePlan.asset_id, MaintenancePlan.interval_id)
            )
        ).all():
            closed_triggers[(asset_id, interval_id)] = Decimal(trigger)
        for asset_id, last_message, cneh in (
            await db.execute(
                select(AssetSourceLink.asset_id, func.max(WialonUnitRecord.last_message_at), func.max(WialonUnitRecord.cneh))
                .join(WialonUnitRecord, WialonUnitRecord.unit_id == AssetSourceLink.external_id)
                .where(
                    AssetSourceLink.asset_id.in_(ids),
                    AssetSourceLink.source == "wialon",
                    AssetSourceLink.status == "active",
                )
                .group_by(AssetSourceLink.asset_id)
            )
        ).all():
            last_data_at[asset_id] = last_message
            if cneh is not None and cneh > 0:
                hours_current[asset_id] = Decimal(cneh)
        wagon_ids = [asset.id for asset in assets if asset.asset_type == "wagon"]
        if wagon_ids:
            # decision D9: a wagon's km are trusted once its projection is approved (approved opening balance)
            trusted_wagons = await mileage_repository.approved_projection_asset_ids(db, wagon_ids)
            estimated_wagons = await mileage_repository.estimated_projection_asset_ids(db, trusted_wagons)
        assets_in_shop = set(
            (
                await db.scalars(
                    select(WorkOrder.fixed_asset_id).where(
                        WorkOrder.fixed_asset_id.in_(ids), WorkOrder.status == "in_progress"
                    )
                )
            ).all()
        )
        failures = (
            await db.execute(
                select(MaintenanceDisruption.scope, MaintenanceDisruption.asset_id, MaintenanceDisruption.section_id).where(
                    MaintenanceDisruption.kind == "sensor_failure",
                    MaintenanceDisruption.status == "open",
                    MaintenanceDisruption.starts_on <= today,
                    (MaintenanceDisruption.ends_on.is_(None)) | (MaintenanceDisruption.ends_on >= today),
                )
            )
        ).all()
        for scope, asset_id, section_id in failures:
            for asset in assets:
                if scope == "all" or (scope == "asset" and asset.id == asset_id) or (
                    scope == "section" and asset.section_id == section_id
                ):
                    sensor_failure.add(asset.id)
    return Context(
        today=today, now=now, default_pace=default_pace, default_source=default_source, book=book,
        baselines=baselines, open_plans=open_plans, closed_triggers=closed_triggers, last_data_at=last_data_at,
        hours_current=hours_current, trusted_wagons=trusted_wagons, assets_in_shop=assets_in_shop,
        sensor_failure=sensor_failure, behavior_of_status=behavior_of_status, estimated_wagons=estimated_wagons,
    )


# ── evaluation ───────────────────────────────────────────────────────────────

@dataclass
class Obligation:
    asset: FixedAsset
    interval: MaintenanceInterval
    plan: MaintenancePlan | None  # the open plan of this cycle, if one exists
    baseline_source: str  # 'provisional' = guessed from the grid; otherwise a real baseline
    baseline_km: Decimal | None
    due_km: Decimal | None
    markers: Markers
    pace: Pace  # of the limiting meter
    confidence: str
    paused: bool
    planned_date: date | None
    merged_into: UUID | None
    priority: Priority
    urgency: str | None
    opportunistic: bool = False
    pace_km: Pace | None = None
    mileage_estimated: bool = False  # the km behind this obligation are an estimate, not a measurement
    rebased: bool = False  # the open plan's cycle was inconsistent with the interval and was moved to the grid

    @property
    def key(self) -> tuple[UUID, UUID]:
        return (self.asset.id, self.interval.id)


def urgency_of(markers: Markers, lead_days: int) -> str | None:
    if markers.state in ("over_limit", "over_tolerance"):
        return "high"
    if markers.date_p75 is None:
        return None
    days = (markers.date_p75 - markers.as_of).days
    if days <= max(1, -(-lead_days // 3)):
        return "high"
    if days <= lead_days:
        return "medium"
    if days <= 2 * lead_days:
        return "low"
    return None


def evaluate_asset(
    asset: FixedAsset,
    intervals: Iterable[MaintenanceInterval],
    ctx: Context,
    mileage: Decimal | None = None,
) -> list[Obligation]:
    """Every obligation of one asset. Withdrawn assets have none; assets in the shop are paused.

    `mileage` overrides `asset.mileage` (a caller that has just learned a newer value).
    """
    current_km = Decimal(mileage if mileage is not None else asset.mileage) if (
        mileage is not None or asset.mileage is not None
    ) else None
    behavior = ctx.behavior(asset)
    if behavior in WITHDRAWN_BEHAVIORS or asset.decommissioned_at is not None:
        return []
    paused = behavior in REPAIR_BEHAVIORS
    stale = ctx.is_stale(asset)
    km_pace = ctx.pace_km(asset)
    hours_pace = ctx.pace_hours(asset)
    stopped = Pace(ZERO, ZERO, ZERO, km_pace.n_days, "asset")

    raw: list[Obligation] = []
    drafts: list[ObligationDraft] = []
    for interval in intervals:
        if not interval.is_active or asset.asset_type not in interval.asset_types:
            continue
        key = (asset.id, interval.id)
        baseline = ctx.baselines.get(key)
        explicit = baseline is not None and baseline.source != "provisional"
        plan = ctx.open_plans.get(key)
        meters: list[MeterInput] = []
        baseline_km: Decimal | None = None
        due_km: Decimal | None = None
        rebased = False
        source = baseline.source if explicit else "provisional"

        wagon_ok = asset.asset_type != "wagon" or asset.id in ctx.trusted_wagons
        if interval.interval_km is not None and current_km is not None and wagon_ok:
            limit = Decimal(interval.interval_km)
            if explicit:
                baseline_km = Decimal(baseline.km)
            elif plan is not None and plan.trigger_mileage is not None:
                baseline_km = Decimal(plan.trigger_mileage) - limit  # the cycle the open plan stands for
                if baseline_km > current_km:
                    # That cycle has not even started: the plan was made when the interval had another length.
                    # Keeping it would show a limit hundreds of km away; count from the current grid instead.
                    trigger = next_mileage_threshold(current_km, limit)
                    baseline_km = trigger - limit if trigger is not None else None
                    rebased = baseline_km is not None
            else:
                trigger = next_mileage_threshold(current_km, limit)
                baseline_km = trigger - limit if trigger is not None else None
                closed = ctx.closed_triggers.get(key)
                if baseline_km is not None and closed is not None and closed > baseline_km:
                    baseline_km = closed  # that cycle is already closed (done, covered or waived)
            if baseline_km is not None:
                due_km = baseline_km + limit
                meters.append(MeterInput("km", limit, baseline_km, current_km, stopped if paused else km_pace))
        if (
            interval.interval_hours is not None
            and explicit
            and baseline.hours is not None
            and asset.id in ctx.hours_current
        ):
            meters.append(
                MeterInput(
                    "hours", Decimal(interval.interval_hours), Decimal(baseline.hours), ctx.hours_current[asset.id],
                    stopped if paused or hours_pace is None else hours_pace,
                )
            )
        calendar = None
        if interval.interval_days is not None and explicit and baseline.done_at is not None:
            calendar = CalendarInput(interval.interval_days, baseline.done_at)
        if not meters and calendar is None:
            continue

        markers = compute_markers(
            ctx.today, meters, calendar, tolerance_pct=Decimal(interval.tolerance_pct), lead_days=interval.lead_days
        )
        limiting_pace = hours_pace if markers.limiting == "hours" and hours_pace is not None else km_pace
        reliable = Pace(ZERO, ZERO, ZERO, 99, "asset") if markers.limiting == "days" else limiting_pace
        days_to_limit = (markers.date_p75 - ctx.today).days if markers.date_p75 is not None else None
        health = float(asset.failure_probability) if asset.failure_probability is not None else None
        priority = priority_score(
            days_to_limit=days_to_limit,
            pace_p75=None if markers.limiting == "days" else limiting_pace.p75,
            health=health,
            deferrals=plan.deferral_count if plan is not None else 0,
            ready=None,
            baseline_provisional=source == "provisional",
        )
        opportunistic = (
            asset.id in ctx.assets_in_shop
            and markers.state == "forecast"
            and markers.limit > 0
            and markers.used / markers.limit * 100 >= settings.maintenance_min_early_pct
        )
        mileage_estimated = (
            asset.asset_type == "wagon" and asset.id in ctx.estimated_wagons and markers.limiting == "km"
        )
        raw.append(
            Obligation(
                asset=asset, interval=interval, plan=plan, baseline_source=source, baseline_km=baseline_km, due_km=due_km,
                markers=markers, pace=limiting_pace, confidence=confidence(baseline_source=source, pace=reliable, stale=stale, estimated=mileage_estimated),
                paused=paused, planned_date=markers.date_p75, merged_into=None, priority=priority,
                urgency=urgency_of(markers, interval.lead_days), opportunistic=opportunistic, pace_km=km_pace,
                mileage_estimated=mileage_estimated, rebased=rebased,
            )
        )
        drafts.append(
            ObligationDraft(
                key=interval.id, rank=interval.rank,
                limit_km=Decimal(interval.interval_km) if interval.interval_km is not None else None, markers=markers,
            )
        )

    merge_visits(drafts, merge_pct=Decimal(settings.maintenance_merge_pct))
    by_key = {draft.key: draft for draft in drafts}
    for obligation in raw:
        draft = by_key[obligation.interval.id]
        obligation.planned_date = draft.planned_date
        obligation.merged_into = draft.merged_into  # type: ignore[assignment]
    return raw


# ── persistence ──────────────────────────────────────────────────────────────

async def persist_obligations(db: AsyncSession, obligations: Iterable[Obligation], today: date) -> int:
    """Create or refresh the plan of every obligation. Returns the number of new plans.

    A plan is created only once its planning window is open; an existing, still-scheduled plan keeps
    following the forecast (unless the planner pinned its date by hand).
    """
    created = 0
    for ob in obligations:
        plan = ob.plan
        planned = ob.planned_date or today
        if plan is None:
            if ob.paused or ob.markers.state == "forecast":
                continue  # nothing to plan yet (or the unit is in the shop)
            plan, was_created = await repository.upsert_scheduled_plan_with_created(
                db, asset_id=ob.asset.id, interval_id=ob.interval.id, trigger_mileage=ob.due_km, scheduled_date=planned
            )
            if was_created:
                created += 1
            elif plan.status == "cancelled":
                # an obligation is never lost: a voided twin of this cycle comes back to life
                plan.status = "scheduled"
                plan.scheduled_date = planned
                plan.updated_at = datetime.now(timezone.utc)
                created += 1
            continue
        if ob.paused or plan.status != "scheduled":
            continue  # running or blocked plans are not rewritten by the forecast
        changed = False
        if plan.scheduled_date_manual:
            if plan.recommended_date != planned:
                plan.recommended_date = planned  # the planner's date stays; the recommendation keeps moving
                changed = True
        elif plan.scheduled_date != planned:
            plan.scheduled_date = planned
            changed = True
        if (
            ob.due_km is not None
            and plan.trigger_mileage != ob.due_km
            and (ob.baseline_source != "provisional" or ob.rebased)
            and await repository.get_plan_for_trigger(db, ob.asset.id, ob.interval.id, ob.due_km) is None
        ):
            plan.trigger_mileage = ob.due_km  # an imported/completed baseline moved the cycle
            changed = True
        if changed:  # an untouched plan must stay untouched: every write is also an audit event, once an hour per plan
            plan.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return created


async def evaluate_for_asset(
    db: AsyncSession, asset: FixedAsset, *, today: date | None = None
) -> tuple[Context, list[Obligation]]:
    intervals = await repository.list_active_intervals(db, asset.asset_type)
    ctx = await load_context(db, [asset], today=today)
    return ctx, evaluate_asset(asset, intervals, ctx)


async def reconcile_asset(db: AsyncSession, asset: FixedAsset, mileage: Decimal | None = None) -> int:
    """Re-evaluate one asset and create/refresh its plans. Returns the number of new plans."""
    intervals = await repository.list_active_intervals(db, asset.asset_type)
    if not intervals:
        return 0
    ctx = await load_context(db, [asset])
    return await persist_obligations(db, evaluate_asset(asset, intervals, ctx, mileage), ctx.today)
