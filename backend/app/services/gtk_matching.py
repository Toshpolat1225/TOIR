"""Pure helpers for operator-reviewed GTK-to-fixed-asset suggestions."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any
from uuid import UUID

from app.services.wialon_asset_import import extract_asset_numbers, extract_asset_series

_SERIES_TOKEN = re.compile(
    r"(?:мпэ|mpe|пэ|pe|тэм|tem|2тэ|2te)\s*-?\s*\d+[a-zа-яё]*",
    re.IGNORECASE,
)
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_LATIN_TO_CYRILLIC = str.maketrans(
    {
        "a": "а",
        "b": "в",
        "c": "с",
        "d": "д",
        "e": "э",
        "h": "н",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "п",
        "t": "т",
        "x": "х",
        "y": "у",
    }
)


def normalize_token(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.translate(_LATIN_TO_CYRILLIC)
    return "".join(character for character in value if character.isalnum())


def extract_series(value: str | None) -> str | None:
    text = unicodedata.normalize("NFKC", value or "")
    text = re.sub(
        r"^\s*(?:тяговый\s+агрегат|тепловзо)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    match = _SERIES_TOKEN.search(text)
    if match is None:
        return extract_asset_series(text)
    candidate = match.group(0)
    if re.match(r"^(?:мпэ|mpe|пэ|pe)\s*\d", candidate, re.IGNORECASE):
        candidate = re.sub(
            r"^((?:мпэ|mpe|пэ|pe))\s*(\d)",
            r"\1-\2",
            candidate,
            flags=re.IGNORECASE,
        )
    return extract_asset_series(candidate) or candidate


def extract_vehicle_numbers(
    value: str | None, *, series: str | None = None
) -> frozenset[int]:
    text = _PARENTHETICAL.sub(" ", value or "")
    numbers = extract_asset_numbers(text)
    if series:
        numbers -= extract_asset_numbers(series)
    return numbers


def _real_inventory(value: str | None) -> str | None:
    if not value or value.strip().casefold().startswith("wialon-"):
        return None
    return normalize_token(value)


def _asset_type_matches(kind: str, asset_type: str) -> bool:
    return asset_type in {"locomotive", "diesel"} if kind == "locomotive" else asset_type == "wagon"


def _candidate_edges(
    kind: str, gtk_rows: list[Any], assets: list[Any]
) -> dict[int, list[tuple[Any, tuple[str, ...]]]]:
    edges: dict[int, list[tuple[Any, tuple[str, ...]]]] = defaultdict(list)
    for gtk in gtk_rows:
        gtk_id = int(gtk.gtk_id)
        if kind == "locomotive":
            gtk_series = normalize_token(
                getattr(gtk, "model_name", None) or extract_series(getattr(gtk, "name", None))
            )
            garage_number = extract_vehicle_numbers(
                getattr(gtk, "garage_number", None)
            )
            gtk_inventory = _real_inventory(getattr(gtk, "inventory_number", None))
        else:
            gtk_series = ""
            garage_number = frozenset()
            gtk_inventory = None
            reg_number = normalize_token(getattr(gtk, "reg_number", None))

        for asset in assets:
            if not _asset_type_matches(kind, asset.asset_type):
                continue
            signals: list[str] = []
            if kind == "locomotive":
                asset_series = normalize_token(
                    extract_series(asset.name) or extract_asset_series(asset.series)
                )
                asset_numbers = extract_vehicle_numbers(
                    asset.name, series=extract_series(asset.name)
                )
                if gtk_series and gtk_series == asset_series and garage_number & asset_numbers:
                    signals.extend(("series", "vehicle_number"))
                asset_inventory = _real_inventory(asset.inv_number)
                if gtk_inventory and gtk_inventory == asset_inventory:
                    signals.append("inventory_number")
            else:
                asset_inventory = normalize_token(asset.inv_number)
                asset_name = normalize_token(asset.name)
                asset_numbers = extract_vehicle_numbers(asset.name)
                if reg_number and (
                    reg_number == asset_inventory
                    or reg_number == asset_name
                    or reg_number.isdigit()
                    and int(reg_number) in asset_numbers
                ):
                    signals.append("reg_number")
                if _real_inventory(getattr(gtk, "inventory_number", None)) == _real_inventory(
                    asset.inv_number
                ) and _real_inventory(asset.inv_number):
                    signals.append("inventory_number")
            if signals:
                edges[gtk_id].append((asset, tuple(signals)))
    return edges


def match_report(
    kind: str,
    gtk_rows: list[Any],
    assets: list[Any],
    *,
    in_train_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    if kind not in {"locomotive", "carriage"}:
        raise ValueError("Unsupported GTK match kind")
    edges = _candidate_edges(kind, gtk_rows, assets)
    duplicate_ids = (
        preferred_carriage_ids(gtk_rows, in_train_ids or set())
        if kind == "carriage"
        else set()
    )
    for duplicate_id in duplicate_ids:
        edges.pop(duplicate_id, None)
    asset_degrees: dict[UUID, int] = defaultdict(int)
    for candidates in edges.values():
        for asset, _ in candidates:
            asset_degrees[asset.id] += 1

    report = []
    for gtk in gtk_rows:
        gtk_id = int(gtk.gtk_id)
        candidates = edges.get(gtk_id, [])
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
        unique = (
            len(candidates) == 1
            and asset_degrees[candidates[0][0].id] == 1
        )
        suggestion = None
        if candidates:
            candidates.sort(
                key=lambda item: (
                    -len(item[1]),
                    str(item[0].name).casefold(),
                    str(item[0].id),
                )
            )
            asset, signals = candidates[0]
            suggestion = {
                "id": asset.id,
                "name": asset.name,
                "inv_number": asset.inv_number,
                "asset_type": asset.asset_type,
                "signals": list(signals),
            }
        report.append(
            {
                "gtk_id": gtk_id,
                "kind": kind,
                "level": "high" if unique else "ambiguous" if candidates else "none",
                "candidate_count": len(candidates),
                "suggestion": suggestion,
                "signals": list(suggestion["signals"]) if suggestion else [],
                "duplicate": False,
            }
        )
    return report


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
