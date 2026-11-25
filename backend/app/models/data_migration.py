"""Migration journal: which values came from which imported file, and what was there before.

One batch = one imported file. One item = one value written into one asset. The asset column itself stays the source
of truth; the item remembers the old value so a migrated value can be viewed, corrected or rolled back.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DataMigrationBatch(Base):
    __tablename__ = "data_migration_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)  # the fixed_assets column that was filled, e.g. last_maint_date
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class DataMigrationItem(Base):
    __tablename__ = "data_migration_items"
    __table_args__ = (
        CheckConstraint("status IN ('applied','reverted')", name="ck_data_migration_items_status"),
        UniqueConstraint("batch_id", "asset_id", name="uq_data_migration_items_batch_asset"),
        Index("ix_data_migration_items_batch_status", "batch_id", "status"),
        Index("ix_data_migration_items_asset", "asset_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_migration_batches.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False
    )
    old_value: Mapped[str | None] = mapped_column(Text)  # what the column held before (NULL = it was empty)
    new_value: Mapped[str | None] = mapped_column(Text)  # what the migration wrote (ISO date for last_maint_date)
    raw_value: Mapped[str | None] = mapped_column(Text)  # the original text in the file, e.g. «12.11.26»
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'applied'"))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
