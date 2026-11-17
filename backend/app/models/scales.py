import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScalePost(Base):
    """One weighing post = one scale PC on its own rail track (code is the last octet of its address: 93, 97)."""

    __tablename__ = "scale_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    tare_default_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    capacity_norm_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_weighing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_src_train_id: Mapped[int | None] = mapped_column(Integer)
    last_src_weighing_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ScaleCargo(Base):
    __tablename__ = "scale_cargo"

    code: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class ScaleTrain(Base):
    """A weighed train (`Составы`). Raw columns come from the scale; derived columns are recomputed by the matching job."""

    __tablename__ = "scale_trains"
    __table_args__ = (
        UniqueConstraint("post_id", "src_id", name="uq_scale_trains_post_src"),
        CheckConstraint(
            "match_status IN ('pending','ok','no_loco','no_gtk_train','excluded')",
            name="ck_scale_trains_match_status",
        ),
        Index("ix_scale_trains_started", "started_at"),
        Index("ix_scale_trains_loco_asset_started", "loco_asset_id", "started_at"),
        Index("ix_scale_trains_open", "match_status", postgresql_where=text("match_status <> 'ok' AND match_status <> 'excluded'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scale_posts.id", ondelete="CASCADE"), nullable=False)
    src_id: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_on: Mapped[date | None] = mapped_column(Date)
    loco_number: Mapped[str | None] = mapped_column(Text)
    declared_wagons: Mapped[int | None] = mapped_column(Integer)
    reported_weight_t: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    doc_weight_t: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cargo_code: Mapped[int | None] = mapped_column(Integer)
    excavator: Mapped[int | None] = mapped_column(Integer)
    operator_code: Mapped[int | None] = mapped_column(Integer)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # derived (recomputed from the raw rows + corrections; never edited by hand)
    wagon_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    dump_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    traction_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    net_total_t: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    net_source: Mapped[str | None] = mapped_column(Text)  # 'weighings' | 'estimated'
    loco_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="SET NULL"))
    loco_gtk_id: Mapped[int | None] = mapped_column(Integer)
    gtk_train_id: Mapped[int | None] = mapped_column(Integer)
    carriages_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    carriages_linked: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    match_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    match_method: Mapped[str | None] = mapped_column(Text)  # 'alias' | 'gtk_garage' | 'forced'
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScaleWeighing(Base):
    """One weighed unit of a train (`Вагоны`): a dump car or a traction-aggregate unit."""

    __tablename__ = "scale_weighings"
    __table_args__ = (
        UniqueConstraint("train_id", "src_id", name="uq_scale_weighings_train_src"),
        CheckConstraint("unit_kind IN ('traction','dump')", name="ck_scale_weighings_unit_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    train_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scale_trains.id", ondelete="CASCADE"), nullable=False)
    src_id: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int | None] = mapped_column(Integer)
    unit_label: Mapped[str | None] = mapped_column(Text)
    gross_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    tare_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    net_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    capacity_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    overload_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    speed_kmh: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    axles: Mapped[int | None] = mapped_column(SmallInteger)
    weighed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unit_kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'dump'"))


class ScaleTrainCarriage(Base):
    """GTK carriages that stood in the train while it was weighed (history-aware), with the TOIR asset when it is linked."""

    __tablename__ = "scale_train_carriages"
    __table_args__ = (Index("ix_scale_train_carriages_asset", "asset_id"),)

    train_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scale_trains.id", ondelete="CASCADE"), primary_key=True)
    carriage_gtk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="SET NULL"))
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_position: Mapped[int | None] = mapped_column(Integer)  # the scale position paired with this car (exact attribution)
    net_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # this car's own cargo; NULL = only the train total is known


class ScaleCorrection(Base):
    """Operator corrections that survive every re-import and re-match (the system re-applies them dynamically)."""

    __tablename__ = "scale_corrections"
    __table_args__ = (
        CheckConstraint("kind IN ('loco_alias','train_exclude','train_gtk')", name="ck_scale_corrections_kind"),
        CheckConstraint(
            "(kind = 'loco_alias' AND loco_number IS NOT NULL AND asset_id IS NOT NULL)"
            " OR (kind = 'train_exclude' AND train_id IS NOT NULL)"
            " OR (kind = 'train_gtk' AND train_id IS NOT NULL AND gtk_train_id IS NOT NULL)",
            name="ck_scale_corrections_shape",
        ),
        Index("uq_scale_corrections_alias", "loco_number", unique=True, postgresql_where=text("kind = 'loco_alias' AND is_active")),
        Index("uq_scale_corrections_train", "train_id", "kind", unique=True, postgresql_where=text("kind <> 'loco_alias' AND is_active")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    loco_number: Mapped[str | None] = mapped_column(Text)
    train_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scale_trains.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"))
    gtk_train_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
