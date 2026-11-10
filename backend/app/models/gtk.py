from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GtkLocomotive(Base):
    __tablename__ = "gtk_locomotives"
    __table_args__ = (Index("ix_gtk_locomotives_name", "name"),)

    gtk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    garage_number: Mapped[str | None] = mapped_column(Text)
    inventory_number: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(Text)
    vehicle_type_name: Mapped[str | None] = mapped_column(Text)
    division_name: Mapped[str | None] = mapped_column(Text)
    start_expl_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_expl_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class GtkCarriage(Base):
    __tablename__ = "gtk_carriages"
    __table_args__ = (
        Index("ix_gtk_carriages_name", "name"),
        Index("ix_gtk_carriages_reg_number", "reg_number"),
    )

    gtk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    reg_number: Mapped[str | None] = mapped_column(Text)
    inventory_number: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(Text)
    start_expl_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_expl_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_loaded: Mapped[bool | None] = mapped_column(Boolean)
    is_not_serviceable: Mapped[bool | None] = mapped_column(Boolean)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    state_duration_s: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class GtkTrain(Base):
    __tablename__ = "gtk_trains"
    __table_args__ = (Index("ix_gtk_trains_number", "number"),)

    gtk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    begin_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class GtkTrainMember(Base):
    __tablename__ = "gtk_train_members"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('locomotive','carriage')", name="ck_gtk_train_members_kind"
        ),
        Index(
            "uq_gtk_train_members_open",
            "train_gtk_id",
            "kind",
            "object_gtk_id",
            unique=True,
            postgresql_where=text("observed_to IS NULL"),
        ),
        Index("ix_gtk_train_members_object", "kind", "object_gtk_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    train_gtk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[Literal["locomotive", "carriage"]] = mapped_column(Text, nullable=False)
    object_gtk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    gtk_begin_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    observed_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GtkMembershipObservation(Base):
    __tablename__ = "gtk_membership_observations"
    __table_args__ = (
        CheckConstraint(
            "change_type IN ('opened','closed')",
            name="ck_gtk_membership_observations_change_type",
        ),
        UniqueConstraint(
            "membership_id",
            "snapshot_id",
            "change_type",
            name="uq_gtk_membership_observation",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("gtk_train_members.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gtk_raw_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_type: Mapped[Literal["opened", "closed"]] = mapped_column(Text, nullable=False)


class GtkSyncRun(Base):
    __tablename__ = "gtk_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok','error','parse_error','suspicious','login_failed')",
            name="ck_gtk_sync_runs_status",
        ),
        Index("ix_gtk_sync_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    counts: Mapped[dict | None] = mapped_column(JSONB)
    quality: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)


class GtkWagonMileageLog(Base):
    __tablename__ = "gtk_wagon_mileage_log"
    __table_args__ = (
        Index(
            "ix_gtk_wagon_mileage_log_wagon_period",
            "wagon_asset_id",
            "period_to",
        ),
        Index("ix_gtk_wagon_mileage_log_train", "train_gtk_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wagon_asset_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fixed_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    loco_asset_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    train_gtk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    km: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class GtkLocomotiveMileageCheckpoint(Base):
    __tablename__ = "gtk_locomotive_mileage_checkpoints"

    locomotive_gtk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    locomotive_asset_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fixed_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    mileage: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    checkpoint_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
