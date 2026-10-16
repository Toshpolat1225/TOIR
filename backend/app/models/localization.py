import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FixedAssetType(Base):
    __tablename__ = "fixed_asset_types"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class FixedAssetStatus(Base):
    __tablename__ = "fixed_asset_statuses"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class DepartmentTranslation(Base):
    __tablename__ = "department_translations"
    __table_args__ = (
        UniqueConstraint("department_id", "locale", name="uq_department_translation_locale"),
        CheckConstraint("locale IN ('uz-Latn','uz-Cyrl','ru')", name="ck_department_translation_locale"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    department_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class SectionTranslation(Base):
    __tablename__ = "section_translations"
    __table_args__ = (
        UniqueConstraint("section_id", "locale", name="uq_section_translation_locale"),
        CheckConstraint("locale IN ('uz-Latn','uz-Cyrl','ru')", name="ck_section_translation_locale"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    section_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class WorkTypeTranslation(Base):
    __tablename__ = "work_type_translations"
    __table_args__ = (
        UniqueConstraint("work_type_id", "locale", name="uq_work_type_translation_locale"),
        CheckConstraint("locale IN ('uz-Latn','uz-Cyrl','ru')", name="ck_work_type_translation_locale"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    work_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class WorkSubtaskTranslation(Base):
    __tablename__ = "work_subtask_translations"
    __table_args__ = (
        UniqueConstraint("work_subtask_id", "locale", name="uq_work_subtask_translation_locale"),
        CheckConstraint("locale IN ('uz-Latn','uz-Cyrl','ru')", name="ck_work_subtask_translation_locale"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    work_subtask_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("work_subtasks.id", ondelete="CASCADE"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class NomenclatureTranslation(Base):
    __tablename__ = "nomenclature_translations"
    __table_args__ = (
        UniqueConstraint("nomenclature_id", "locale", name="uq_nomenclature_translation_locale"),
        CheckConstraint("locale IN ('uz-Latn','uz-Cyrl','ru')", name="ck_nomenclature_translation_locale"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    nomenclature_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nomenclature.id", ondelete="CASCADE"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class FixedAssetTypeTranslation(Base):
    __tablename__ = "fixed_asset_type_translations"
    __table_args__ = (
        UniqueConstraint("type_code", "locale", name="uq_fixed_asset_type_translation_locale"),
        CheckConstraint("locale IN ('uz-Latn','uz-Cyrl','ru')", name="ck_fixed_asset_type_translation_locale"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    type_code: Mapped[str] = mapped_column(Text, ForeignKey("fixed_asset_types.code", ondelete="CASCADE"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class FixedAssetStatusTranslation(Base):
    __tablename__ = "fixed_asset_status_translations"
    __table_args__ = (
        UniqueConstraint("status_code", "locale", name="uq_fixed_asset_status_translation_locale"),
        CheckConstraint("locale IN ('uz-Latn','uz-Cyrl','ru')", name="ck_fixed_asset_status_translation_locale"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    status_code: Mapped[str] = mapped_column(Text, ForeignKey("fixed_asset_statuses.code", ondelete="CASCADE"), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
