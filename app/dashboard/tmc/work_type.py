import uuid
from pydantic import BaseModel, ConfigDict


class WorkTypeBase(BaseModel):
    code: str
    name: str
    unit_type: str
    sort_order: int | None = None


class WorkTypeCreate(WorkTypeBase):
    pass


class WorkTypeUpdate(BaseModel):
    name: str | None = None
    unit_type: str | None = None
    sort_order: int | None = None


class WorkTypeRead(WorkTypeBase):
    id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)