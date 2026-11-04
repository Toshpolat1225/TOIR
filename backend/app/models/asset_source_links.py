import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssetSourceLink(Base):
    __tablename__ = "asset_source_links"
    __table_args__ = (
        CheckConstraint(
            "source IN ('wialon','gtk','vesavoy','onec')",
            name="ck_asset_source_links_source",
        ),
        CheckConstraint(
            "status IN ('active','ended')",
            name="ck_asset_source_links_status",
        ),
        CheckConstraint(
            "link_method IN ('manual','migrated','import')",
            name="ck_asset_source_links_method",
        ),
        Index(
            "uq_asset_source_links_source_external_active",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_asset_source_links_asset_source_active",
            "asset_id",
            "source",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_asset_source_links_asset_time", "asset_id", "linked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fixed_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    link_method: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'manual'")
    )
    linked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    linked_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    unlinked_at: Mapped[datetime | None]
    note: Mapped[str | None] = mapped_column(Text)
