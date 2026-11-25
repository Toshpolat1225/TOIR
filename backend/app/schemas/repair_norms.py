from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Section = Literal["materials", "spare_parts", "lubricants"]
Basis = Literal["per_repair", "per_month_per_unit"]


class RepairNormSetRead(BaseModel):
    work_type_id: UUID
    work_type_code: str
    asset_type: str
    asset_model_id: UUID | None
    norm_group: str
    basis: Basis
    model_name: str | None
    total: int
    materials: int
    spare_parts: int
    lubricants: int
    alternatives: int
    source_file: str | None


class RepairNormItemRead(BaseModel):
    id: UUID
    work_type_id: UUID
    asset_type: str
    asset_model_id: UUID | None
    norm_group: str
    seq: int
    section: Section
    group_name: str | None
    basis: Basis
    name: str
    unit: str | None
    quantity: Decimal | None
    quantity_text: str
    parent_id: UUID | None
    note: str | None
    source_file: str | None
    source_sheet: str | None
    updated_at: datetime


class RepairNormItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_type_id: UUID
    asset_type: str = Field(min_length=1, max_length=40)
    asset_model_id: UUID | None = None
    norm_group: str = Field(default="", max_length=200)
    basis: Basis = "per_repair"
    section: Section = "materials"
    group_name: str | None = Field(default=None, max_length=300)
    name: str = Field(min_length=1, max_length=500)
    unit: str | None = Field(default=None, max_length=40)
    quantity_text: str = Field(min_length=1, max_length=100)
    parent_id: UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class RepairNormItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Section | None = None
    group_name: str | None = Field(default=None, max_length=300)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    unit: str | None = Field(default=None, max_length=40)
    quantity_text: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "RepairNormItemUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for field in ("section", "name", "quantity_text"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
