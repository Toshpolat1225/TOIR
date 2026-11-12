from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MileageOpeningCreate(BaseModel):
    asset_id: UUID
    mileage_km: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    effective_at: datetime
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("effective_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("effective_at must include a timezone")
        return value


class MileageOpeningRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    mileage_km: Decimal
    effective_at: datetime
    created_by: UUID | None
    approved_by: UUID | None
    supersedes_id: UUID | None
    note: str | None
    status: Literal["pending", "approved", "rejected", "superseded"]
    approved_at: datetime | None
    created_at: datetime


class MileageOpeningList(BaseModel):
    items: list[MileageOpeningRead]
    total: int
    limit: int
    offset: int


class MileageLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    wagon_asset_id: UUID
    locomotive_asset_id: UUID | None
    train_gtk_id: int | None
    period_from: datetime
    period_to: datetime
    distance_km: Decimal
    estimated: bool
    classification: Literal["CONFIRMED", "ESTIMATED", "HELD"]
    calculation_eligible: bool
    status: Literal["active", "superseded", "rejected"]
    supersedes_id: UUID | None
    calculation_details: dict
    created_at: datetime


class WagonMileageSummary(BaseModel):
    asset_id: UUID
    opening_balance_km: Decimal | None
    projected_km: Decimal | None
    confirmed_km: Decimal
    estimated_km: Decimal
    held_km: Decimal
    held_reasons: dict[str, int]
    items: list[MileageLedgerRead]
    total: int
    limit: int
    offset: int
