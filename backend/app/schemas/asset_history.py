"""«Where was it, when, with which traction unit and what was it doing»: the history of one wagon or locomotive."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.scales_insights import AssetIdentity, GtkCarriageInfo, GtkLocoInfo


class HistoryPoint(BaseModel):
    at: datetime
    lat: float
    lon: float
    speed: float | None = None
    source: Literal["own", "loco"]  # the asset's own fix, or the position of the locomotive that pulled it
    label: str | None = None


class WagonRef(BaseModel):
    carriage_gtk_id: int
    asset_id: UUID | None
    label: str


class HistorySegment(BaseModel):
    """A stretch of time a wagon stood in one GTK train (behind one locomotive), or a locomotive pulled one train."""

    from_at: datetime
    to_at: datetime | None
    is_open: bool
    train_gtk_id: int
    train_title: str | None
    loco_asset_id: UUID | None
    loco_inv_number: str | None
    loco_label: str | None
    cars: int
    km: float | None
    max_speed: float | None
    points: int
    activity: Literal["moving", "standing", "unknown"]
    trips: int  # weighings at the scales during the segment
    tonnes: Decimal
    wagons: list[WagonRef] = []  # locomotive history only: which wagons it pulled


class HistoryTrip(BaseModel):
    train_id: UUID
    started_at: datetime | None
    post_code: str
    tonnes: Decimal | None
    basis: str | None
    loco_number: str | None
    cargo_name: str | None
    cars: int | None


class LocoShare(BaseModel):
    loco_asset_id: UUID | None
    label: str
    hours: float
    segments: int


class HistoryCurrent(BaseModel):
    lat: float
    lon: float
    at: datetime
    source: Literal["own", "loco"]
    in_train: bool
    loco_label: str | None
    speed: float | None


class HistoryStats(BaseModel):
    segments: int
    coupled_hours: float
    km: float
    distinct_partners: int  # wagon: locomotives; locomotive: wagons
    trips: int
    tonnes: Decimal
    last_move_at: datetime | None


class AssetHistory(BaseModel):
    kind: Literal["wagon", "locomotive"]
    asset: AssetIdentity | None
    gtk_carriage: GtkCarriageInfo | None
    gtk_loco: GtkLocoInfo | None
    date_from: date
    date_to: date
    days: int
    gtk_history_from: datetime | None  # GTK keeps train compositions only since this moment
    track_from: datetime | None  # position history exists only since this moment
    current: HistoryCurrent | None
    segments: list[HistorySegment]
    trips: list[HistoryTrip]
    track: list[HistoryPoint]
    by_loco: list[LocoShare]
    stats: HistoryStats
