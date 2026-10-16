from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyReadinessSnapshot(Base):
    __tablename__ = "daily_readiness_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    section_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    asset_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False)
    availability_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
