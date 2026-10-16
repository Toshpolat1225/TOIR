import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FixedAsset(Base):
    __tablename__ = "fixed_assets"
    __table_args__ = (
        Index("ix_assets_type_status", "asset_type", "status"),
        Index("ix_assets_section", "section_id"),
        Index("ix_assets_series", "series"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    inv_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(
        Text, ForeignKey("fixed_asset_types.code", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False
    )
    series: Mapped[str | None] = mapped_column(Text)
    depot: Mapped[str | None] = mapped_column(Text)
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        Text,
        ForeignKey("fixed_asset_statuses.code", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        server_default=text("'operational'"),
    )
    comm_date: Mapped[date | None] = mapped_column(Date)
    year_built: Mapped[int | None] = mapped_column(Integer)
    mileage: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    last_maint_date: Mapped[date | None] = mapped_column(Date)
    next_maint_date: Mapped[date | None] = mapped_column(Date)
    initial_cost: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    owner: Mapped[str | None] = mapped_column(Text)
    wialon_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    wialon_last_sync: Mapped[datetime | None]
    wialon_speed: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    wialon_online: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    failure_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    health_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    predicted_failure_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    last_ml_update: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class MileageHistory(Base):
    __tablename__ = "mileage_history"
    __table_args__ = (
        CheckConstraint(
            "source IN ('wialon','manual')", name="mileage_history_source_check"
        ),
        Index(
            "ix_mileage_asset_time",
            "asset_id",
            text("recorded_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False
    )
    mileage: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'wialon'")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class WialonSettings(Base):
    __tablename__ = "wialon_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="wialon_settings_id_check"),
    )

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, server_default=text("1")
    )
    host: Mapped[str | None] = mapped_column(Text)
    token: Mapped[str | None] = mapped_column(Text)
    sync_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5")
    )
    auto_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    last_sync_at: Mapped[datetime | None]
    last_sync_status: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
