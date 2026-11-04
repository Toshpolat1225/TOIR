from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AssetModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    name_normalized: str
    asset_type: str
    series: str | None
