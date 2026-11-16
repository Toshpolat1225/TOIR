from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AssetFieldChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: UUID
    field: str
    old_value: Any | None
    new_value: Any | None
    source: str
    kind: Literal["auto_fill", "conflict", "manual"]
    status: Literal["applied", "pending", "accepted", "rejected"]
    created_at: datetime
    resolved_by: UUID | None
    resolved_at: datetime | None


class AssetConflictRow(AssetFieldChangeRead):
    asset_inv_number: str
    asset_serial_number: str | None = None
    asset_type: str


class WialonCounterBlockRead(BaseModel):
    asset_id: UUID
    inv_number: str
    serial_number: str | None = None
    asset_type: str
    section_id: UUID | None = None
    wialon_id: str | None = None
    blocked_since: datetime
    last_cnm: float | None = None
    last_cnm_at: datetime | None = None
    blocked_readings_24h: int
    affected_wagons: int


class WialonCounterBlockList(BaseModel):
    items: list[WialonCounterBlockRead]
    total: int
    limit: int
    offset: int
    blocked_locomotives: int
    affected_wagons: int
