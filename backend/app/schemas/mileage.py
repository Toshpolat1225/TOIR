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
