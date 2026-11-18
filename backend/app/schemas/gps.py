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
    # --- analytics (P1) ---
    cause: str = "ok"  # ok | method | day_open | gtk_dead | gtk_no_day | gtk_gaps | gtk_sparse | wialon_gaps | both_gaps | not_collected | idle | no_data
    fused_m: int | None = None  # the «единый трек» length: Wialon timeline with the gaps filled from GTK (+ straight bridges over silence)
    unknown_gap_m: int | None = None  # the part of fused_m that is only a straight bridge over a silent stretch (> 60 min without any fix)
    wialon_cov_h: float | None = None  # hours of the day covered by Wialon fixes no further apart than 60 min
    gtk_cov_h: float | None = None
    confidence: float | None = None  # 0..1: coverage of the day by the fused track x agreement of the trackers
    odo_m: int | None = None  # Wialon odometer delta over the local day (the third opinion)
    odo_agrees: bool | None = None  # the odometer corroborates the Wialon track (within 15%); None: too little movement to say
    explanation: str | None = None  # one Russian sentence generated from the structured cause (no external service)


class GpsHealth(BaseModel):
    """How reliable the GTK tracker of a locomotive is over the window (active days only)."""

    health_class: str  # ok | intermittent | dead | frozen | no_gtk
    window_days: int = 0
    active_days: int = 0  # days with >= 5 km in either tracker
    ok_days: int = 0
    partial_days: int = 0
    none_days: int = 0
    last_gtk_fix_age_h: float | None = None
    km_lost_m: int = 0  # Wialon km on the days GTK missed (the part of the distance GTK did not record)
    ok_share: float | None = None


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
    # --- analytics (P1) ---
    health: GpsHealth | None = None
    top_cause: str | None = None  # the most frequent non-ok cause in the window
    week_fused_m: int = 0
    week_confidence: float | None = None  # distance-weighted mean confidence over the window
    moving: bool = False  # either tracker reports speed > 3 km/h on a fresh fix
    section_name_short: str | None = None
    model_id: UUID | None = None
    explanation: str | None = None  # about the position verdict, in Russian


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
    cause_counts: dict[str, int] = Field(default_factory=dict)  # over all asset-days in the window
    health_counts: dict[str, int] = Field(default_factory=dict)
    week_fused_m: int = 0
    km_lost_m: int = 0  # Wialon km on the days GTK missed


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
    facets: dict[str, dict[str, int]] = Field(default_factory=dict)  # filter name -> value -> count under the OTHER active filters
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


# ---- GTK tracker health ranking ---------------------------------------------------------------------------
class GpsHealthRow(BaseModel):
    asset_id: UUID
    inv_number: str
    name: str
    asset_type_name: str | None = None
    model_name: str | None = None
    section_id: UUID | None = None
    section_name: str | None = None
    gtk_linked: bool = False
    gtk_id: int | None = None
    health: GpsHealth
    last_gtk_fix_at: datetime | None = None
    anomaly: str | None = None  # frozen | silent | None (a flag, never a correction)
    explanation: str | None = None


class GpsHealthPage(BaseModel):
    items: list[GpsHealthRow]
    total: int
    limit: int
    offset: int
    counts: dict[str, int] = Field(default_factory=dict)  # health_class -> locomotives


# ---- wagons (derived from the train their locomotive pulls) -----------------------------------------------
class WagonSegment(BaseModel):
    train_gtk_id: int
    train_number: str | None = None
    loco_asset_id: UUID | None = None  # hidden (None) from a master of another section
    loco_inv_number: str | None = None
    period_from: datetime
    period_to: datetime
    open: bool = False  # the membership is still running
    km_odometer: float | None = None  # A: Wialon odometer between the two instants (interpolated)
    km_wialon: float | None = None  # B: Wialon stored track
    km_gtk: float | None = None  # C: GTK stored track
    km_fused: float | None = None  # D: fused track
    selected_km: float | None = None
    basis: str  # fused_track | track | odometer | conflict | single_source | held
    confidence: str  # high | medium | low | none
    coverage: float | None = None
    flags: list[str] = Field(default_factory=list)


class GpsWagonRow(BaseModel):
    asset_id: UUID | None = None  # None: a GTK carriage that is not linked to a fixed asset
    carriage_gtk_id: int
    inv_number: str | None = None
    name: str
    asset_type: str | None = None
    asset_type_name: str | None = None
    section_id: UUID | None = None
    section_name: str | None = None
    in_train: bool = False
    train_gtk_id: int | None = None
    train_number: str | None = None
    since: datetime | None = None  # start of the current membership
    loco_asset_id: UUID | None = None
    loco_inv_number: str | None = None
    loco_name: str | None = None
    position: GpsFix | None = None  # the locomotive's best fix (the wagon has none of its own)
    position_source: str | None = None  # wialon | gtk_gps
    position_verdict: str | None = None  # the locomotive's Wialon-vs-GTK verdict
    confidence: str = "none"  # high | medium | low | none
    flags: list[str] = Field(default_factory=list)  # two_trains | stale_membership | loco_silent | no_loco | no_history
    km_period: float = 0.0  # selected km over the window
    segments_n: int = 0
    basis_counts: dict[str, int] = Field(default_factory=dict)


class GpsWagonSummary(BaseModel):
    wagons: int = 0
    in_train: int = 0
    confidence_counts: dict[str, int] = Field(default_factory=dict)
    flag_counts: dict[str, int] = Field(default_factory=dict)
    km_period: float = 0.0
    history_from: datetime | None = None  # the GTK membership history starts here: nothing earlier can be attributed


class GpsWagonPage(BaseModel):
    items: list[GpsWagonRow]
    total: int
    limit: int
    offset: int
    summary: GpsWagonSummary
    days: int


class GpsWagonDetail(BaseModel):
    row: GpsWagonRow
    segments: list[WagonSegment]
    explanation: str | None = None
