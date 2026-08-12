import uuid
from pydantic import BaseModel, ConfigDict


class MaintenanceIntervalBase(BaseModel):
    code: str
    name: str
    interval_km: int | None = None
    asset_types: list[str] | None = []
    is_active: bool = True


class MaintenanceIntervalCreate(MaintenanceIntervalBase):
    pass


class MaintenanceIntervalUpdate(BaseModel):
    name: str | None = None
    interval_km: int | None = None
    asset_types: list[str] | None = None
    is_active: bool | None = None


class MaintenanceIntervalRead(MaintenanceIntervalBase):
    id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)