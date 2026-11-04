from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssetFieldChange(Base):
    __tablename__ = "asset_field_changes"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('auto_fill','conflict','manual')",
            name="ck_asset_field_changes_kind",
        ),
        CheckConstraint(
            "status IN ('applied','pending','accepted','rejected')",
            name="ck_asset_field_changes_status",
        ),
        Index(
            "ix_asset_field_changes_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_asset_field_changes_asset_field_status",
            "asset_id",
            "field",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fixed_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    resolved_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None]
