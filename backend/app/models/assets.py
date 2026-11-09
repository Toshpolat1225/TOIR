import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    func,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    select,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FixedAsset(Base):
    __tablename__ = "fixed_assets"
    __table_args__ = (
        Index("ix_assets_type_status", "asset_type", "status"),
        Index("ix_assets_section", "section_id"),
        Index(
            "ix_fixed_assets_inv_number",
            "inv_number",
        ),
        Index("ix_fixed_assets_model_id", "model_id"),
        Index(
            "uq_fixed_assets_accounting_inv_number",
            "accounting_inv_number",
            unique=True,
            postgresql_where=text("accounting_inv_number IS NOT NULL"),
        ),
        Index(
            "ix_fixed_assets_type_model_serial",
            "asset_type",
            "model_id",
            "serial_number",
            postgresql_where=text(
                "model_id IS NOT NULL AND serial_number IS NOT NULL"
            ),
        ),
        CheckConstraint(
            "year_built IS NULL OR year_built >= 1900",
            name="ck_fixed_assets_year_built_min",
        ),
        CheckConstraint(
            "CASE WHEN commissioned_at IS NULL OR year_built IS NULL "
            "OR year_built < 1 OR year_built > 9999 THEN true "
            "ELSE commissioned_at >= make_date(year_built, 1, 1) END",
            name="ck_fixed_assets_commissioned_at_year_built",
        ),
        CheckConstraint(
            "decommissioned_at IS NULL OR commissioned_at IS NULL "
            "OR decommissioned_at >= commissioned_at",
            name="ck_fixed_assets_decommissioned_at_commissioned_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    inv_number: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(
        Text, ForeignKey("fixed_asset_types.code", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        Text,
        ForeignKey("fixed_asset_statuses.code", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        server_default=text("'operational'"),
    )
    year_built: Mapped[int | None] = mapped_column(Integer)
    mileage: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    last_maint_date: Mapped[date | None] = mapped_column(Date)
    next_maint_date: Mapped[date | None] = mapped_column(Date)
    initial_cost: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    owner: Mapped[str | None] = mapped_column(Text)
    wialon_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    gtk_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    serial_number: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_models.id", ondelete="RESTRICT")
    )
    accounting_inv_number: Mapped[str | None] = mapped_column(Text)
    commissioned_at: Mapped[date | None] = mapped_column(Date)
    decommissioned_at: Mapped[date | None] = mapped_column(Date)
    inv_number_is_provisional: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("false")
    )
    # Operational telemetry and maintenance state are not passport identity.
    wialon_last_sync: Mapped[datetime | None]
    wialon_speed: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    wialon_online: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    failure_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    health_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    predicted_failure_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    last_ml_update: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )

    @property
    def name(self) -> str:
        type_name = getattr(self, "_asset_type_name", None) or self.asset_type
        return f"{type_name} {self.serial_number or ''}-{self.inv_number}"

    @name.setter
    def name(self, value: str | None) -> None:
        self._legacy_name = value

    @property
    def series(self) -> str | None:
        return getattr(self, "_asset_series", None)

    @series.setter
    def series(self, value: str | None) -> None:
        self._asset_series = value

    @property
    def depot(self) -> str | None:
        return getattr(self, "_asset_depot", None)

    @depot.setter
    def depot(self, value: str | None) -> None:
        self._asset_depot = value

    @property
    def number(self) -> str | None:
        return self.serial_number

    @number.setter
    def number(self, value: str | None) -> None:
        self.serial_number = value

    @property
    def number_normalized(self) -> str | None:
        if self.serial_number:
            from app.services.asset_passport import normalize_token

            return normalize_token(self.serial_number) or None
        return getattr(self, "_number_normalized", None)

    @number_normalized.setter
    def number_normalized(self, value: str | None) -> None:
        self._number_normalized = value

    @property
    def org_unit_id(self) -> uuid.UUID | None:
        return self.section_id

    @org_unit_id.setter
    def org_unit_id(self, value: uuid.UUID | None) -> None:
        self.section_id = value

    @property
    def comm_date(self) -> date | None:
        return self.commissioned_at

    @comm_date.setter
    def comm_date(self, value: date | None) -> None:
        self.commissioned_at = value


class MileageHistory(Base):
    __tablename__ = "mileage_history"
    __table_args__ = (
        CheckConstraint(
            "source IN ('wialon','manual','gtk')",
            name="mileage_history_source_check",
        ),
        Index(
            "ix_mileage_asset_time",
            "asset_id",
            text("recorded_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False
    )
    mileage: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'wialon'")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class WialonSettings(Base):
    __tablename__ = "wialon_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="wialon_settings_id_check"),
    )

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, server_default=text("1")
    )
    host: Mapped[str | None] = mapped_column(Text)
    token: Mapped[str | None] = mapped_column(Text)
    sync_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5")
    )
    auto_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    last_sync_at: Mapped[datetime | None]
    last_sync_status: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


def fixed_asset_name_expression():
    from app.models.localization import FixedAssetTypeTranslation

    type_name = (
        select(FixedAssetTypeTranslation.name)
        .where(
            FixedAssetTypeTranslation.type_code == FixedAsset.asset_type,
            FixedAssetTypeTranslation.locale == "ru",
        )
        .limit(1)
        .scalar_subquery()
    )
    return func.concat(
        func.coalesce(type_name, FixedAsset.asset_type),
        " ",
        func.coalesce(FixedAsset.serial_number, ""),
        "-",
        FixedAsset.inv_number,
    )
