from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WialonUnitRecord(Base):
    __tablename__ = "wialon_units"
    __table_args__ = (
        Index("ix_wialon_units_name", "name"),
        Index("ix_wialon_units_last_message_at", "last_message_at"),
        CheckConstraint(
            "(lat IS NULL OR lat BETWEEN -90 AND 90) AND (lon IS NULL OR lon BETWEEN -180 AND 180)",
            name="ck_wialon_units_position_range",
        ),
    )

    unit_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    cnm: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    cneh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_flags: Mapped[int | None] = mapped_column(Integer)
    speed: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # last known GPS position (kept when a later pull has none) and when that fix was made
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    position_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspect_absolute: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
