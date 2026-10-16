from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.references import PatchModel

OrderKind = Literal["planned", "unplanned", "repair", "emergency"]
OrderStatus = Literal["pending", "in_progress", "completed", "cancelled"]
OrderPriority = Literal["critical", "high", "normal", "low"]


class WorkOrderItemInput(BaseModel):
    nomenclature_id: UUID | None = None
    name: str = Field(min_length=1, max_length=500)
    inv_no: str | None = None
    unit: str | None = None
    qty: Decimal = Field(ge=0)
    note: str | None = None

    @model_validator(mode="after")
    def normalize_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Item name must not be empty")
        return self


class WorkOrderRepairInput(BaseModel):
    work_type_id: UUID
    items: list[WorkOrderItemInput] = Field(default_factory=list)


class WorkOrderCreate(BaseModel):
    fixed_asset_id: UUID
    maintenance_plan_id: UUID | None = None
    maintenance_interval_id: UUID | None = None
    maintenance_trigger_mileage: Decimal | None = Field(default=None, ge=0)
    section_id: UUID | None = None
    department_id: UUID | None = None
    order_kind: OrderKind
    priority: OrderPriority = "normal"
    executor_id: UUID
    chief_id: UUID | None = None
    description: str = Field(min_length=1)
    note: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    repairs: list[WorkOrderRepairInput] = Field(min_length=1)

    @model_validator(mode="after")
    def normalize_values(self):
        self.description = self.description.strip()
        if not self.description:
            raise ValueError("Description must not be empty")
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class WorkOrderUpdate(PatchModel):
    fixed_asset_id: UUID | None = None
    section_id: UUID | None = None
    department_id: UUID | None = None
    order_kind: OrderKind | None = None
    status: OrderStatus | None = None
    priority: OrderPriority | None = None
    executor_id: UUID | None = None
    chief_id: UUID | None = None
    description: str | None = Field(default=None, min_length=1)
    note: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    repairs: list[WorkOrderRepairInput] | None = None

    @model_validator(mode="after")
    def normalize_values(self):
        for field_name in (
            "fixed_asset_id",
            "section_id",
            "order_kind",
            "status",
            "priority",
            "description",
            "repairs",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if "description" in self.model_fields_set:
            if self.description is None or not self.description.strip():
                raise ValueError("Description must not be empty")
            self.description = self.description.strip()
        if "note" in self.model_fields_set and self.note is not None:
            self.note = self.note.strip() or None
        return self


class WorkOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repair_id: UUID
    nomenclature_id: UUID | None
    name: str
    inv_no: str | None
    unit: str | None
    qty: Decimal
    note: str | None
    sort_order: int


class WorkOrderRepairRead(BaseModel):
    id: UUID
    work_order_id: UUID
    work_type_id: UUID
    work_type_code: str
    work_type_name: str
    sort_order: int
    items: list[WorkOrderItemRead] = Field(default_factory=list)


class WorkOrderRead(BaseModel):
    id: UUID
    number: str
    fixed_asset_id: UUID
    asset_name: str
    asset_inv_number: str
    section_id: UUID
    section_name: str
    department_id: UUID | None
    order_kind: OrderKind
    status: OrderStatus
    priority: OrderPriority
    executor_id: UUID | None
    executor_name: str | None
    chief_id: UUID | None
    description: str
    note: str | None
    date_start: datetime | None
    date_end: datetime | None
    closed_at: datetime | None
    mileage_at_creation: Decimal | None
    mileage_threshold: Decimal | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    is_overdue: bool
    repairs: list[WorkOrderRepairRead] = Field(default_factory=list)


class NormCheckItem(BaseModel):
    nomenclature_id: UUID
    work_type_id: UUID
    qty: Decimal = Field(ge=0)


class NormCheckRequest(BaseModel):
    department_id: UUID
    items: list[NormCheckItem] = Field(min_length=1)


class NormCheckResult(BaseModel):
    nomenclature_id: UUID
    work_type_id: UUID
    qty: Decimal
    standard_quantity: Decimal | None
    deviation_percent: Decimal | None
    warning: bool
    estimated_cost: Decimal | None


class TemplateItemRead(BaseModel):
    id: UUID
    work_type_id: UUID
    work_type: str
    department_id: UUID | None
    nomenclature_id: UUID | None
    nomenclature_name: str | None
    name: str | None
    inv_no: str | None
    unit: str | None
    default_quantity: Decimal
    is_required: bool
    note: str | None
