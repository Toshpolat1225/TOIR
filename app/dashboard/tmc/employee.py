import uuid
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class EmployeeBase(BaseModel):
    full_name: str
    tab_number: str
    position: str | None = None
    section_id: uuid.UUID | None = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    tab_number: str | None = None
    position: str | None = None
    section_id: uuid.UUID | None = None


class EmployeeRead(EmployeeBase):
    id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)