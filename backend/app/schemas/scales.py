from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MatchStatus = Literal["pending", "ok", "no_loco", "no_gtk_train", "excluded"]


class ScaleCargoIn(BaseModel):
    code: int
    name: str = Field(max_length=100)


class ScaleTrainIn(BaseModel):
    """One row of the scale's `Составы`; times are the scale PC's local time without a zone."""

    src_id: int
    registered_on: date | None = None
    loco_number: str | None = Field(default=None, max_length=40)
    declared_wagons: int | None = Field(default=None, ge=0, le=500)
    reported_weight_t: float | None = None
    doc_weight_t: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cargo_code: int | None = None
    excavator: int | None = None
    operator_code: int | None = None


class ScaleWeighingIn(BaseModel):
    """One row of the scale's `Вагоны`."""

    src_id: int
    train_src_id: int
    position: int | None = None
    unit_label: str | None = Field(default=None, max_length=40)
    gross_t: float | None = None
    tare_t: float | None = None
    net_t: float | None = None
    capacity_t: float | None = None
    overload_t: float | None = None
    speed_kmh: float | None = None
    axles: int | None = Field(default=None, ge=0, le=32)
    weighed_at: datetime | None = None


class ScalesIngestIn(BaseModel):
    post: str = Field(pattern=r"^[0-9A-Za-z_-]{1,10}$")
    mode: Literal["live", "archive"] = "live"
    period: str | None = Field(default=None, max_length=40)
    tare_default_t: float | None = None
    capacity_norm_t: float | None = None
    cargo: list[ScaleCargoIn] = Field(default_factory=list, max_length=200)
    trains: list[ScaleTrainIn] = Field(default_factory=list, max_length=1000)
    weighings: list[ScaleWeighingIn] = Field(default_factory=list, max_length=5000)


class ScalesIngestResult(BaseModel):
    post: str
    trains_received: int
    trains_changed: int
    weighings_received: int
    weighings_changed: int
    weighings_orphaned: int
    rematched: int


class PostStatus(BaseModel):
    code: str
    name: str
    last_weighing_at: datetime | None
    last_pull_at: datetime | None
    silent_hours: float | None
    health: Literal["ok", "warn", "alert", "unknown"]
    collector: Literal["ok", "stale", "never"]
    trains_24h: int
    tonnes_24h: Decimal
    trains_7d: int
    match_rate_7d: float | None
    unmatched: int


class ScalesStatus(BaseModel):
    posts: list[PostStatus]
    trains_total: int
    unmatched_total: int  # what an operator can still fix (older weighings than the GTK history are counted separately)
    before_gtk_history: int
    gtk_history_from: datetime | None
    first_train_at: datetime | None
    last_train_at: datetime | None


class ScaleTrainRead(BaseModel):
    id: UUID
    post_code: str
    src_id: int
    started_at: datetime | None
    finished_at: datetime | None
    loco_number: str | None
    loco_asset_id: UUID | None
    loco_inv_number: str | None
    gtk_train_id: int | None
    declared_wagons: int | None
    wagon_rows: int
    dump_count: int
    traction_count: int
    carriages_total: int
    carriages_linked: int
    reported_weight_t: Decimal | None
    net_total_t: Decimal | None
    net_source: str | None
    cargo_name: str | None
    excavator: int | None
    match_status: MatchStatus
    match_method: str | None
    flags: list[str]


class ScaleTrainPage(BaseModel):
    items: list[ScaleTrainRead]
    total: int
    limit: int
    offset: int


class LocoCandidate(BaseModel):
    loco_gtk_id: int
    garage_number: str | None
    name: str | None
    asset_id: UUID | None
    asset_inv_number: str | None
    overlap_min: float


class UnmatchedTrain(ScaleTrainRead):
    candidates: list[LocoCandidate]


class UnmatchedPage(BaseModel):
    items: list[UnmatchedTrain]
    total: int
    limit: int
    offset: int


class CorrectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: Literal["loco_alias", "train_exclude", "train_gtk"]
    loco_number: str | None
    train_id: UUID | None
    asset_id: UUID | None
    asset_inv_number: str | None = None
    gtk_train_id: int | None
    note: str | None
    is_active: bool
    created_at: datetime


class CorrectionCreate(BaseModel):
    kind: Literal["loco_alias", "train_exclude", "train_gtk"]
    loco_number: str | None = Field(default=None, max_length=40)
    train_id: UUID | None = None
    asset_id: UUID | None = None
    gtk_train_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


class WorkDay(BaseModel):
    day: date
    trips: int
    tonnes: Decimal


class AssetWorkRead(BaseModel):
    asset_id: UUID
    kind: Literal["wagon", "locomotive"]
    date_from: date
    date_to: date
    trips: int
    tonnes: Decimal
    avg_tonnes_per_trip: Decimal | None
    estimated_share: float | None
    exact_share: float | None  # share of trips where the car's own weighing was paired (the rest use the train average)
    first_at: datetime | None
    last_at: datetime | None
    daily: list[WorkDay]


class DaySummary(BaseModel):
    day: date
    post_code: str
    trains: int
    tonnes: Decimal


class WagonTripRead(BaseModel):
    """One trip of one wagon: which wagon, when, how much, behind which locomotive, from which quarry."""

    train_id: UUID
    started_at: datetime | None
    post_code: str
    asset_id: UUID | None
    inv_number: str | None
    carriage_gtk_id: int
    gtk_name: str | None
    gtk_inventory_number: str | None
    position: int | None
    tonnes: Decimal | None
    basis: Literal["own", "train_avg", "estimated", "unknown"]
    loco_number: str | None
    loco_asset_id: UUID | None = None
    loco_inv_number: str | None
    cargo_name: str | None
    excavator: int | None
    train_total_t: Decimal | None


class WagonTripPage(BaseModel):
    items: list[WagonTripRead]
    total: int
    limit: int
    offset: int
    wagons_total: int
    tonnes_total: Decimal


class WagonTotalRead(BaseModel):
    asset_id: UUID | None
    inv_number: str | None
    carriage_gtk_id: int
    gtk_name: str | None
    gtk_inventory_number: str | None
    trips: int
    tonnes: Decimal
    avg_tonnes: Decimal | None
    own_trips: int
    last_at: datetime | None


class WagonTotalPage(BaseModel):
    items: list[WagonTotalRead]
    total: int
    limit: int
    offset: int
    trips_total: int
    tonnes_total: Decimal
