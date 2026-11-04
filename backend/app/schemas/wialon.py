from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.assets import FixedAssetRead


class WialonSyncResult(BaseModel):
    found: int
    updated: int
    not_found: int
    not_found_units: list[str]


class WialonSyncStatus(BaseModel):
    enabled: bool
    interval_minutes: int
    last_sync_at: datetime | None
    last_sync_status: str | None


class WialonLinkedAssetRead(BaseModel):
    id: UUID
    name: str
    inv_number: str


class WialonCounterSummary(BaseModel):
    last_status: str | None
    last_reason: str | None


class WialonRejectedReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    counter: str
    value: Decimal | None
    previous_value: Decimal | None
    reading_at: datetime | None
    reason: str
    created_at: datetime


class WialonUnitRead(BaseModel):
    unit_id: str
    name: str
    cnm: Decimal | None
    cneh: Decimal | None
    speed: Decimal | None
    last_message_at: datetime | None
    is_online: bool
    suspect_absolute: bool
    linked_asset: WialonLinkedAssetRead | None
    counter_state: WialonCounterSummary | None
    rejected_count: int


class WialonUnitDetail(WialonUnitRead):
    rejected_readings: list[WialonRejectedReadingRead]


class WialonAssetSuggestion(BaseModel):
    asset_id: UUID
    name: str
    inv_number: str
    asset_type: str
    series: str | None
    section_id: UUID | None
    matched_series: bool
    matched_numbers: list[int]


class WialonAssetSuggestions(BaseModel):
    items: list[WialonAssetSuggestion]


class WialonCreateAssetRequest(BaseModel):
    inv_number: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    asset_type: Literal["locomotive", "diesel", "wagon"]
    series: str | None = None
    model_id: UUID | None = None
    number: str | None = None
    section_id: UUID | None = None

    @model_validator(mode="after")
    def normalize_text(self):
        self.inv_number = self.inv_number.strip()
        if not self.inv_number:
            raise ValueError("Inventory number must not be empty")
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("Name must not be empty")
        for field_name in ("series", "number"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, value.strip() or None)
        return self


class WialonCreateAssetResponse(BaseModel):
    asset: FixedAssetRead
    warning: str | None


class UnifiedAssetRead(BaseModel):
    source: Literal["toir", "wialon", "both"]
    asset_id: UUID | None
    unit_id: str | None
    name: str
    asset_type: str | None
    series: str | None
    inv_number: str | None
    status: str | None
    section: str | None
    section_id: UUID | None
    mileage: Decimal | None
    wialon_cnm: Decimal | None
    wialon_cneh: Decimal | None
    speed: Decimal | None
    last_message_at: datetime | None
    is_online: bool
    suspect_absolute: bool
