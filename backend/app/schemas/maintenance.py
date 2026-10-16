from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MaintenancePlanStatus = Literal[
    "scheduled", "in_progress", "completed", "cancelled"
]
MaintenanceDisplayStatus = Literal[
    "upcoming", "in_progress", "completed", "overdue"
]


class MaintenanceSettingsRead(BaseModel):
    daily_average_km: Decimal | None


class MaintenanceSettingsUpdate(BaseModel):
    daily_average_km: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class MaintenancePlanUpdate(BaseModel):
    status: MaintenancePlanStatus | None = None
    completed_date: date | None = None
    work_order_id: UUID | None = None


class MaintenancePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    asset_name: str
    asset_inv_number: str
    section_id: UUID | None
    interval_id: UUID
    interval_code: str
    interval_name: str
    work_type_id: UUID | None
    status: MaintenancePlanStatus
    trigger_mileage: Decimal | None
    scheduled_date: date | None
    completed_date: date | None
    work_order_id: UUID | None


class MaintenanceScheduleItem(BaseModel):
    id: str
    entity_type: Literal["work_order", "maintenance_plan", "forecast"]
    unit: str
    type: str
    startDate: date
    durationH: int = 8
    depot: str
    tech: str
    status: MaintenanceDisplayStatus
    note: str | None = None
    mileage: Decimal | None = None
    remainingKm: Decimal | None = None
    nextThreshold: Decimal | None = None
    asset_id: UUID
    section_id: UUID | None = None
    interval_id: UUID | None = None
    work_type_id: UUID | None = None
    plan_id: UUID | None = None
    work_order_id: UUID | None = None


class MaintenanceScheduleRead(BaseModel):
    schedule: list[MaintenanceScheduleItem]
    daily_average_km: Decimal | None
