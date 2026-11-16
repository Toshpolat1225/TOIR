from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MaintenancePlanStatus = Literal[
    "scheduled", "in_progress", "completed", "cancelled", "blocked", "covered", "waived"
]
# What a client may ask for through PATCH: the rest are reached through dedicated actions
# (block / unblock / waive) or by the system itself (covered, cancelled).
MaintenancePlanRequestedStatus = Literal["scheduled", "in_progress", "completed", "cancelled"]
MaintenanceDisplayStatus = Literal[
    "upcoming", "in_progress", "completed", "overdue", "blocked"
]
BlockReason = Literal[
    "parts", "no_bay", "no_crew", "unit_unavailable", "accident", "unplanned_repair",
    "sensor_failure", "weather", "other",
]
DisruptionScope = Literal["asset", "section", "all"]
MaintenanceConfidence = Literal["high", "low", "stale"]
MaintenanceUrgency = Literal["high", "medium", "low"]


class MaintenanceSettingsRead(BaseModel):
    daily_average_km: Decimal | None


class MaintenanceSettingsUpdate(BaseModel):
    daily_average_km: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class MaintenancePlanUpdate(BaseModel):
    status: MaintenancePlanRequestedStatus | None = None
    completed_date: date | None = None
    work_order_id: UUID | None = None
    # Manual rescheduling. `scheduled_date` moves the planned day; `reset_schedule` returns to the
    # system recommendation. Neither can be combined with the fields above.
    scheduled_date: date | None = None
    reschedule_reason: str | None = Field(default=None, max_length=500)
    reset_schedule: bool = False


class MaintenancePlanBlock(BaseModel):
    """Put a plan on hold. The obligation itself is never dropped: it keeps growing while blocked."""

    reason_code: BlockReason
    until: date | None = None
    note: str | None = Field(default=None, max_length=500)


class MaintenancePlanWaive(BaseModel):
    """An admin decision that this cycle is not needed (e.g. replaced by a higher service)."""

    reason: str = Field(min_length=3, max_length=500)


class MaintenancePlanFromForecast(BaseModel):
    """Turn a forecast row into a real plan on a date chosen by the planner."""

    asset_id: UUID
    interval_id: UUID
    scheduled_date: date
    reschedule_reason: str | None = Field(default=None, max_length=500)


class MaintenancePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    asset_name: str
    asset_inv_number: str
    section_id: UUID | None
    interval_id: UUID
    interval_code: str
    interval_name: str
    work_type_id: UUID | None
    urgency: MaintenanceUrgency | None = None
    status: MaintenancePlanStatus
    trigger_mileage: Decimal | None
    scheduled_date: date | None
    completed_date: date | None
    work_order_id: UUID | None
    scheduled_date_manual: bool = False
    recommended_date: date | None = None
    reschedule_reason: str | None = None
    blocked_reason: str | None = None
    blocked_until: date | None = None
    blocked_note: str | None = None
    deferral_count: int = 0


class MaintenanceScheduleItem(BaseModel):
    id: str
    entity_type: Literal["work_order", "maintenance_plan", "forecast"]
    unit: str
    type: str
    startDate: date
    durationH: int = 8
    depot: str
    tech: str
    status: MaintenanceDisplayStatus
    note: str | None = None
    mileage: Decimal | None = None
    remainingKm: Decimal | None = None
    nextThreshold: Decimal | None = None
    # Length of the interval (km) the threshold belongs to; lets the UI show progress
    # inside the CURRENT interval instead of against the absolute odometer value.
    intervalKm: Decimal | None = None
    urgency: MaintenanceUrgency | None = None
    asset_id: UUID
    section_id: UUID | None = None
    interval_id: UUID | None = None
    work_type_id: UUID | None = None
    plan_id: UUID | None = None
    work_order_id: UUID | None = None
    # Joined display data of the asset (names instead of codes); the same for every item of one asset.
    asset_type: str | None = None
    asset_type_name: str | None = None
    asset_model: str | None = None
    asset_serial: str | None = None
    asset_inv_number: str | None = None
    asset_status: str | None = None
    asset_status_name: str | None = None
    asset_online: bool | None = None
    # Manual rescheduling state of a plan (always False/None for forecasts and work orders).
    dateManual: bool = False
    recommendedDate: date | None = None
    rescheduleReason: str | None = None
    # The living-plan model (None for work orders): raw plan status, what limits the unit, the three
    # date markers, the pace behind them and how far to trust the forecast.
    planStatus: MaintenancePlanStatus | None = None
    state: Literal["forecast", "due_soon", "over_limit", "over_tolerance"] | None = None
    rank: int | None = None
    limiting: Literal["km", "hours", "days"] | None = None
    limitingUsed: Decimal | None = None
    limitingLimit: Decimal | None = None
    tolerance: Decimal | None = None
    windowOpen: date | None = None
    dateEarly: date | None = None  # cautious (fast pace): when to act by
    dateTypical: date | None = None
    dateLate: date | None = None  # slow pace
    paceKmPerDay: Decimal | None = None
    paceFastKmPerDay: Decimal | None = None  # the cautious (p75) pace: what an approval is judged by
    paceSource: str | None = None
    paceDays: int | None = None
    confidence: MaintenanceConfidence | None = None
    baselineSource: str | None = None
    priority: int | None = None
    priorityWhy: list[str] = Field(default_factory=list)
    blockedReason: str | None = None
    blockedUntil: date | None = None
    blockedNote: str | None = None
    deferralCount: int = 0
    mergedInto: UUID | None = None
    opportunistic: bool = False
    paused: bool = False
    mileageEstimated: bool = False  # wagon km that include ESTIMATED km: the forecast is approximate


class MaintenanceScheduleRead(BaseModel):
    schedule: list[MaintenanceScheduleItem]
    daily_average_km: Decimal | None


# ── baselines, disruptions, decisions, KPIs ───────────────────────────────────

BaselineSource = Literal["provisional", "import", "completed", "manual", "waived"]
DecisionKind = Literal["reschedule", "block", "unblock", "waive", "cover", "release"]


class MaintenanceBaselineUpsert(BaseModel):
    """When a service was last done. Give the km in the TOIR scale OR the real odometer reading."""

    asset_id: UUID
    interval_id: UUID
    done_at: date
    km: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    odometer_km: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    hours: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    note: str | None = Field(default=None, max_length=500)


class MaintenanceBaselineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    interval_id: UUID
    done_at: date | None
    km: Decimal
    hours: Decimal | None
    source: BaselineSource
    note: str | None = None
    work_order_id: UUID | None = None
    updated_at: datetime | None = None


class MaintenanceDisruptionCreate(BaseModel):
    kind: BlockReason
    scope: DisruptionScope
    asset_id: UUID | None = None
    section_id: UUID | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    note: str | None = Field(default=None, max_length=500)


class MaintenanceDisruptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    scope: DisruptionScope
    asset_id: UUID | None
    section_id: UUID | None
    starts_on: date
    ends_on: date | None
    status: Literal["open", "closed"]
    note: str | None
    affected_plans: int = 0


class MaintenanceDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    kind: DecisionKind
    reason_code: str | None
    note: str | None
    from_date: date | None
    to_date: date | None
    created_at: datetime


class MaintenanceKpiRead(BaseModel):
    as_of: date
    obligations: int
    over_limit: int
    over_tolerance: int
    due_soon: int
    blocked: int
    low_confidence: int
    provisional_baseline: int
    open_plans: int
    manual_dates: int
    avg_deferrals: float
    completed_last_90d: int
    on_time_last_90d: int
    on_time_pct: float | None


class MaintenanceHealthIssue(BaseModel):
    code: str
    count: int
    detail: str
    fixed: int = 0


class MaintenanceHealthRead(BaseModel):
    as_of: date
    ok: bool
    issues: list[MaintenanceHealthIssue]
