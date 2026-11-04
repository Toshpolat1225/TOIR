"""Compatibility exports for the shared source-neutral name helpers."""

from app.services.asset_matching import (
    classify_asset_type,
    extract_asset_numbers,
    extract_asset_series,
)

__all__ = [
    "classify_asset_type",
    "extract_asset_numbers",
    "extract_asset_series",
]
