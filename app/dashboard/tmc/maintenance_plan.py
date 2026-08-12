import uuid
from pydantic import BaseModel, ConfigDict
from datetime import date


class MaintenancePlanBase(BaseModel):
    asset_id: uuid.UUID
    asset_name: str
    maintenance_type: str
    trigger_mileage: int | None = None
    scheduled_date: date | None = None
    status: str = "Scheduled"


class MaintenancePlanCreate(MaintenancePlanBase):
    pass


class MaintenancePlanUpdate(BaseModel):
    scheduled_date: date | None = None
    status: str | None = None
    trigger_mileage: int | None = None


class MaintenancePlanRead(MaintenancePlanBase):
    id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)