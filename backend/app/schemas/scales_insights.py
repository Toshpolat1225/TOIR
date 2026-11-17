"""Read models of the weighing-scale command center: overview, train / wagon / locomotive cards (many joins, one payload each)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

TripBasis = Literal["own", "train_avg", "estimated", "unknown"]


# ───────────── overview ─────────────
class Kpi(BaseModel):
    trains: int
    wagon_trips: int
    tonnes: Decimal
    avg_train_t: Decimal | None
    avg_car_t: Decimal | None
    overload_share: float | None  # trains with at least one car above its capacity
    matched_share: float | None  # trains placed on a GTK train
    estimated_share: float | None  # trains whose cargo is estimated (wagon rows missing)
    active_wagons: int
    active_locos: int


class DayPoint(BaseModel):
    day: date
    post_code: str
    trains: int
    tonnes: Decimal


class HourPoint(BaseModel):
    hour: int
    post_code: str
    trains: int
    tonnes: Decimal


class NamedTotal(BaseModel):
    key: str
    label: str
    trains: int
    tonnes: Decimal


class LocoTop(BaseModel):
    asset_id: UUID | None
    loco_number: str | None
    inv_number: str | None
    model_name: str | None
    trains: int
    tonnes: Decimal
    avg_train_t: Decimal | None


class WagonTop(BaseModel):
    asset_id: UUID | None
    carriage_gtk_id: int
    label: str
    trips: int
    tonnes: Decimal


class LaneTrain(BaseModel):
    id: UUID
    post_code: str
    started_at: datetime | None
    finished_at: datetime | None
    tonnes: Decimal | None
    match_status: str
    loco_number: str | None


class Quality(BaseModel):
    by_status: dict[str, int]
    flags: dict[str, int]
    before_gtk_history: int


class Overview(BaseModel):
    date_from: date
    date_to: date
    days: int
    kpi: Kpi
    previous: Kpi
    daily: list[DayPoint]
    hourly: list[HourPoint]
    by_cargo: list[NamedTotal]
    by_excavator: list[NamedTotal]
    top_locomotives: list[LocoTop]
    top_wagons: list[WagonTop]
    today: list[LaneTrain]
    quality: Quality


# ───────────── shared asset identity ─────────────
class AssetIdentity(BaseModel):
    asset_id: UUID
    inv_number: str
    name: str | None
    asset_type: str
    asset_type_name: str | None
    status: str
    status_name: str | None
    section_id: UUID | None
    section_name: str | None
    model_name: str | None
    owner: str | None
    year_built: int | None
    mileage: Decimal | None
    last_maint_date: date | None
    next_maint_date: date | None


class PlanItem(BaseModel):
    plan_id: UUID
    interval_code: str
    interval_name: str
    status: str
    scheduled_date: date | None
    trigger_mileage: Decimal | None


class WorkOrderItem(BaseModel):
    id: UUID
    number: str
    status: str
    order_kind: str
    description: str
    date_start: datetime | None
    closed_at: datetime | None


class Maintenance(BaseModel):
    last_service_at: date | None  # the latest of: completed work order, recorded baseline, the asset's own last_maint_date
    last_service_source: str | None
    trips_since: int
    tonnes_since: Decimal
    plans: list[PlanItem]
    work_orders: list[WorkOrderItem]
    work_orders_total: int


class Split(BaseModel):
    key: str
    label: str
    trips: int
    tonnes: Decimal


class Totals(BaseModel):
    trips: int
    tonnes: Decimal
    avg_tonnes: Decimal | None
    own_trips: int
    overload_trips: int
    first_at: datetime | None
    last_at: datetime | None


class WorkDayPoint(BaseModel):
    day: date
    trips: int
    tonnes: Decimal


class WagonTripBrief(BaseModel):
    train_id: UUID
    started_at: datetime | None
    post_code: str
    tonnes: Decimal | None
    basis: TripBasis
    position: int | None
    loco_number: str | None
    cargo_name: str | None


# ───────────── wagon card ─────────────
class GtkCarriageInfo(BaseModel):
    carriage_gtk_id: int
    name: str | None
    reg_number: str | None
    inventory_number: str | None
    model_name: str | None
    is_active: bool | None
    is_loaded: bool | None
    lat: Decimal | None
    lon: Decimal | None


class WagonCard(BaseModel):
    asset: AssetIdentity | None  # None = a GTK carriage not linked to a TOIR asset yet
    gtk: GtkCarriageInfo | None
    date_from: date
    date_to: date
    period: Totals
    all_time: Totals
    daily: list[WorkDayPoint]
    by_cargo: list[Split]
    by_loco: list[Split]
    by_excavator: list[Split]
    recent: list[WagonTripBrief]
    maintenance: Maintenance | None


# ───────────── locomotive card ─────────────
class WialonInfo(BaseModel):
    unit_id: str
    name: str
    last_message_at: datetime | None
    speed: Decimal | None
    lat: Decimal | None
    lon: Decimal | None


class GtkLocoInfo(BaseModel):
    gtk_id: int
    name: str | None
    garage_number: str | None
    model_name: str | None
    is_active: bool | None


class TrainBrief(BaseModel):
    id: UUID
    started_at: datetime | None
    post_code: str
    tonnes: Decimal | None
    net_source: str | None
    cars: int
    cargo_name: str | None
    match_status: str
    flags: list[str]


class LocoCard(BaseModel):
    asset: AssetIdentity
    gtk: GtkLocoInfo | None
    wialon: WialonInfo | None
    numbers_used: list[str]  # the numbers the operators typed for this locomotive (aliases / typos show up here)
    date_from: date
    date_to: date
    period: Totals
    all_time: Totals
    avg_cars: Decimal | None
    daily: list[WorkDayPoint]
    by_cargo: list[Split]
    by_excavator: list[Split]
    top_wagons: list[WagonTop]
    recent: list[TrainBrief]
    maintenance: Maintenance


# ───────────── train card ─────────────
class UnitRow(BaseModel):
    position: int | None
    kind: Literal["traction", "dump"]
    gross_t: Decimal | None
    tare_t: Decimal | None
    net_t: Decimal | None
    capacity_t: Decimal | None
    overload_t: Decimal | None
    speed_kmh: Decimal | None
    axles: int | None
    weighed_at: datetime | None
    carriage_gtk_id: int | None  # the GTK carriage paired with this dump car (by sequence)
    carriage_name: str | None
    asset_id: UUID | None
    inv_number: str | None


class CarriageRow(BaseModel):
    ord: int
    carriage_gtk_id: int
    gtk_name: str | None
    model_name: str | None
    asset_id: UUID | None
    inv_number: str | None
    unit_position: int | None
    net_t: Decimal | None


class TrainGtkInfo(BaseModel):
    gtk_train_id: int
    number: str | None
    title: str | None
    begin_time: datetime | None
    is_open: bool | None


class CorrectionBrief(BaseModel):
    id: UUID
    kind: str
    loco_number: str | None
    note: str | None
    created_at: datetime


class TrainCard(BaseModel):
    id: UUID
    post_code: str
    post_name: str
    src_id: int
    started_at: datetime | None
    finished_at: datetime | None
    registered_on: date | None
    loco_number: str | None
    cargo_name: str | None
    excavator: int | None
    operator_code: int | None
    declared_wagons: int | None
    wagon_rows: int
    dump_count: int
    traction_count: int
    reported_weight_t: Decimal | None
    doc_weight_t: Decimal | None
    net_total_t: Decimal | None
    net_source: str | None
    offset_t: Decimal | None  # reported weight minus real cargo (the scale counts the traction units too)
    avg_car_t: Decimal | None
    match_status: str
    match_method: str | None
    flags: list[str]
    loco: AssetIdentity | None
    gtk_loco: GtkLocoInfo | None
    gtk_train: TrainGtkInfo | None
    units: list[UnitRow]
    carriages: list[CarriageRow]
    prev_id: UUID | None
    next_id: UUID | None
    corrections: list[CorrectionBrief]
