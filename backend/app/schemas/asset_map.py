from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PositionSource = Literal["wialon", "gtk"]
UnplacedReason = Literal["no_link", "no_position"]


class AssetMapPoint(BaseModel):
    asset_id: UUID
    inv_number: str
    name: str
    asset_type: str
    asset_type_name: str | None = None
    status: str
    status_name: str | None = None
    section_id: UUID | None = None
    section_name: str | None = None
    model_name: str | None = None
    lat: float
    lon: float
    source: PositionSource  # where THIS point comes from
    position_at: datetime | None = None  # when the source recorded the position (Wialon fix / GTK last sync)
    speed: Decimal | None = None  # km/h, Wialon only
    online: bool | None = None  # Wialon message in the last 15 minutes


class AssetMapSummary(BaseModel):
    total_assets: int = 0  # assets in scope (before the source filter)
    placed: int = 0
    unplaced: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)  # placed assets by the source of their point
    unplaced_reasons: dict[str, int] = Field(default_factory=dict)  # no_link / no_position


class AssetMapRead(BaseModel):
    points: list[AssetMapPoint]
    summary: AssetMapSummary
