import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Nomenclature(Base):
    __tablename__ = "nomenclature"
    __table_args__ = (
        UniqueConstraint(
            "department_id", "name", name="nomenclature_department_id_name_key"
        ),
        Index("ix_nomenclature_code", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'шт.'")
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class NomenclatureNorm(Base):
    __tablename__ = "nomenclature_norms"
    __table_args__ = (
        UniqueConstraint(
            "nomenclature_id",
            "department_id",
            "work_type_id",
            name="nomenclature_norms_nomenclature_id_department_id_work_type_id_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    nomenclature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nomenclature.id", ondelete="CASCADE"),
        nullable=False,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    standard_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    min_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    max_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class WorkTypeTemplate(Base):
    __tablename__ = "work_type_templates"
    __table_args__ = (
        CheckConstraint(
            "nomenclature_id IS NOT NULL OR name IS NOT NULL",
            name="ck_template_target",
        ),
        Index("ix_templates_work_type", "work_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    work_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE")
    )
    nomenclature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nomenclature.id", ondelete="CASCADE")
    )
    name: Mapped[str | None] = mapped_column(Text)
    inv_no: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    default_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("1")
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    note: Mapped[str | None] = mapped_column(Text)
