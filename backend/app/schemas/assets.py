from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssetType = str
AssetStatus = str
MileageSource = Literal["manual", "wialon"]


class PatchModel(BaseModel):
    @model_validator(mode="after")
    def require_patch_values(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class FixedAssetCreate(BaseModel):
    inv_number: str = Field(min_length=1)
    name: str = Field(min_length=1)
    asset_type: AssetType
    series: str | None = None
    depot: str | None = None
    section_id: UUID | None = None
    status: AssetStatus = "operational"
    comm_date: date | None = None
    year_built: int | None = None
    mileage: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    last_maint_date: date | None = None
    next_maint_date: date | None = None
    initial_cost: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    owner: str | None = None
    wialon_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def normalize_text(self):
        for field_name in ("inv_number", "name"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            setattr(self, field_name, value)
        for field_name in ("series", "depot", "owner", "wialon_id"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, value.strip() or None)
        return self


class FixedAssetUpdate(PatchModel):
    inv_number: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    asset_type: AssetType | None = None
    series: str | None = None
    depot: str | None = None
    section_id: UUID | None = None
    status: AssetStatus | None = None
    comm_date: date | None = None
    year_built: int | None = None
    mileage: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    last_maint_date: date | None = None
    next_maint_date: date | None = None
    initial_cost: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    owner: str | None = None
    wialon_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def normalize_text(self):
        for field_name in ("inv_number", "name"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if value is None or not value.strip():
                    raise ValueError(f"{field_name} must not be empty")
                setattr(self, field_name, value.strip())
        for field_name in ("series", "depot", "owner", "wialon_id"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if value is not None:
                    setattr(self, field_name, value.strip() or None)
        for field_name in ("asset_type", "status", "mileage"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class FixedAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inv_number: str
    name: str
    asset_type: AssetType
    series: str | None
    depot: str | None
    section_id: UUID | None
    status: AssetStatus
    comm_date: date | None
    year_built: int | None
    mileage: Decimal
    last_maint_date: date | None
    next_maint_date: date | None
    initial_cost: Decimal | None
    owner: str | None
    wialon_id: str | None
    wialon_last_sync: datetime | None
    wialon_speed: Decimal | None
    wialon_online: bool
    failure_probability: Decimal | None
    health_score: Decimal | None
    predicted_failure_km: Decimal | None
    last_ml_update: datetime | None
    created_at: datetime
    updated_at: datetime


class FixedAssetStats(BaseModel):
    total: int
    by_asset_type: dict[str, int]
    by_status: dict[str, int]
    by_status_behavior: dict[str, int]
    by_section: dict[str, int]
    depots: list[str]


class MileageUpdate(BaseModel):
    mileage: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class MileageHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: UUID
    mileage: Decimal
    source: MileageSource
    recorded_at: datetime


class MileageHistoryList(BaseModel):
    items: list[MileageHistoryRead]
    total: int
    days: int
    limit: int


def asset_read(asset: object) -> FixedAssetRead:
    result = FixedAssetRead.model_validate(asset)
    last_sync = result.wialon_last_sync
    is_recent = (
        last_sync is not None
        and last_sync >= datetime.now(timezone.utc) - timedelta(minutes=15)
    )
    return result.model_copy(update={"wialon_online": is_recent})
