from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.references import PatchModel


class NomenclatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    department_id: UUID
    department_name: str
    name: str
    code: str | None
    unit: str
    extra: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class NomenclatureCreate(BaseModel):
    department_id: UUID
    name: str = Field(min_length=1)
    code: str | None = None
    unit: str = Field(default="шт.", min_length=1)
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_values(self):
        self.name = self.name.strip()
        self.unit = self.unit.strip()
        if not self.name or not self.unit:
            raise ValueError("Name and unit must not be empty")
        if self.code is not None:
            self.code = self.code.strip() or None
        return self


class NomenclatureUpdate(PatchModel):
    department_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1)
    code: str | None = None
    unit: str | None = Field(default=None, min_length=1)
    extra: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_values(self):
        for field_name in ("department_id", "name", "unit", "extra"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        for field_name in ("name", "unit"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if not value.strip():
                    raise ValueError(f"{field_name} must not be empty")
                setattr(self, field_name, value.strip())
        if "code" in self.model_fields_set and self.code is not None:
            self.code = self.code.strip() or None
        return self


class NomenclatureNormRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nomenclature_id: UUID
    department_id: UUID
    work_type_id: UUID
    standard_quantity: Decimal
    avg_price: Decimal
    min_quantity: Decimal | None
    max_quantity: Decimal | None
    nomenclature_name: str
    nomenclature_code: str | None
    nomenclature_unit: str
    work_type_code: str
    created_at: datetime
    updated_at: datetime


class NomenclatureNormCreate(BaseModel):
    nomenclature_id: UUID
    department_id: UUID
    work_type_id: UUID
    standard_quantity: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    avg_price: Decimal = Field(default=Decimal("0"), max_digits=14, decimal_places=2)
    min_quantity: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    max_quantity: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)

    @model_validator(mode="after")
    def validate_quantity_range(self):
        if (
            self.min_quantity is not None
            and self.max_quantity is not None
            and self.min_quantity > self.max_quantity
        ):
            raise ValueError("min_quantity cannot exceed max_quantity")
        return self


class NomenclatureNormUpdate(PatchModel):
    nomenclature_id: UUID | None = None
    department_id: UUID | None = None
    work_type_id: UUID | None = None
    standard_quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=3
    )
    avg_price: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    min_quantity: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    max_quantity: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)

    @model_validator(mode="after")
    def validate_values(self):
        for field_name in (
            "nomenclature_id",
            "department_id",
            "work_type_id",
            "standard_quantity",
            "avg_price",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if (
            self.min_quantity is not None
            and self.max_quantity is not None
            and self.min_quantity > self.max_quantity
        ):
            raise ValueError("min_quantity cannot exceed max_quantity")
        return self
