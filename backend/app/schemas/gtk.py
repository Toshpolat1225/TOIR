from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assets import AssetType


class GtkLinkedAssetRead(BaseModel):
    id: UUID
    name: str
    inv_number: str
    asset_type: AssetType


class GtkSuggestionRead(BaseModel):
    level: Literal["high", "ambiguous", "none"]
    candidate_count: int
    asset: GtkLinkedAssetRead | None
    signals: list[str]


class GtkSyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    status: Literal["ok", "error", "parse_error", "suspicious", "login_failed"]
    counts: dict[str, int | float] | None
    quality: dict | None
    error: str | None


class GtkStatusRead(BaseModel):
    enabled: bool
    interval_minutes: int
    auto_sync_stopped: bool
    last_run: GtkSyncRunRead | None


class GtkLocomotiveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gtk_id: int
    name: str | None
    garage_number: str | None
    inventory_number: str | None
    model_name: str | None
    vehicle_type_name: str | None
    division_name: str | None
    start_expl_date: datetime | None
    end_expl_date: datetime | None
    is_active: bool
    first_seen_at: datetime
    last_synced_at: datetime
    in_train: bool = False
    linked_asset: GtkLinkedAssetRead | None = None
    suggestion: GtkSuggestionRead = Field(
        default_factory=lambda: GtkSuggestionRead(
            level="none", candidate_count=0, asset=None, signals=[]
        )
    )


class GtkCarriageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gtk_id: int
    name: str | None
    reg_number: str | None
    inventory_number: str | None
    model_name: str | None
    start_expl_date: datetime | None
    end_expl_date: datetime | None
    is_active: bool
    is_loaded: bool | None
    is_not_serviceable: bool | None
    lat: Decimal | None
    lon: Decimal | None
    state_duration_s: int | None
    first_seen_at: datetime
    last_synced_at: datetime
    in_train: bool = False
    duplicate: bool = False
    linked_asset: GtkLinkedAssetRead | None = None
    suggestion: GtkSuggestionRead = Field(
        default_factory=lambda: GtkSuggestionRead(
            level="none", candidate_count=0, asset=None, signals=[]
        )
    )


class GtkMatchReportItem(BaseModel):
    gtk_id: int
    kind: Literal["locomotive", "carriage"]
    level: Literal["high", "ambiguous", "none", "duplicate"]
    candidate_count: int
    suggestion: GtkLinkedAssetRead | None
    signals: list[str]
    linked_asset: GtkLinkedAssetRead | None = None
    duplicate: bool = False


class GtkMatchReport(BaseModel):
    kind: Literal["locomotive", "carriage"]
    totals: dict[str, int]
    items: list[GtkMatchReportItem]


class GtkLinkItem(BaseModel):
    asset_id: UUID
    gtk_id: int
    kind: Literal["locomotive", "carriage"]
    expected_inventory_number: str | None = Field(default=None, max_length=100)


class GtkLinkBatchRequest(BaseModel):
    links: list[GtkLinkItem] = Field(min_length=1, max_length=500)


class GtkLinkBatchResponse(BaseModel):
    updated: int


class GtkCarriageAssetPreview(BaseModel):
    name: str
    asset_type: Literal["wagon"] = "wagon"
    series: str | None
    inv_number: str
    mileage: Decimal = Decimal("0")
    gtk_id: str


class GtkCreateAssetItemResult(BaseModel):
    gtk_id: int
    status: Literal["created", "would_create", "skipped"]
    reason: str | None = None
    asset: GtkCarriageAssetPreview | None = None


class GtkCreateAssetsResponse(BaseModel):
    dry_run: bool
    created: int
    would_create: int
    skipped: int
    items: list[GtkCreateAssetItemResult]


class GtkCreateAssetRequest(BaseModel):
    dry_run: bool = True


class GtkTrainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gtk_id: int
    number: str | None
    title: str | None
    begin_time: datetime | None
    end_time: datetime | None
    is_open: bool
    last_synced_at: datetime


class GtkWagonMileageLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wagon_asset_id: UUID
    loco_asset_id: UUID
    train_gtk_id: int
    period_from: datetime
    period_to: datetime
    km: Decimal
    created_at: datetime


class GtkWagonMileageList(BaseModel):
    items: list[GtkWagonMileageLogRead]
    total: int
    limit: int


class GtkTrainLocomotiveMemberRead(GtkLocomotiveRead):
    is_main: bool
    ord: int


class GtkTrainCarriageMemberRead(GtkCarriageRead):
    ord: int


class GtkTrainDetail(GtkTrainRead):
    locomotives: list[GtkTrainLocomotiveMemberRead]
    carriages: list[GtkTrainCarriageMemberRead]


class GtkFixedAssetSourceDetail(BaseModel):
    asset_id: UUID
    gtk_id: int
    kind: Literal["locomotive", "carriage"]
    gtk_object: GtkLocomotiveRead | GtkCarriageRead
    current_trains: list[GtkTrainDetail]
    recent_mileage_logs: list[GtkWagonMileageLogRead]
