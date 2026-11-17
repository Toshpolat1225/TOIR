from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PositionSource = Literal["wialon", "gtk", "gtk_gps", "train"]
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
    source: PositionSource  # where THIS point comes from; "train" = a wagon placed at its locomotive (GTK train)
    position_at: datetime | None = None  # when the source recorded the position (Wialon fix / GTK last sync)
    speed: Decimal | None = None  # km/h, Wialon only
    online: bool | None = None  # Wialon message in the last 15 minutes (for a train point: of the locomotive)
    train_number: str | None = None  # source "train": the GTK train the wagon is part of
    locomotive_asset_id: UUID | None = None  # source "train": the locomotive pulling it (hidden from a master of another section)
    locomotive_inv_number: str | None = None
    locomotive_name: str | None = None
    # Locomotives that have BOTH trackers (Wialon and GTK's own GPS): the verdict of comparing the two live fixes and the other fix
    gps_verdict: str | None = None  # confirmed | diverged | gtk_stale | wialon_stale | both_stale_agree | both_stale_apart | wialon_only | gtk_only
    gps_diff_m: float | None = None
    gps_wialon_age_min: float | None = None
    gps_gtk_age_min: float | None = None
    alt_source: Literal["wialon", "gtk_gps"] | None = None  # the OTHER tracker's fix (the point itself is the newer one)
    alt_lat: float | None = None
    alt_lon: float | None = None
    alt_position_at: datetime | None = None


class AssetMapSummary(BaseModel):
    total_assets: int = 0  # assets in scope (before the source filter)
    placed: int = 0
    unplaced: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)  # placed assets by the source of their point
    unplaced_reasons: dict[str, int] = Field(default_factory=dict)  # no_link / no_position
    gps_verdicts: dict[str, int] = Field(default_factory=dict)  # locomotives with a GTK GPS unit, by the Wialon-vs-GTK verdict


class AssetMapRead(BaseModel):
    points: list[AssetMapPoint]
    summary: AssetMapSummary


# ---- the "without coordinates" page ---------------------------------------------------------------------
UnplacedGroup = Literal["no_link", "no_position"]
UnplacedDetail = Literal[
    "no_link",  # not linked to Wialon or GTK at all
    "wialon_unit_missing",  # linked to a Wialon unit that is not in our copy of Wialon
    "wialon_no_fix",  # the Wialon unit exists but has never sent a usable position
    "gtk_locomotive_only",  # a locomotive linked only to GTK, which has no coordinates for locomotives
    "gtk_carriage_missing",  # linked to a GTK carriage that is not in our copy of GTK
    "gtk_no_coords",  # the GTK carriage exists but GTK gives no coordinates for it
    "train_no_gps",  # the wagon is in an open GTK train, but no locomotive of it has a GPS position
]


class GtkCandidate(BaseModel):
    """A GTK carriage that probably is this unlinked wagon (same inventory and/or registration number)."""

    gtk_id: int
    name: str | None = None
    reg_number: str | None = None
    inventory_number: str | None = None
    is_active: bool = True
    has_coordinates: bool = False
    match: Literal["inv_and_reg", "inv", "reg"]
    taken_by_inv_number: str | None = None  # the carriage is already linked to ANOTHER asset (a possible duplicate)


class AssetUnplacedItem(BaseModel):
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
    group: UnplacedGroup
    reason: UnplacedDetail
    asset_created_at: datetime | None = None  # since when the system knows the asset
    wialon_external_id: str | None = None  # the Wialon unit id the asset is linked to (even if we do not have that unit)
    wialon_unit_id: str | None = None
    wialon_unit_name: str | None = None
    wialon_linked_at: datetime | None = None
    wialon_first_seen_at: datetime | None = None
    wialon_last_message_at: datetime | None = None
    wialon_last_synced_at: datetime | None = None
    gtk_external_id: str | None = None  # the GTK id the asset is linked to (even if we do not have that carriage)
    gtk_carriage_id: int | None = None
    gtk_carriage_name: str | None = None
    gtk_linked_at: datetime | None = None
    gtk_first_seen_at: datetime | None = None
    gtk_last_synced_at: datetime | None = None
    gtk_is_active: bool | None = None
    train_number: str | None = None  # an open GTK train the wagon is part of
    train_has_locomotive: bool | None = None
    candidate: GtkCandidate | None = None


class TypeCount(BaseModel):
    value: str
    label: str
    count: int


class AssetUnplacedSummary(BaseModel):
    total: int = 0  # all assets without coordinates in scope (before the reason/type/search filters)
    by_group: dict[str, int] = Field(default_factory=dict)
    by_reason: dict[str, int] = Field(default_factory=dict)
    by_type: list[TypeCount] = Field(default_factory=list)
    linkable: int = 0  # unlinked wagons with a free GTK carriage of the same inventory AND registration number


class AssetUnplacedPage(BaseModel):
    items: list[AssetUnplacedItem]
    total: int  # after the filters
    limit: int
    offset: int
    summary: AssetUnplacedSummary
