from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TmcDocumentItemRead(BaseModel):
    id: UUID
    nomenclature_id: UUID | None
    name: str
    inv_no: str | None
    unit: str | None
    qty: Decimal
    price: Decimal | None
    note: str | None
    sort_order: int


class TmcDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doc_no: str
    doc_date: date
    work_order_id: UUID | None
    work_order_number: str | None
    section_id: UUID | None
    work_type_id: UUID | None
    loco: str | None
    work_type: str | None
    depot: str | None
    warehouse: str | None
    issued_by: str | None
    accepted_by: str | None
    chief: str | None
    status: str
    created_at: datetime
    items: list[TmcDocumentItemRead]
