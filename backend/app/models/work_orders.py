import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint(
            "order_kind IN ('planned','unplanned','repair','emergency')",
            name="work_orders_order_kind_check",
        ),
        CheckConstraint(
            "status IN ('pending','in_progress','completed','cancelled')",
            name="work_orders_status_check",
        ),
        CheckConstraint(
            "priority IN ('critical','high','normal','low')",
            name="work_orders_priority_check",
        ),
        CheckConstraint(
            "status <> 'completed' OR closed_at IS NOT NULL",
            name="ck_closed_when_completed",
        ),
        Index("ix_wo_created", text("created_at DESC")),
        Index("ix_wo_asset", "fixed_asset_id"),
        Index(
            "ix_wo_section_status",
            "section_id",
            "status",
            text("created_at DESC"),
        ),
        Index(
            "ix_wo_open",
            "status",
            postgresql_where=text("status IN ('pending','in_progress')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    fixed_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fixed_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    order_kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    priority: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'normal'")
    )
    executor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    chief_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    date_start: Mapped[datetime | None]
    date_end: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    mileage_at_creation: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    mileage_threshold: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class WorkOrderRepair(Base):
    __tablename__ = "work_order_repairs"
    __table_args__ = (
        UniqueConstraint(
            "work_order_id",
            "work_type_id",
            name="work_order_repairs_work_order_id_work_type_id_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class WorkOrderItem(Base):
    __tablename__ = "work_order_items"
    __table_args__ = (
        CheckConstraint("qty >= 0", name="work_order_items_qty_check"),
        Index("ix_wo_items_repair", "repair_id"),
        Index("ix_wo_items_nom", "nomenclature_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    repair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_order_repairs.id", ondelete="CASCADE"),
        nullable=False,
    )
    nomenclature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nomenclature.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    inv_no: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
