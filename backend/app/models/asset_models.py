import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssetModel(Base):
    __tablename__ = "asset_models"
    __table_args__ = (
        UniqueConstraint("name_normalized", name="uq_asset_models_name_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "fixed_asset_types.code", onupdate="CASCADE", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    series: Mapped[str | None] = mapped_column(Text)
