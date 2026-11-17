from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GpsFix(BaseModel):
    lat: float
    lon: float
    at: datetime | None = None
    speed: float | None = None  # km/h
    age_min: float | None = None
    fresh: bool = False  # newer than 30 minutes


class GpsPositionCheck(BaseModel):
    verdict: str  # see services.gps_compare.PositionVerdict
    diff_m: float | None = None
    lag_s: float | None = None
    tolerance_m: float | None = None
    best: str | None = None  # "wialon" | "gtk": the newer valid fix, the one the map draws


class GpsDayRow(BaseModel):
    day: date  # local day (UTC+5)
    wialon_m: int | None = None  # length of the stored Wialon track that day
    wialon_points: int = 0
    gtk_m: int | None = None  # GTK's own distance figure
    gtk_points: int = 0  # stored (thinned) GTK points
    gtk_raw_points: int = 0  # points GTK returned
    gtk_final: bool = False
    verdict: str  # see services.gps_compare.DistanceVerdict
    ratio: float | None = None  # GTK / Wialon
    diff_m: int | None = None  # GTK - Wialon
    unified_m: int | None = None
    idle_events: int | None = None  # GTK "no reason idle" events (stops) that day


class GpsAssetRow(BaseModel):
    asset_id: UUID
    inv_number: str
    name: str
    asset_type: str
    asset_type_name: str | None = None
    model_name: str | None = None
    section_id: UUID | None = None
    section_name: str | None = None
    wialon_linked: bool = False
    gtk_linked: bool = False
    wialon: GpsFix | None = None
    gtk: GpsFix | None = None
    position: GpsPositionCheck
    days: list[GpsDayRow] = Field(default_factory=list)  # newest first
    week_wialon_m: int = 0
    week_gtk_m: int = 0
    week_unified_m: int = 0
    distance_issues: int = 0  # days with a gap or a minor difference
    severity: int = 0  # 0 ok, 1 one source only / minor, 2 a source is silent or has gaps, 3 diverged
    status: str = "ok"  # ok | warn | bad


class GpsSummary(BaseModel):
    assets: int = 0
    both_sources: int = 0
    position_verdicts: dict[str, int] = Field(default_factory=dict)
    distance_verdicts: dict[str, int] = Field(default_factory=dict)  # over all asset-days in the window
    week_wialon_m: int = 0
    week_gtk_m: int = 0
    week_unified_m: int = 0
    ok: int = 0
    warn: int = 0
    bad: int = 0


class GpsFeedHealth(BaseModel):
    gtk_enabled: bool = False
    gtk_last_run_at: datetime | None = None
    gtk_last_status: str | None = None
    gtk_last_error: str | None = None
    gtk_running: bool = False  # a synchronisation (or a backfill) is in progress right now
    gtk_units: int = 0  # units GTK returned in the last run
    gtk_tracks_failed: int = 0
    gtk_units_synced_at: datetime | None = None
    wialon_units_synced_at: datetime | None = None
    gtk_track_points: int = 0
    wialon_track_points: int = 0
    gtk_track_from: datetime | None = None
    wialon_track_from: datetime | None = None
    utc_offset_hours: int = 5


class GpsOverview(BaseModel):
    items: list[GpsAssetRow]
    total: int
    limit: int
    offset: int
    summary: GpsSummary
    feed: GpsFeedHealth
    days: int
    date_from: date
    date_to: date


class GpsTrackPoint(BaseModel):
    at: datetime
    lat: float
    lon: float
    speed: float | None = None


class GpsAssetDetail(BaseModel):
    row: GpsAssetRow
    wialon_track: list[GpsTrackPoint]
    gtk_track: list[GpsTrackPoint]
    track_from: datetime
    track_to: datetime
    feed: GpsFeedHealth
