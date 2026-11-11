"""GTK compatibility helpers backed by source-neutral asset matching."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from app.services.asset_matching import (
    _PARENTHETICAL,
    extract_series,
    extract_vehicle_numbers,
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


def match_report(
    kind: str,
    gtk_rows: list[Any],
    assets: list[Any],
    *,
    linked_asset_ids: frozenset[UUID] | set[UUID] = frozenset(),
    linked_gtk_ids: frozenset[int] | set[int] = frozenset(),
) -> list[dict[str, Any]]:
    if kind not in {"locomotive", "carriage"}:
        raise ValueError("Unsupported GTK match kind")
    allowed_types = (
        {"locomotive", "diesel"} if kind == "locomotive" else {"wagon"}
    )
    assets_by_inventory: dict[str, list[Any]] = defaultdict(list)
    for asset in assets:
        inventory = getattr(asset, "inv_number", None)
        if (
            getattr(asset, "asset_type", None) in allowed_types
            and isinstance(inventory, str)
            and inventory.strip()
        ):
            assets_by_inventory[inventory].append(asset)

    candidates_by_gtk_id: dict[int, list[Any]] = {}
    source_counts: dict[str, int] = defaultdict(int)
    for row in gtk_rows:
        gtk_id = int(row.gtk_id)
        inventory = getattr(row, "inventory_number", None)
        if (
            gtk_id in linked_gtk_ids
            or not isinstance(inventory, str)
            or not inventory.strip()
        ):
            candidates_by_gtk_id[gtk_id] = []
            continue
        candidates = assets_by_inventory.get(inventory, [])
        candidates_by_gtk_id[gtk_id] = candidates
        if candidates:
            source_counts[inventory] += 1

    report: list[dict[str, Any]] = []
    for gtk in gtk_rows:
        gtk_id = int(gtk.gtk_id)
        inventory = getattr(gtk, "inventory_number", None)
        candidates = candidates_by_gtk_id[gtk_id]
        ambiguous = len(candidates) > 1 or (
            isinstance(inventory, str)
            and source_counts[inventory] > 1
            and bool(candidates)
        )
        is_unique_source = (
            isinstance(inventory, str)
            and source_counts[inventory] == 1
        )
        selected = (
            candidates[0]
            if len(candidates) == 1
            and is_unique_source
            and candidates[0].id not in linked_asset_ids
            else None
        )
        level = (
            "high"
            if selected is not None
            else "ambiguous"
            if ambiguous
            else "none"
        )
        suggestion = (
            {
                "id": selected.id,
                "name": selected.name,
                "inv_number": selected.inv_number,
                "asset_type": selected.asset_type,
                "signals": ["inventory_number"],
            }
            if selected is not None
            else None
        )
        report.append(
            {
                "gtk_id": gtk_id,
                "kind": kind,
                "level": level,
                "candidate_count": len(candidates),
                "suggestion": suggestion,
                "signals": ["inventory_number"] if candidates else [],
                "duplicate": False,
            }
        )
    return report
