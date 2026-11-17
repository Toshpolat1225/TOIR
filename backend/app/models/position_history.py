import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssetPositionHistory(Base):
    """Where an asset was and when: stored only when it moved (>= ~100 m) or as a slow heartbeat, so a parked unit costs a row per 20 min."""

    __tablename__ = "asset_position_history"
    __table_args__ = (
        UniqueConstraint("asset_id", "at", "source", name="uq_asset_position_history_point"),
        CheckConstraint("source IN ('wialon','gtk')", name="ck_asset_position_history_source"),
        CheckConstraint("lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180", name="ck_asset_position_history_range"),
        Index("ix_asset_position_history_asset_at", "asset_id", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    lon: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    speed: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'wialon'"))
