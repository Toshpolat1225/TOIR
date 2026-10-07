from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PatchModel(BaseModel):
    @model_validator(mode="after")
    def require_patch_values(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1)
    color: str = "#3b82f6"

    @model_validator(mode="after")
    def normalize_values(self):
        self.name = self.name.strip()
        self.color = self.color.strip()
        if not self.name or not self.color:
            raise ValueError("Department name and color must not be empty")
        return self


class DepartmentUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1)
    color: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def normalize_values(self):
        for field_name in ("name", "color"):
            value = getattr(self, field_name)
            if field_name in self.model_fields_set:
                if value is None or not value.strip():
                    raise ValueError(f"{field_name} must not be empty")
                setattr(self, field_name, value.strip())
        return self


class SectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    department_id: UUID | None
    created_at: datetime
    updated_at: datetime


class SectionCreate(BaseModel):
    name: str = Field(min_length=1)
    department_id: UUID | None = None

    @model_validator(mode="after")
    def normalize_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Section name must not be empty")
        return self


class SectionUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1)
    department_id: UUID | None = None

    @model_validator(mode="after")
    def validate_name(self):
        if "name" in self.model_fields_set:
            if self.name is None or not self.name.strip():
                raise ValueError("Section name must not be empty")
            self.name = self.name.strip()
        return self


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tab_number: str
    full_name: str
    position: str | None
    section_id: UUID | None
    location_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EmployeeCreate(BaseModel):
    tab_number: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    position: str | None = None
    section_id: UUID | None = None
    location_id: str | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def normalize_values(self):
        self.tab_number = self.tab_number.strip()
        self.full_name = self.full_name.strip()
        if not self.tab_number or not self.full_name:
            raise ValueError("Tab number and full name must not be empty")
        if self.position is not None:
            self.position = self.position.strip() or None
        if self.location_id is not None:
            self.location_id = self.location_id.strip() or None
        return self


class EmployeeUpdate(PatchModel):
    tab_number: str | None = Field(default=None, min_length=1)
    full_name: str | None = Field(default=None, min_length=1)
    position: str | None = None
    section_id: UUID | None = None
    location_id: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def normalize_values(self):
        for field_name in ("tab_number", "full_name"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if value is None or not value.strip():
                    raise ValueError(f"{field_name} must not be empty")
                setattr(self, field_name, value.strip())
        for field_name in ("position", "location_id"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if value is not None:
                    setattr(self, field_name, value.strip() or None)
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active cannot be null")
        return self


WorkUnitType = Literal["locomotive", "wagon"]


class WorkSubtaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_type_id: UUID
    name: str
    sort_order: int


class WorkSubtaskCreate(BaseModel):
    name: str = Field(min_length=1)
    sort_order: int = 0

    @model_validator(mode="after")
    def normalize_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Subtask name must not be empty")
        return self


class WorkSubtaskUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1)
    sort_order: int | None = None

    @model_validator(mode="after")
    def validate_values(self):
        if "name" in self.model_fields_set:
            if self.name is None or not self.name.strip():
                raise ValueError("Subtask name must not be empty")
            self.name = self.name.strip()
        if "sort_order" in self.model_fields_set and self.sort_order is None:
            raise ValueError("sort_order cannot be null")
        return self


class WorkTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    unit_type: WorkUnitType
    sort_order: int
    created_at: datetime
    updated_at: datetime
    subtasks: list[WorkSubtaskRead] = Field(default_factory=list)


class WorkTypeCreate(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    unit_type: WorkUnitType
    sort_order: int = 0

    @model_validator(mode="after")
    def normalize_values(self):
        self.code = self.code.strip()
        self.name = self.name.strip()
        if not self.code or not self.name:
            raise ValueError("Work type code and name must not be empty")
        if self.description is not None:
            self.description = self.description.strip() or None
        return self


class WorkTypeUpdate(PatchModel):
    code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    unit_type: WorkUnitType | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def normalize_values(self):
        for field_name in ("code", "name"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if value is None or not value.strip():
                    raise ValueError(f"{field_name} must not be empty")
                setattr(self, field_name, value.strip())
        if "description" in self.model_fields_set and self.description is not None:
            self.description = self.description.strip() or None
        for field_name in ("unit_type", "sort_order"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class MaintenanceIntervalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_type_id: UUID | None
    code: str
    name: str
    interval_km: Decimal | None
    interval_days: int | None
    asset_types: list[str]
    warn_percent: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MaintenanceIntervalCreate(BaseModel):
    work_type_id: UUID | None = None
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    interval_km: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    interval_days: int | None = None
    asset_types: list[str] = Field(default_factory=lambda: ["locomotive", "diesel"])
    warn_percent: Decimal = Field(default=Decimal("10"), max_digits=5, decimal_places=2)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_interval(self):
        self.code = self.code.strip()
        self.name = self.name.strip()
        if not self.code or not self.name:
            raise ValueError("Interval code and name must not be empty")
        if self.interval_km is None and self.interval_days is None:
            raise ValueError("At least one of interval_km or interval_days is required")
        self.asset_types = [asset_type.strip() for asset_type in self.asset_types]
        if any(not asset_type for asset_type in self.asset_types):
            raise ValueError("asset_types must not contain empty values")
        return self


class MaintenanceIntervalUpdate(PatchModel):
    work_type_id: UUID | None = None
    code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    interval_km: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    interval_days: int | None = None
    asset_types: list[str] | None = None
    warn_percent: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    is_active: bool | None = None

    @model_validator(mode="after")
    def normalize_values(self):
        for field_name in ("code", "name"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if value is None or not value.strip():
                    raise ValueError(f"{field_name} must not be empty")
                setattr(self, field_name, value.strip())
        if "asset_types" in self.model_fields_set:
            if self.asset_types is None:
                raise ValueError("asset_types cannot be null")
            self.asset_types = [asset_type.strip() for asset_type in self.asset_types]
            if any(not asset_type for asset_type in self.asset_types):
                raise ValueError("asset_types must not contain empty values")
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active cannot be null")
        if "warn_percent" in self.model_fields_set and self.warn_percent is None:
            raise ValueError("warn_percent cannot be null")
        return self


class TemplateNomenclatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str | None
    unit: str


class WorkTypeTemplateRead(BaseModel):
    id: UUID
    work_type_id: UUID
    work_type: str
    department_id: UUID | None
    nomenclature_id: UUID | None
    name: str | None
    inv_no: str | None
    unit: str | None
    default_quantity: Decimal
    is_required: bool
    note: str | None
    nomenclature: TemplateNomenclatureRead | None = None


class WorkTypeTemplateCreate(BaseModel):
    work_type_id: UUID
    department_id: UUID | None = None
    nomenclature_id: UUID | None = None
    name: str | None = None
    inv_no: str | None = None
    unit: str | None = None
    default_quantity: Decimal = Field(default=Decimal("1"), max_digits=12, decimal_places=3)
    is_required: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def require_template_target(self):
        if self.nomenclature_id is None and not (self.name and self.name.strip()):
            raise ValueError("Provide nomenclature_id or a template name")
        if self.name is not None:
            self.name = self.name.strip() or None
        if self.inv_no is not None:
            self.inv_no = self.inv_no.strip() or None
        if self.unit is not None:
            self.unit = self.unit.strip() or None
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class WorkTypeTemplateUpdate(PatchModel):
    department_id: UUID | None = None
    nomenclature_id: UUID | None = None
    name: str | None = None
    inv_no: str | None = None
    unit: str | None = None
    default_quantity: Decimal | None = Field(
        default=None, max_digits=12, decimal_places=3
    )
    is_required: bool | None = None
    note: str | None = None

    @model_validator(mode="after")
    def normalize_values(self):
        for field_name in ("name", "inv_no", "unit", "note"):
            if field_name in self.model_fields_set:
                value = getattr(self, field_name)
                if value is not None:
                    setattr(self, field_name, value.strip() or None)
        for field_name in ("default_quantity", "is_required"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self
