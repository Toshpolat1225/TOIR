from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class FixedAssetsPassportImportRequest(BaseModel):
    json_text: str = Field(min_length=2, max_length=10_000_000)


class FixedAssetPassportImportPreviewRow(BaseModel):
    row_number: int
    status: Literal["ready", "duplicate", "invalid"]
    asset_type: str | None
    name: str | None
    model: str | None
    serial_number: str | None
    inv_number: str | None
    commissioned_at: date | None
    decommissioned_at: date | None
    year_built: int | None
    section: str | None
    wialon_id: str | None
    gtk_id: str | None
    issue: str | None


class FixedAssetsPassportImportPreview(BaseModel):
    source_hash: str
    total: int
    current_assets: int
    ready: int
    blocked: int
    duplicate_inventory_groups: int
    duplicate_number_groups: int
    type_counts: dict[str, int]
    section_counts: dict[str, int]
    items: list[FixedAssetPassportImportPreviewRow]


class FixedAssetsPassportImportApplyRequest(FixedAssetsPassportImportRequest):
    source_hash: str = Field(min_length=64, max_length=64)


class FixedAssetsPassportImportApplyRead(BaseModel):
    deleted_count: int
    imported_count: int
