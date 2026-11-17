"""Trains on the line drawn to scale: every vehicle with its own centre, heading, length and width (metres)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

VehicleKind = Literal["electric", "diesel", "loco", "motor", "dump", "tank", "platform"]


class FormationVehicle(BaseModel):
    role: Literal["loco", "motor", "wagon"]
    kind: VehicleKind
    ord: int  # 0 = the locomotive, 1.. = the GTK order of the cars behind it
    asset_id: UUID | None
    carriage_gtk_id: int | None
    label: str | None
    lat: float
    lon: float
    heading: float  # degrees clockwise from north, the direction the train travels
    length_m: float
    width_m: float
    is_loaded: bool | None = None
    hidden: bool = False  # a master does not see the identity of another section's wagon


class LiveTrain(BaseModel):
    gtk_train_id: int
    number: str | None
    title: str | None
    loco_asset_id: UUID | None
    loco_inv_number: str | None
    loco_name: str | None
    loco_model: str | None
    loco_kind: Literal["electric", "diesel", "loco"]
    lat: float
    lon: float
    speed: float | None
    online: bool | None
    position_at: datetime | None
    heading: float
    heading_known: bool  # False: the locomotive has no recorded movement, the drawing direction is a default
    moving: bool
    wagons_count: int
    length_m: float
    vehicles: list[FormationVehicle]


class LiveTrains(BaseModel):
    generated_at: datetime
    trains: list[LiveTrain]
