from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DataMigrationBatchRead(BaseModel):
    id: UUID
    name: str
    source_file: str
    field: str
    description: str | None
    created_at: datetime
    total: int
    applied: int
    reverted: int


class DataMigrationItemRead(BaseModel):
    id: int
    batch_id: UUID
    asset_id: UUID
    inv_number: str | None
    serial_number: str | None
    asset_name: str | None
    asset_type: str | None
    section_name: str | None
    old_value: str | None
    new_value: str | None
    current_value: str | None  # what the asset holds right now (it may differ if someone changed it elsewhere)
    raw_value: str | None
    status: str
    updated_at: datetime


class DataMigrationItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_value: str


class DataMigrationRevertResult(BaseModel):
    reverted: int
    skipped_changed_elsewhere: int
    already_reverted: int
