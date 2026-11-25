"""Repair consumption norms: materials and spare parts per ONE unit of equipment for one repair kind.

A norm set is (repair kind = work type, equipment type, optional model). Unlike `nomenclature_norms` it is not tied to
a department (section): the same norm applies wherever that repair is done.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RepairNormItem(Base):
    __tablename__ = "repair_norm_items"
    __table_args__ = (
        CheckConstraint("section IN ('materials','spare_parts','lubricants')", name="ck_repair_norm_items_section"),
        CheckConstraint("basis IN ('per_repair','per_month_per_unit')", name="ck_repair_norm_items_basis"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_repair_norm_items_quantity"),
        Index("ix_repair_norm_items_set", "work_type_id", "asset_type", "asset_model_id", "norm_group", "seq"),
        Index("ix_repair_norm_items_parent", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    work_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, ForeignKey("fixed_asset_types.code", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    asset_model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id", ondelete="SET NULL"))
    norm_group: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))  # series the norm applies to, e.g. «ТЭМ2, ТЭМ18, ТЭМ18ДМ»
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # order inside the source sheet
    section: Mapped[str] = mapped_column(Text, nullable=False)  # materials | spare_parts | lubricants
    group_name: Mapped[str | None] = mapped_column(Text)  # assembly / sub-group title inside the sheet
    basis: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'per_repair'"))  # per_repair | per_month_per_unit
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))  # the FIRST number of quantity_text (pieces for «12/1,44-2,4»)
    quantity_text: Mapped[str] = mapped_column(Text, nullable=False)  # exactly as in the source file
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("repair_norm_items.id", ondelete="CASCADE"))
    note: Mapped[str | None] = mapped_column(Text)  # e.g. «При замене на швеллер №18»
    source_file: Mapped[str | None] = mapped_column(Text)
    source_sheet: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
