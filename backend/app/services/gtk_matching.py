"""GTK compatibility helpers backed by source-neutral asset matching."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from app.integrations.base import SourceObject
from app.services.asset_matching import (
    _PARENTHETICAL,
    _real_inventory,
    extract_asset_numbers,
    extract_asset_series,
    extract_series,
    extract_vehicle_numbers,
    match_source_objects,
    normalize_token,
)


def preferred_carriage_ids(
    carriages: list[Any], in_train_ids: set[int]
) -> set[int]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for carriage in carriages:
        registration = (getattr(carriage, "reg_number", None) or "").strip().casefold()
        if registration:
            groups[registration].append(carriage)
    duplicates: set[int] = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda carriage: (
                int(carriage.gtk_id) not in in_train_ids,
                int(carriage.gtk_id),
            ),
        )
        duplicates.update(int(carriage.gtk_id) for carriage in ordered[1:])
    return duplicates


def _source_object(kind: str, row: Any) -> SourceObject:
    if kind == "locomotive":
        return SourceObject(
            source="gtk",
            external_id=str(row.gtk_id),
            name=getattr(row, "name", None),
            number=getattr(row, "garage_number", None),
            inventory=getattr(row, "inventory_number", None),
            model=getattr(row, "model_name", None),
            type="locomotive",
        )
    return SourceObject(
        source="gtk",
        external_id=str(row.gtk_id),
        name=getattr(row, "name", None),
        number=getattr(row, "reg_number", None),
        inventory=getattr(row, "inventory_number", None),
        model=getattr(row, "model_name", None),
        type="carriage",
    )


def match_report(
    kind: str,
    gtk_rows: list[Any],
    assets: list[Any],
    *,
    in_train_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    if kind not in {"locomotive", "carriage"}:
        raise ValueError("Unsupported GTK match kind")
    duplicate_ids = (
        preferred_carriage_ids(gtk_rows, in_train_ids or set())
        if kind == "carriage"
        else set()
    )
    matchable_rows = [
        row for row in gtk_rows if int(row.gtk_id) not in duplicate_ids
    ]
    generic_rows = match_source_objects(
        (_source_object(kind, row) for row in matchable_rows),
        assets,
    )
    by_id = {int(row["external_id"]): row for row in generic_rows}
    report: list[dict[str, Any]] = []
    for gtk in gtk_rows:
        gtk_id = int(gtk.gtk_id)
        if gtk_id in duplicate_ids:
            report.append(
                {
                    "gtk_id": gtk_id,
                    "kind": kind,
                    "level": "duplicate",
                    "candidate_count": 0,
                    "suggestion": None,
                    "signals": [],
                    "duplicate": True,
                }
            )
            continue
        match = by_id[gtk_id]
        best = match["suggestion"]
        suggestion = (
            {
                "id": best["asset_id"],
                "name": best["name"],
                "inv_number": best["inv_number"],
                "asset_type": best["asset_type"],
                "signals": best["signals"],
            }
            if best
            else None
        )
        report.append(
            {
                "gtk_id": gtk_id,
                "kind": kind,
                "level": match["level"],
                "candidate_count": match["candidate_count"],
                "suggestion": suggestion,
                "signals": match["signals"],
                "duplicate": False,
            }
        )
    return report
