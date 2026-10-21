from datetime import datetime

from pydantic import BaseModel


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
