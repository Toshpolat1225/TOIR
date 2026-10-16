from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DashboardAsset(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    asset_type: str
    series: str | None
    status: str
    section: str | None
    depot: str | None
    mileage: Decimal


class DashboardOrder(BaseModel):
    id: UUID
    number: str
    unit: str
    section: str
    section_id: UUID
    status: str
    priority: str
    description: str
    created_at: datetime
    date_start: datetime | None
    tech: str | None
    repair_kind: str | None


class DashboardAvailability(BaseModel):
    month: str
    label: str
    pct: float


class DashboardSummary(BaseModel):
    assets: list[DashboardAsset]
    orders: list[DashboardOrder]
    availability: list[DashboardAvailability]
