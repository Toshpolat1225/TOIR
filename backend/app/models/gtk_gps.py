"""GTK's OWN GPS (separate from Wialon): the live state of every GTK unit, one row per unit-day with GTK's distance, and the sync log.

The track points themselves live in `asset_position_history` with source = 'gtk_gps' (movement-thinned, like Wialon's).
"""
from datetime import date, datetime
from decimal import Decimal

import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GtkGpsUnit(Base):
    """Last GPS state of a GTK unit (get_vehicles). `gtk_id` is the same id as `asset_source_links.external_id` of a locomotive."""

    __tablename__ = "gtk_gps_units"
    __table_args__ = (
        CheckConstraint("(lat IS NULL OR lat BETWEEN -90 AND 90) AND (lon IS NULL OR lon BETWEEN -180 AND 180)", name="ck_gtk_gps_units_range"),
    )

    gtk_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(Text)
    garage_number: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(Text)
    vehicle_type_id: Mapped[int | None] = mapped_column(Integer)
    enterprise_id: Mapped[int | None] = mapped_column(Integer)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    speed: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    course: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    height: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    position_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # GTK's fix time, UTC
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GtkGpsDay(Base):
    """GTK's distance for one unit and one local day (UTC+5) and how many raw points it came from."""

    __tablename__ = "gtk_gps_days"
    __table_args__ = (Index("ix_gtk_gps_days_day", "day"),)

    gtk_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    first_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    events: Mapped[dict | None] = mapped_column(JSONB)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GtkGpsRun(Base):
    """One GTK GPS synchronisation (health of the feed shown on the GPS page)."""

    __tablename__ = "gtk_gps_runs"
    __table_args__ = (
        CheckConstraint("status IN ('success','partial','failed')", name="ck_gtk_gps_runs_status"),
        Index("ix_gtk_gps_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tracks_ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tracks_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    points_stored: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # bumped by every committed batch: a run without one for a while is dead


class GpsDayAssessment(Base):
    """Per locomotive and local day: both trackers' distances side by side, the cause of a difference, the fused distance and the confidence."""

    __tablename__ = "gps_day_assessment"
    __table_args__ = (Index("ix_gps_day_assessment_day", "day"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    wialon_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    wialon_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    gtk_m: Mapped[int | None] = mapped_column(Integer)
    gtk_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    gtk_raw_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    gtk_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    gtk_collected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    diff_m: Mapped[int | None] = mapped_column(Integer)
    fused_m: Mapped[int | None] = mapped_column(Integer)
    unknown_gap_m: Mapped[int | None] = mapped_column(Integer)
    wialon_cov_h: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    gtk_cov_h: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    wialon_gap_h: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    gtk_gap_h: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cause: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    idle_events: Mapped[int | None] = mapped_column(Integer)
    odo_m: Mapped[int | None] = mapped_column(Integer)  # Wialon odometer delta over the day (interpolated at the day edges)
    odo_agrees: Mapped[bool | None] = mapped_column(Boolean)  # the odometer corroborates the Wialon track (within 15%)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GpsWagonSegment(Base):
    """A wagon's stay behind one locomotive (GTK membership) with the four distance candidates and the selected one (never summed or averaged)."""

    __tablename__ = "gps_wagon_segments"
    __table_args__ = (
        UniqueConstraint("carriage_gtk_id", "train_gtk_id", "period_from", name="uq_gps_wagon_segments_key"),
        Index("ix_gps_wagon_segments_wagon", "wagon_asset_id", "period_from"),
        Index("ix_gps_wagon_segments_loco", "loco_asset_id", "period_from"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wagon_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="SET NULL"))
    carriage_gtk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    train_gtk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    loco_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="SET NULL"))
    loco_gtk_id: Mapped[int | None] = mapped_column(Integer)
    period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    km_odometer: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    km_wialon: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    km_gtk: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    km_fused: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    selected_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    coverage: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    flags: Mapped[list | None] = mapped_column(JSONB)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
