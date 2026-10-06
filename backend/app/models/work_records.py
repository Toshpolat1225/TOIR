import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MaintenanceLog(Base):
    __tablename__ = "maintenance_log"
    __table_args__ = (Index("ix_mlog_section_item", "section_id", "item_name"),)

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="SET NULL")
    )
    item_name: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    equipment: Mapped[str | None] = mapped_column(Text)
    work_type: Mapped[str | None] = mapped_column(Text)
    maintenance_date: Mapped[date | None] = mapped_column(Date)


class AiInsight(Base):
    __tablename__ = "ai_insights"
    __table_args__ = (
        CheckConstraint(
            "insight_type IN ('anomaly','prediction','efficiency')",
            name="ai_insights_insight_type_check",
        ),
        CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name="ai_insights_severity_check",
        ),
        Index("ix_insights_created", text("created_at DESC")),
        Index("ix_insights_asset", "asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE")
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE")
    )
    insight_type: Mapped[str] = mapped_column(Text, nullable=False)
    probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    severity: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'low'")
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
