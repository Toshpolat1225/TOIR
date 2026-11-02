import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WialonCounterState(Base):
    """Har bir texnika uchun oxirgi QABUL QILINGAN Wialon hisoblagichlari (baseline + delta uchun)."""

    __tablename__ = "wialon_counter_state"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), primary_key=True
    )
    baseline_cnm: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    last_cnm: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    last_cnm_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    baseline_cneh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    last_cneh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    last_cneh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # TOIR yig'gan moto-soat (faqat qabul qilingan deltalar). NULL = ma'lumot yo'q (0 emas!).
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    suspect_absolute: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_status: Mapped[str | None] = mapped_column(Text)
    last_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WialonRejectedReading(Base):
    """Rad etilgan o'qishlar auditi: nima, qachon, nega."""

    __tablename__ = "wialon_rejected_readings"
    __table_args__ = (
        CheckConstraint("counter IN ('mileage','engine_hours')", name="wialon_rejected_counter_check"),
        Index("ix_wialon_rejected_asset_time", "asset_id", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False
    )
    counter: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    reading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
