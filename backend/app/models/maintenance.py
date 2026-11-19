import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkType(Base):
    __tablename__ = "work_types"
    __table_args__ = (
        CheckConstraint(
            "unit_type IN ('locomotive','wagon')", name="work_types_unit_type_check"
        ),
        CheckConstraint(
            "duration_hours IS NULL OR duration_hours > 0",
            name="work_types_duration_hours_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit_type: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class WorkSubtask(Base):
    __tablename__ = "work_subtasks"
    __table_args__ = (Index("ix_subtasks_work_type", "work_type_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    work_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class MaintenanceInterval(Base):
    __tablename__ = "maintenance_intervals"
    __table_args__ = (
        CheckConstraint(
            "interval_km IS NOT NULL OR interval_days IS NOT NULL OR interval_hours IS NOT NULL",
            name="ck_interval_defined",
        ),
        CheckConstraint(
            "tolerance_pct >= 0 AND tolerance_pct <= 100", name="ck_interval_tolerance_range"
        ),
        CheckConstraint("lead_days >= 0 AND lead_days <= 1000", name="ck_interval_lead_days_range"),
        UniqueConstraint("code", name="maintenance_intervals_code_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    work_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_types.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    interval_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    interval_days: Mapped[int | None] = mapped_column(Integer)
    # Engine hours (моточасы), the usual meter of diesel locomotives; a limit is optional per interval.
    interval_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Position in the cycle: completing a higher rank resets every lower rank. NULL = independent.
    rank: Mapped[int | None] = mapped_column(Integer)
    # Permitted overrun past the limit (percent of the interval) before approval is required.
    tolerance_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("10")
    )
    # How many days before the cautious due date planning (parts, slot) starts.
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("7"))
    asset_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{locomotive,diesel}'"),
    )
    warn_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("10")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class MaintenancePlan(Base):
    __tablename__ = "maintenance_plan"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled','in_progress','completed','cancelled','blocked','covered','waived')",
            name="maintenance_plan_status_check",
        ),
        CheckConstraint(
            "(status = 'blocked') = (blocked_reason IS NOT NULL)",
            name="ck_maintenance_plan_blocked_consistency",
        ),
        CheckConstraint("deferral_count >= 0", name="ck_maintenance_plan_deferral_count"),
        UniqueConstraint(
            "asset_id",
            "interval_id",
            "trigger_mileage",
            name="maintenance_plan_asset_id_interval_id_trigger_mileage_key",
        ),
        Index("ix_plan_status_date", "status", "scheduled_date"),
        CheckConstraint(
            "reschedule_reason IS NULL OR char_length(reschedule_reason) <= 500",
            name="ck_maintenance_plan_reschedule_reason_len",
        ),
        CheckConstraint(
            "scheduled_date_manual OR (recommended_date IS NULL AND reschedule_reason IS NULL)",
            name="ck_maintenance_plan_manual_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False
    )
    interval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_intervals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'scheduled'")
    )
    trigger_mileage: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    completed_date: Mapped[date | None] = mapped_column(Date)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="SET NULL")
    )
    # True once a planner moved the date by hand; the automatic forecast then leaves it alone.
    scheduled_date_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # What the system recommended (kept fresh while the date is manual) and why it was moved.
    recommended_date: Mapped[date | None] = mapped_column(Date)
    reschedule_reason: Mapped[str | None] = mapped_column(Text)
    # Blocked: a named obstacle (parts, no bay, ...) with an optional expected end.
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    blocked_until: Mapped[date | None] = mapped_column(Date)
    blocked_note: Mapped[str | None] = mapped_column(Text)
    blocked_by_disruption_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_disruption.id", ondelete="SET NULL")
    )
    deferral_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Covered: a higher-rank plan was completed and reset this one.
    covered_by_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_plan.id", ondelete="SET NULL")
    )
    # Meter values at completion: the new baseline of the "since the last service" count.
    completed_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    completed_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class MaintenanceSettings(Base):
    __tablename__ = "maintenance_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="maintenance_settings_id_check"),
        CheckConstraint(
            "daily_average_km IS NULL OR daily_average_km > 0",
            name="maintenance_settings_daily_average_km_check",
        ),
    )

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, server_default=text("1")
    )
    daily_average_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class AssetMaintenanceBaseline(Base):
    """Where the "since the last service" count of one asset and interval starts."""

    __tablename__ = "asset_maintenance_baseline"
    __table_args__ = (
        CheckConstraint("hours IS NULL OR hours >= 0", name="ck_baseline_hours_nonnegative"),
        CheckConstraint(
            "source IN ('provisional','import','completed','manual','waived')",
            name="ck_baseline_source",
        ),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), primary_key=True
    )
    interval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_intervals.id", ondelete="CASCADE"), primary_key=True
    )
    done_at: Mapped[date | None] = mapped_column(Date)
    # In the SAME scale as fixed_assets.mileage (kilometres since tracking began). A service done before
    # tracking began therefore has a negative baseline.
    km: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="SET NULL")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class MaintenanceDecision(Base):
    """Every human decision on a plan (move, block, waive...) with its reason and who approved it."""

    __tablename__ = "maintenance_decision"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('reschedule','block','unblock','waive','cover','release')",
            name="ck_decision_kind",
        ),
        CheckConstraint("note IS NULL OR char_length(note) <= 500", name="ck_decision_note_len"),
        Index("ix_decision_plan_time", "plan_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_plan.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    from_date: Mapped[date | None] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class MaintenanceDisruption(Base):
    """An obstacle (no parts, no bay, accident...) that blocks planned work for a time."""

    __tablename__ = "maintenance_disruption"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('parts','no_bay','no_crew','unit_unavailable','accident','unplanned_repair','sensor_failure','weather','other')",
            name="ck_disruption_kind",
        ),
        CheckConstraint("scope IN ('asset','section','all')", name="ck_disruption_scope"),
        CheckConstraint("status IN ('open','closed')", name="ck_disruption_status"),
        CheckConstraint(
            "(scope <> 'asset' OR asset_id IS NOT NULL) AND (scope <> 'section' OR section_id IS NOT NULL)",
            name="ck_disruption_scope_target",
        ),
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="ck_disruption_dates"),
        CheckConstraint("note IS NULL OR char_length(note) <= 500", name="ck_disruption_note_len"),
        Index("ix_disruption_status_dates", "status", "starts_on", "ends_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE")
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="SET NULL")
    )
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    closed_at: Mapped[datetime | None] = mapped_column()


class AssetMeterDaily(Base):
    """End-of-day meter values: the history that pace estimation (and, for hours, only this) can use."""

    __tablename__ = "asset_meter_daily"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
