from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, Mapping
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_models import AssetModel
from app.repositories import asset_models as repository
from app.services.gtk_matching import (
    _PARENTHETICAL,
    extract_series,
    extract_vehicle_numbers,
    normalize_token,
)

_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{2,4}(?!\d)")


def extract_passport_number(value: str | None, *, series: str | None = None) -> str | None:
    without_parentheses = _PARENTHETICAL.sub(" ", value or "")
    candidates = extract_vehicle_numbers(value, series=series)
    for match in _NUMBER_PATTERN.finditer(without_parentheses):
        if int(match.group()) in candidates:
            return match.group()
    return None


def derive_model_name(value: str | None, *, series: str | None = None) -> str | None:
    supplied = (series or "").strip()
    if supplied:
        return supplied
    parsed = extract_series(value)
    if parsed:
        return parsed
    without_parentheses = _PARENTHETICAL.sub(" ", value or "")
    number = extract_passport_number(value)
    if number is None:
        return None
    match = _NUMBER_PATTERN.search(without_parentheses)
    if match is None:
        return None
    prefix = without_parentheses[: match.start()].strip(" \t-_/")
    return " ".join(prefix.split()) or None


def plan_passport_backfill(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    models: dict[str, dict[str, Any]] = {}
    assets: list[dict[str, Any]] = []
    for row in rows:
        name = row["name"] or ""
        model_name = derive_model_name(name, series=row["series"])
        normalized_model = normalize_token(model_name) if model_name else ""
        number = extract_passport_number(name, series=model_name)
        if normalized_model:
            models.setdefault(
                normalized_model,
                {
                    "name": model_name,
                    "name_normalized": normalized_model,
                    "asset_type": row["asset_type"],
                    "series": row["series"] or model_name,
                },
            )
        assets.append(
            {
                "id": row["id"],
                "model_normalized": normalized_model or None,
                "serial_number": number,
                "number": number,
                "number_normalized": normalize_token(number) or None,
                "commissioned_at": row["comm_date"],
                "inv_number_is_provisional": (
                    (row["inv_number"] or "").upper().startswith("WIALON-")
                ),
            }
        )
    return list(models.values()), assets


def validate_passport_values(
    *,
    year_built: int | None,
    commissioned_at: date | None,
    decommissioned_at: date | None,
    current_year: int | None = None,
) -> None:
    current_year = current_year or date.today().year
    if year_built is not None and not 1900 <= year_built <= current_year:
        raise ValueError(f"year_built must be between 1900 and {current_year}")
    if (
        year_built is not None
        and commissioned_at is not None
        and commissioned_at < date(year_built, 1, 1)
    ):
        raise ValueError("commissioned_at cannot be before the year built")
    if (
        commissioned_at is not None
        and decommissioned_at is not None
        and decommissioned_at < commissioned_at
    ):
        raise ValueError("decommissioned_at cannot be before commissioned_at")


async def resolve_model(
    db: AsyncSession,
    *,
    asset_type: str,
    model_id: UUID | None,
    model_name: str | None,
    name: str | None,
) -> AssetModel:
    model: AssetModel | None = None
    if model_id is not None:
        model = await repository.get_model(db, model_id)
        if model is None:
            raise HTTPException(status_code=422, detail="Asset model was not found")
    else:
        candidate = derive_model_name(name, series=model_name)
        normalized = normalize_token(candidate) if candidate else ""
        if not candidate or not normalized:
            raise HTTPException(
                status_code=422, detail="Asset model is required for a new asset"
            )
        model = await repository.add_if_missing(
            db,
            name=candidate,
            name_normalized=normalized,
            asset_type=asset_type,
            series=model_name or candidate,
        )
    if model.asset_type != asset_type:
        raise HTTPException(
            status_code=422, detail="Asset model type does not match asset type"
        )
    return model


async def list_models(
    db: AsyncSession,
    *,
    asset_type: str | None,
    q: str | None,
    limit: int,
    offset: int,
):
    return await repository.list_models(
        db, asset_type=asset_type, q=q, limit=limit, offset=offset
    )


async def prepare_new_asset(
    db: AsyncSession,
    *,
    asset_type: str,
    name: str | None,
    model_id: UUID | None,
    model_name: str | None,
    number: str | None,
) -> dict[str, Any]:
    model = await resolve_model(
        db,
        asset_type=asset_type,
        model_id=model_id,
        model_name=model_name,
        name=name,
    )
    normalized_number = (number or "").strip() or extract_passport_number(
        name, series=model.series or model.name
    )
    if not normalized_number:
        raise HTTPException(
            status_code=422, detail="Asset number is required for a new asset"
        )
    normalized_number = normalized_number.strip()
    return {
        "model_id": model.id,
        "serial_number": normalized_number,
    }


def build_passport_report(
    assets: Iterable[Any],
    sections: Iterable[tuple[UUID, str]],
    *,
    current_year: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    current_year = current_year or date.today().year
    sections_by_name: dict[str, list[tuple[UUID, str]]] = {}
    for section_id, section_name in sections:
        sections_by_name.setdefault(section_name, []).append((section_id, section_name))

    depot_matches: list[dict[str, Any]] = []
    depot_unmatched: list[dict[str, Any]] = []
    invalid_values: list[dict[str, Any]] = []
    duplicate_groups: dict[tuple[str, UUID | None, str], list[Any]] = {}
    asset_rows = list(assets)

    for asset in asset_rows:
        if asset.depot:
            candidates = sections_by_name.get(asset.depot, [])
            depot_row = {
                "asset_id": asset.id,
                "inv_number": asset.inv_number,
                "depot": asset.depot,
                "candidate_sections": [
                    {"id": section_id, "name": section_name}
                    for section_id, section_name in candidates
                ],
                "org_unit_id": asset.org_unit_id,
            }
            if len(candidates) == 1:
                depot_matches.append(depot_row)
            else:
                depot_row["status"] = "ambiguous" if candidates else "no_match"
                depot_unmatched.append(depot_row)

        issues = []
        if asset.year_built is not None and not 1900 <= asset.year_built <= current_year:
            issues.append("year_built_out_of_range")
        if (
            asset.year_built is not None
            and asset.commissioned_at is not None
            and 1 <= asset.year_built <= 9999
            and asset.commissioned_at < date(asset.year_built, 1, 1)
        ):
            issues.append("commissioned_before_year_built")
        if (
            asset.commissioned_at is not None
            and asset.decommissioned_at is not None
            and asset.decommissioned_at < asset.commissioned_at
        ):
            issues.append("decommissioned_before_commissioned")
        if issues:
            invalid_values.append(
                {"asset_id": asset.id, "inv_number": asset.inv_number, "issues": issues}
            )

        serial_number = getattr(asset, "serial_number", None) or getattr(
            asset, "number", None
        )
        normalized_serial = normalize_token(serial_number) or getattr(
            asset, "number_normalized", None
        )
        if asset.model_id is not None and normalized_serial:
            duplicate_groups.setdefault(
                (asset.asset_type, asset.model_id, normalized_serial), []
            ).append(asset)

    duplicate_numbers = [
        {
            "asset_type": key[0],
            "model_id": key[1],
            "number_normalized": key[2],
            "assets": [
                {"asset_id": asset.id, "inv_number": asset.inv_number}
                for asset in group
            ],
        }
        for key, group in duplicate_groups.items()
        if len(group) > 1
    ]
    return {
        "depot_matches": depot_matches,
        "depot_unmatched": depot_unmatched,
        "duplicate_numbers": duplicate_numbers,
        "invalid_values": invalid_values,
    }
