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
