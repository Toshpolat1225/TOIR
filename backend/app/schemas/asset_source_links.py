from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AssetLinkSource = Literal["wialon", "gtk", "vesavoy", "onec"]
AssetLinkStatus = Literal["active", "ended"]
AssetLinkMethod = Literal["manual", "migrated", "import"]


class AssetSourceLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    source: AssetLinkSource
    external_id: str
    external_name: str | None
    status: AssetLinkStatus
    link_method: AssetLinkMethod
    linked_by: UUID | None
    linked_at: datetime
    unlinked_at: datetime | None
    note: str | None


class AssetSourceLinksRead(BaseModel):
    asset_id: UUID
    items: list[AssetSourceLinkRead]


class AssetSourceLinkCreate(BaseModel):
    source: AssetLinkSource
    external_id: str = Field(min_length=1, max_length=100)
    external_name: str | None = None
