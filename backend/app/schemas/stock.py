from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PurchaseStatus = Literal["ordered", "in_transit", "partial", "received", "cancelled"]


class SupplierTermWrite(BaseModel):
    supplier: str | None = Field(default=None, max_length=200)
    lead_time_days: int = Field(gt=0, le=3650)
    min_order_qty: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    safety_days: int = Field(default=14, ge=0, le=3650)
    note: str | None = Field(default=None, max_length=500)


class SupplierTermRead(SupplierTermWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nomenclature_id: UUID
    nomenclature_name: str | None = None
    updated_at: datetime


class PurchaseOrderWrite(BaseModel):
    supplier: str | None = Field(default=None, max_length=200)
    doc_no: str | None = Field(default=None, max_length=100)
    qty: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    qty_received: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=3)
    ordered_on: date | None = None
    expected_on: date | None = None
    status: PurchaseStatus = "ordered"
    note: str | None = Field(default=None, max_length=500)


class PurchaseOrderCreate(PurchaseOrderWrite):
    nomenclature_id: UUID


class PurchaseOrderRead(PurchaseOrderWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nomenclature_id: UUID
    nomenclature_name: str | None = None
    created_at: datetime
