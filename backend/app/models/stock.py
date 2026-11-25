"""Spare-part stock (from 1C), supplier lead times and purchase orders: the input of the stock-risk analytics."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StockBalance(Base):
    __tablename__ = "stock_balances"
    __table_args__ = (
        CheckConstraint("qty >= 0", name="ck_stock_balances_qty"),
        CheckConstraint("source IN ('1c_import','manual','demo')", name="ck_stock_balances_source"),
        UniqueConstraint("nomenclature_id", "warehouse", "as_of", name="uq_stock_balances_key"),
        Index("ix_stock_balances_nomenclature", "nomenclature_id", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    nomenclature_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nomenclature.id", ondelete="CASCADE"), nullable=False)
    warehouse: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'1c_import'"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class SupplierTerm(Base):
    __tablename__ = "supplier_terms"
    __table_args__ = (
        CheckConstraint("lead_time_days > 0", name="ck_supplier_terms_lead"),
        CheckConstraint("safety_days >= 0", name="ck_supplier_terms_safety"),
        CheckConstraint("min_order_qty IS NULL OR min_order_qty > 0", name="ck_supplier_terms_moq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    nomenclature_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nomenclature.id", ondelete="CASCADE"), nullable=False, unique=True)
    supplier: Mapped[str | None] = mapped_column(Text)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    min_order_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    safety_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("14"))
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_purchase_orders_qty"),
        CheckConstraint("qty_received >= 0", name="ck_purchase_orders_received"),
        CheckConstraint("status IN ('ordered','in_transit','partial','received','cancelled')", name="ck_purchase_orders_status"),
        Index("ix_purchase_orders_nomenclature", "nomenclature_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    nomenclature_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nomenclature.id", ondelete="CASCADE"), nullable=False)
    doc_no: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    qty_received: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, server_default=text("0"))
    ordered_on: Mapped[date | None] = mapped_column(Date)
    expected_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ordered'"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
