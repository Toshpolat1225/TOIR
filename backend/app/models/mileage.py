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
        UniqueConstraint("payload_hash", name="uq_gtk_raw_snapshots_payload_hash"),
        Index("ix_gtk_raw_snapshots_effective_received", "effective_at", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sync_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("gtk_sync_runs.id", ondelete="SET NULL")
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
        CheckConstraint("odometer_km >= 0", name="ck_wialon_odometer_readings_nonnegative"),
        Index("ix_wialon_odometer_asset_time", "asset_id", "reading_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="RESTRICT"), nullable=False
    )
    source_unit_id: Mapped[str] = mapped_column(Text, nullable=False)
    odometer_km: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    reading_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class WagonMileageOpeningBalance(Base):
    __tablename__ = "wagon_mileage_opening_balances"
    __table_args__ = (
        CheckConstraint("mileage_km >= 0", name="ck_wagon_mileage_opening_nonnegative"),
        Index("ix_wagon_mileage_opening_asset_effective", "asset_id", "effective_at"),
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
    note: Mapped[str | None] = mapped_column(Text)
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
        CheckConstraint("km >= 0", name="ck_wagon_mileage_ledger_nonnegative"),
        CheckConstraint("period_to >= period_from", name="ck_wagon_mileage_ledger_period"),
        CheckConstraint(
            "status IN ('active','superseded','rejected')",
            name="ck_wagon_mileage_ledger_status",
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
    train_gtk_id: Mapped[int | None] = mapped_column(Integer)
    period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    km: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    calculation_details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WagonIdlePeriod(Base):
    __tablename__ = "wagon_idle_periods"
    __table_args__ = (
        CheckConstraint("period_to >= period_from", name="ck_wagon_idle_period"),
        CheckConstraint(
            "status IN ('confirmed','unknown_activity','estimated')",
            name="ck_wagon_idle_status",
        ),
        Index("ix_wagon_idle_asset_period", "wagon_asset_id", "period_from"),
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
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
