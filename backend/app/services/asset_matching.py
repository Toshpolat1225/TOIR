"""Source-neutral normalization and candidate matching for asset links."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Iterable

from app.integrations.base import SourceObject
from app.models.gtk import GtkCarriage, GtkLocomotive
from app.repositories import assets as assets_repository
from app.repositories import gtk as gtk_repository
from app.repositories import wialon_units as wialon_repository

_LOCOMOTIVE_PREFIX = re.compile(
    r"^(?:(?:м|m)(?:п|p)(?:э|e)|(?:п|p)(?:э|e))-",
    re.IGNORECASE,
)
_DIESEL_PREFIX = re.compile(r"^[тt][эe][мm]", re.IGNORECASE)
_TWO_TE_PREFIX = re.compile(r"^2[тt][эe]\d+", re.IGNORECASE)
_LOCOMOTIVE_SERIES = re.compile(
    r"^(?:(?:м|m)(?:п|p)(?:э|e)|(?:п|p)(?:э|e))"
    r"\s*-\s*\d+[a-zа-яё]?",
    re.IGNORECASE,
)
_DIESEL_SERIES = re.compile(
    r"^[тt][эe][мm]\s*\d+[a-zа-яё]*(?:\s+[a-zа-яё]+)?",
    re.IGNORECASE,
)
_ASSET_NUMBERS = re.compile(r"(?<!\d)\d{2,4}(?!\d)")
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_SERIES_TOKEN = re.compile(
    r"(?:мпэ|mpe|пэ|pe|тэм|tem|2тэ|2te)\s*-?\s*\d+[a-zа-яё]*",
    re.IGNORECASE,
)
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
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = normalized.translate(_LATIN_TO_CYRILLIC)
    return "".join(character for character in normalized if character.isalnum())


def classify_asset_type(name: str | None) -> str | None:
    normalized = (name or "").strip().casefold()
    if _LOCOMOTIVE_PREFIX.match(normalized):
        return "locomotive"
    if _DIESEL_PREFIX.match(normalized) or _TWO_TE_PREFIX.match(normalized):
        return "diesel"
    return None


def extract_asset_series(name: str | None) -> str | None:
    value = (name or "").strip()
    two_te_match = _TWO_TE_PREFIX.match(value)
    if two_te_match is not None:
        return two_te_match.group(0).translate(
            str.maketrans(
                {"t": "Т", "T": "Т", "e": "Э", "E": "Э", "т": "Т", "э": "Э"}
            )
        )
    match = _LOCOMOTIVE_SERIES.match(value) or _DIESEL_SERIES.match(value)
    if match is None:
        return None
    return " ".join(match.group(0).split())


def extract_asset_numbers(name: str | None) -> frozenset[int]:
    return frozenset(int(value) for value in _ASSET_NUMBERS.findall(name or ""))


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


def _allowed_asset_types(source_object: SourceObject) -> frozenset[str]:
    object_type = (source_object.type or "").casefold()
    if object_type in {"locomotive", "diesel"}:
        return frozenset({"locomotive", "diesel"})
    if object_type in {"carriage", "wagon"}:
        return frozenset({"wagon"})
    return frozenset({"locomotive", "diesel", "wagon"})


def _source_series(source_object: SourceObject) -> str:
    model = source_object.model or source_object.serial
    if model:
        return normalize_token(model)
    return normalize_token(
        extract_series(source_object.name) or extract_asset_series(source_object.name)
    )


def _source_numbers(source_object: SourceObject) -> frozenset[int]:
    numbers: set[int] = set()
    for value in (source_object.number, source_object.serial):
        if value:
            numbers.update(extract_vehicle_numbers(value))
    if source_object.name:
        numbers.update(
            extract_vehicle_numbers(
                source_object.name, series=extract_series(source_object.name)
            )
        )
    return frozenset(numbers)


def match_source_objects(
    source_objects: Iterable[SourceObject],
    assets: Iterable[Any],
) -> list[dict[str, Any]]:
    source_rows = list(source_objects)
    asset_rows = list(assets)
    edges: dict[str, list[tuple[Any, tuple[str, ...]]]] = defaultdict(list)

    for source_object in source_rows:
        allowed_types = _allowed_asset_types(source_object)
        source_type = (source_object.type or "").casefold()
        source_is_carriage = source_type in {"carriage", "wagon"}
        source_series = _source_series(source_object)
        source_numbers = _source_numbers(source_object)
        source_inventory = _real_inventory(source_object.inventory)
        source_registration = normalize_token(source_object.number)

        for asset in asset_rows:
            if asset.asset_type not in allowed_types:
                continue
            signals: list[str] = []
            if source_is_carriage:
                inventory = normalize_token(asset.inv_number)
                asset_name = normalize_token(asset.name)
                asset_numbers = extract_vehicle_numbers(asset.name)
                if source_registration and (
                    source_registration == inventory
                    or source_registration == asset_name
                    or (
                        source_registration.isdigit()
                        and int(source_registration) in asset_numbers
                    )
                ):
                    signals.append("reg_number")
            elif source_series and source_numbers:
                if source_object.source == "wialon":
                    asset_series_value = asset.series or extract_asset_series(asset.name)
                else:
                    asset_series_value = extract_series(asset.name) or extract_asset_series(
                        asset.series
                    )
                asset_series = normalize_token(asset_series_value)
                asset_numbers = extract_vehicle_numbers(
                    asset.name, series=extract_series(asset.name)
                )
                if source_series == asset_series and source_numbers & asset_numbers:
                    signals.extend(("series", "vehicle_number"))

            asset_inventory = _real_inventory(asset.inv_number)
            if source_inventory and source_inventory == asset_inventory:
                signals.append("inventory_number")
            if source_is_carriage and source_inventory and source_inventory == asset_inventory:
                if "inventory_number" not in signals:
                    signals.append("inventory_number")
            if signals:
                edges[str(source_object.external_id)].append(
                    (asset, tuple(signals))
                )

    asset_degrees: dict[Any, int] = defaultdict(int)
    for candidates in edges.values():
        for asset, _ in candidates:
            asset_degrees[asset.id] += 1

    report: list[dict[str, Any]] = []
    for source_object in source_rows:
        candidates = edges.get(str(source_object.external_id), [])
        unique = (
            len(candidates) == 1
            and asset_degrees[candidates[0][0].id] == 1
        )
        candidates.sort(
            key=lambda item: (
                -len(item[1]),
                str(item[0].name).casefold(),
                str(item[0].id),
            )
        )
        candidate_data = [
            {
                "asset_id": asset.id,
                "name": asset.name,
                "inv_number": asset.inv_number,
                "asset_type": asset.asset_type,
                "signals": list(signals),
            }
            for asset, signals in candidates
        ]
        best = candidate_data[0] if candidate_data else None
        report.append(
            {
                "source": source_object.source,
                "external_id": source_object.external_id,
                "name": source_object.name,
                "number": source_object.number,
                "serial": source_object.serial,
                "inventory": source_object.inventory,
                "model": source_object.model,
                "type": source_object.type,
                "level": "high" if unique else "ambiguous" if candidates else "none",
                "candidate_count": len(candidates),
                "suggestion": best,
                "candidates": candidate_data,
                "signals": best["signals"] if best else [],
            }
        )
    return report


def _to_source_object(source: str, record: Any) -> SourceObject:
    if source == "gtk":
        if isinstance(record, GtkLocomotive):
            from app.services.wialon_asset_import import classify_asset_type

            return SourceObject(
                source="gtk",
                external_id=str(record.gtk_id),
                name=record.name,
                number=record.garage_number,
                inventory=record.inventory_number,
                model=record.model_name,
                type="locomotive",
            )
        return SourceObject(
            source="gtk",
            external_id=str(record.gtk_id),
            name=record.name,
            number=record.reg_number,
            inventory=record.inventory_number,
            model=record.model_name,
            type="carriage",
        )
    return SourceObject(
        source="wialon",
        external_id=record.unit_id,
        name=record.name,
        model=extract_asset_series(record.name),
        type=classify_asset_type(record.name),
    )


async def list_unmatched(
    db: Any,
    *,
    source: str,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    if source not in {"gtk", "wialon"}:
        raise ValueError("Unsupported asset source")
    records = (
        await gtk_repository.list_unlinked_source_objects(db)
        if source == "gtk"
        else await wialon_repository.list_unlinked_source_objects(db)
    )
    source_objects = [_to_source_object(source, record) for record in records]
    assets = await assets_repository.list_assets_unlinked_from_source(db, source)
    report = match_source_objects(source_objects, assets)
    total = len(report)
    return report[offset : offset + limit], total
