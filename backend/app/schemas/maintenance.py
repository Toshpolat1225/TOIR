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
MaintenanceUrgency = Literal["high", "medium", "low"]


class MaintenanceSettingsRead(BaseModel):
    daily_average_km: Decimal | None


class MaintenanceSettingsUpdate(BaseModel):
    daily_average_km: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class MaintenancePlanUpdate(BaseModel):
    status: MaintenancePlanStatus | None = None
    completed_date: date | None = None
    work_order_id: UUID | None = None
    # Manual rescheduling. `scheduled_date` moves the planned day; `reset_schedule` returns to the
    # system recommendation. Neither can be combined with the fields above.
    scheduled_date: date | None = None
    reschedule_reason: str | None = Field(default=None, max_length=500)
    reset_schedule: bool = False


class MaintenancePlanFromForecast(BaseModel):
    """Turn a forecast row into a real plan on a date chosen by the planner."""

    asset_id: UUID
    interval_id: UUID
    scheduled_date: date
    reschedule_reason: str | None = Field(default=None, max_length=500)


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
    urgency: MaintenanceUrgency | None = None
    status: MaintenancePlanStatus
    trigger_mileage: Decimal | None
    scheduled_date: date | None
    completed_date: date | None
    work_order_id: UUID | None
    scheduled_date_manual: bool = False
    recommended_date: date | None = None
    reschedule_reason: str | None = None


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
    # Length of the interval (km) the threshold belongs to; lets the UI show progress
    # inside the CURRENT interval instead of against the absolute odometer value.
    intervalKm: Decimal | None = None
    urgency: MaintenanceUrgency | None = None
    asset_id: UUID
    section_id: UUID | None = None
    interval_id: UUID | None = None
    work_type_id: UUID | None = None
    plan_id: UUID | None = None
    work_order_id: UUID | None = None
    # Joined display data of the asset (names instead of codes); the same for every item of one asset.
    asset_type: str | None = None
    asset_type_name: str | None = None
    asset_model: str | None = None
    asset_serial: str | None = None
    asset_inv_number: str | None = None
    asset_status: str | None = None
    asset_status_name: str | None = None
    asset_online: bool | None = None
    # Manual rescheduling state of a plan (always False/None for forecasts and work orders).
    dateManual: bool = False
    recommendedDate: date | None = None
    rescheduleReason: str | None = None


class MaintenanceScheduleRead(BaseModel):
    schedule: list[MaintenanceScheduleItem]
    daily_average_km: Decimal | None
