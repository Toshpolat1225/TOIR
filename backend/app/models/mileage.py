from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GtkRawSnapshot(Base):
    __tablename__ = "gtk_raw_snapshots"
    __table_args__ = (
        Index("ix_gtk_raw_snapshots_effective_received", "effective_at", "received_at"),
        Index("ix_gtk_raw_snapshots_payload_hash", "payload_hash"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sync_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("gtk_sync_runs.id", ondelete="SET NULL")
    )
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class WialonOdometerReading(Base):
    __tablename__ = "wialon_odometer_readings"
    __table_args__ = (
        UniqueConstraint("payload_hash", name="uq_wialon_odometer_readings_payload_hash"),
        UniqueConstraint("measurement_key", name="uq_wialon_odometer_measurement_key"),
        CheckConstraint("odometer_km >= 0", name="ck_wialon_odometer_readings_nonnegative"),
        CheckConstraint(
            "classification IN ('CONFIRMED','ESTIMATED','HELD')",
            name="ck_wialon_odometer_classification",
        ),
        CheckConstraint(
            "source IN ('push','pull')",
            name="ck_wialon_odometer_source",
        ),
        Index("ix_wialon_odometer_asset_time", "asset_id", "reading_at"),
        Index("ix_wialon_odometer_observed_at", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="RESTRICT")
    )
    source_unit_id: Mapped[str] = mapped_column(Text, nullable=False)
    odometer_km: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    reading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_km: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, server_default=text("1")
    )
    source: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'pull'")
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    calculation_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    classification: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'HELD'")
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_key: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class WialonRawReceipt(Base):
    __tablename__ = "wialon_raw_receipts"
    __table_args__ = (
        CheckConstraint(
            "transport IN ('push','pull')",
            name="ck_wialon_raw_receipts_transport",
        ),
        Index("ix_wialon_raw_receipts_received", "received_at"),
        Index("ix_wialon_raw_receipts_unit_received", "source_unit_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_unit_id: Mapped[str | None] = mapped_column(Text)
    asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="SET NULL")
    )
    reading_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("wialon_odometer_readings.id", ondelete="SET NULL")
    )
    transport: Mapped[str] = mapped_column(String(8), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class WagonMileageOpeningBalance(Base):
    __tablename__ = "wagon_mileage_opening_balances"
    __table_args__ = (
        CheckConstraint("mileage_km >= 0", name="ck_wagon_mileage_opening_nonnegative"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','superseded')",
            name="ck_wagon_mileage_opening_status",
        ),
        CheckConstraint(
            "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_wagon_mileage_opening_approval_audit",
        ),
        Index("ix_wagon_mileage_opening_asset_effective", "asset_id", "effective_at"),
        Index(
            "uq_wagon_mileage_opening_active_approved",
            "asset_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="RESTRICT"), nullable=False
    )
    mileage_km: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("wagon_mileage_opening_balances.id", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class MileageCalculationRun(Base):
    __tablename__ = "mileage_calculation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','partial','failed')",
            name="ck_mileage_calculation_runs_status",
        ),
        Index("ix_mileage_calculation_runs_started", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("gtk_raw_snapshots.id", ondelete="SET NULL")
    )
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))
    input_watermark: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)


class WagonMileageLedger(Base):
    __tablename__ = "wagon_mileage_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_wagon_mileage_ledger_idempotency"),
        CheckConstraint(
            "distance_km >= 0",
            name="ck_wagon_mileage_ledger_distance_nonnegative",
        ),
        CheckConstraint("period_to > period_from", name="ck_wagon_mileage_ledger_period"),
        CheckConstraint(
            "status IN ('active','superseded','rejected')",
            name="ck_wagon_mileage_ledger_status",
        ),
        CheckConstraint(
            "classification IN ('CONFIRMED','ESTIMATED','HELD')",
            name="ck_wagon_mileage_ledger_classification",
        ),
        Index("ix_wagon_mileage_ledger_asset_period", "wagon_asset_id", "period_from", "period_to"),
        Index("ix_wagon_mileage_ledger_run", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mileage_calculation_runs.id", ondelete="RESTRICT"), nullable=False
    )
    wagon_asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="RESTRICT"), nullable=False
    )
    locomotive_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="RESTRICT")
    )
    train_gtk_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("gtk_trains.gtk_id", ondelete="RESTRICT")
    )
    period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    classification: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'HELD'")
    )
    calculation_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'wagon-mileage-v1'")
    )
    input_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'legacy'")
    )
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wagon_mileage_ledger.id", ondelete="RESTRICT"),
    )
    calculation_details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class MileageCalculationInput(Base):
    __tablename__ = "mileage_calculation_inputs"
    __table_args__ = (
        CheckConstraint(
            "(gtk_snapshot_id IS NOT NULL)::int + "
            "(wialon_reading_id IS NOT NULL)::int + "
            "(opening_balance_id IS NOT NULL)::int + "
            "(gtk_membership_id IS NOT NULL)::int = 1",
            name="ck_mileage_calculation_inputs_one_source",
        ),
        Index(
            "uq_mileage_run_input_gtk_snapshot",
            "run_id",
            "gtk_snapshot_id",
            unique=True,
            postgresql_where=text("gtk_snapshot_id IS NOT NULL"),
        ),
        Index(
            "uq_mileage_run_input_wialon_reading",
            "run_id",
            "wialon_reading_id",
            unique=True,
            postgresql_where=text("wialon_reading_id IS NOT NULL"),
        ),
        Index(
            "uq_mileage_run_input_opening_balance",
            "run_id",
            "opening_balance_id",
            unique=True,
            postgresql_where=text("opening_balance_id IS NOT NULL"),
        ),
        Index(
            "uq_mileage_run_input_gtk_membership",
            "run_id",
            "gtk_membership_id",
            unique=True,
            postgresql_where=text("gtk_membership_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("mileage_calculation_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gtk_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("gtk_raw_snapshots.id", ondelete="RESTRICT")
    )
    wialon_reading_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("wialon_odometer_readings.id", ondelete="RESTRICT")
    )
    opening_balance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wagon_mileage_opening_balances.id", ondelete="RESTRICT"),
    )
    gtk_membership_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("gtk_train_members.id", ondelete="RESTRICT")
    )


class WagonIdlePeriod(Base):
    __tablename__ = "wagon_idle_periods"
    __table_args__ = (
        CheckConstraint("period_to > period_from", name="ck_wagon_idle_period"),
        CheckConstraint(
            "distance_km = 0",
            name="ck_wagon_idle_distance_zero",
        ),
        CheckConstraint(
            "status IN ('confirmed','unknown_activity','estimated')",
            name="ck_wagon_idle_status",
        ),
        Index("ix_wagon_idle_asset_period", "wagon_asset_id", "period_from"),
        UniqueConstraint("idempotency_key", name="uq_wagon_idle_period_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    wagon_asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="RESTRICT"), nullable=False
    )
    aggregate_gtk_id: Mapped[int | None] = mapped_column(BigInteger)
    period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
