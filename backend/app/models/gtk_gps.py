"""GTK's OWN GPS (separate from Wialon): the live state of every GTK unit, one row per unit-day with GTK's distance, and the sync log.

The track points themselves live in `asset_position_history` with source = 'gtk_gps' (movement-thinned, like Wialon's).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Index, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
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
