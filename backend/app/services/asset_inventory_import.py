import csv
import io
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_field_changes import AssetFieldChange
from app.repositories import assets as repository
from app.schemas.assets import (
    FixedAssetInventoryImportApply,
    FixedAssetInventoryImportPreview,
    FixedAssetInventoryImportPreviewItem,
    FixedAssetInventoryImportRequest,
)
from app.services import asset_field_changes
from app.services.asset_matching import normalize_token


def _input_rows(payload: FixedAssetInventoryImportRequest):
    if payload.rows is not None:
        return [
            (
                index,
                row.asset_id.strip() if row.asset_id else None,
                row.name.strip() if row.name else None,
                row.inv_number.strip() if row.inv_number else None,
                row.accounting_inv_number.strip()
                if row.accounting_inv_number
                else None,
            )
            for index, row in enumerate(payload.rows, start=1)
        ]

    text = (payload.csv_text or "").lstrip("\ufeff")
    try:
        reader = csv.reader(io.StringIO(text, newline=""))
        raw_headers = next(reader, None)
        headers = [header.strip() for header in (raw_headers or [])]
        header_set = set(headers)
        if len(header_set) != len(headers):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CSV contains duplicate column names",
            )
        if not {"inv_number"} <= header_set or not (
            {"asset_id", "name"} & header_set
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CSV must include inv_number and asset_id or name columns",
            )
        rows = []
        for values in reader:
            if len(values) > len(headers):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="CSV row has more columns than the header",
                )
            row = {
                header: values[index] if index < len(values) else ""
                for index, header in enumerate(headers)
            }
            rows.append(
                (
                    reader.line_num,
                    (row.get("asset_id") or "").strip() or None,
                    (row.get("name") or "").strip() or None,
                    (row.get("inv_number") or "").strip() or None,
                    (row.get("accounting_inv_number") or "").strip() or None,
                )
            )
        return rows
    except csv.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV format is invalid",
        ) from exc


async def preview_inventory_import(
    db: AsyncSession, payload: FixedAssetInventoryImportRequest
) -> FixedAssetInventoryImportPreview:
    rows = _input_rows(payload)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Import must contain at least one data row",
        )

    asset_names = await repository.list_asset_names(db)
    asset_names_by_id = {asset_id: name for asset_id, name in asset_names}
    all_names: dict[str, list[UUID]] = {}
    for asset_id, name in asset_names:
        normalized = normalize_token(name)
        if normalized:
            all_names.setdefault(normalized, []).append(asset_id)

    resolved: list[dict] = []
    for row_number, raw_asset_id, name, inv_number, accounting_number in rows:
        if not any((raw_asset_id, name, inv_number, accounting_number)):
            resolved.append(
                {
                    "row_number": row_number,
                    "status": "empty",
                    "asset_id": None,
                    "asset_name": None,
                    "inv_number": inv_number,
                    "accounting_inv_number": accounting_number,
                    "message": "Строка пустая.",
                }
            )
            continue
        if not inv_number:
            resolved.append(
                {
                    "row_number": row_number,
                    "status": "empty",
                    "asset_id": None,
                    "asset_name": None,
                    "inv_number": inv_number,
                    "accounting_inv_number": accounting_number,
                    "message": "Не указан инвентарный номер.",
                }
            )
            continue

        candidates: list[UUID] = []
        if raw_asset_id:
            try:
                candidate_id = UUID(raw_asset_id)
            except ValueError:
                candidate_id = None
            if candidate_id is not None:
                candidates = [candidate_id] if candidate_id in asset_names_by_id else []
        elif name:
            candidates = all_names.get(normalize_token(name), [])

        if not candidates:
            resolved.append(
                {
                    "row_number": row_number,
                    "status": "not_found",
                    "asset_id": None,
                    "asset_name": None,
                    "inv_number": inv_number,
                    "accounting_inv_number": accounting_number,
                    "message": "Основное средство не найдено.",
                }
            )
        elif len(candidates) > 1:
            resolved.append(
                {
                    "row_number": row_number,
                    "status": "ambiguous",
                    "asset_id": None,
                    "asset_name": name,
                    "inv_number": inv_number,
                    "accounting_inv_number": accounting_number,
                    "message": "Найдено несколько основных средств с таким наименованием.",
                }
            )
        else:
            asset_id = candidates[0]
            asset_name = asset_names_by_id.get(asset_id)
            asset = await repository.get_asset(db, asset_id)
            if asset is None or asset_name is None:
                resolved.append(
                    {
                        "row_number": row_number,
                        "status": "not_found",
                        "asset_id": None,
                        "asset_name": None,
                        "inv_number": inv_number,
                        "accounting_inv_number": accounting_number,
                        "message": "Основное средство не найдено.",
                    }
                )
            else:
                resolved.append(
                    {
                        "row_number": row_number,
                        "status": "ok",
                        "asset_id": asset.id,
                        "asset_name": asset.name,
                        "inv_number": inv_number,
                        "accounting_inv_number": accounting_number,
                        "message": "Готово к импорту.",
                    }
                )

    eligible = [row for row in resolved if row["status"] == "ok"]
    inv_counts = Counter(row["inv_number"].casefold() for row in eligible)
    accounting_counts = Counter(
        row["accounting_inv_number"].casefold()
        for row in eligible
        if row["accounting_inv_number"]
    )
    existing = await repository.find_inventory_records(
        db,
        inventory_numbers=[row["inv_number"] for row in eligible],
        accounting_numbers=[
            row["accounting_inv_number"]
            for row in eligible
            if row["accounting_inv_number"]
        ],
    )
    for row in eligible:
        duplicate = inv_counts[row["inv_number"].casefold()] > 1
        duplicate = duplicate or bool(
            row["accounting_inv_number"]
            and accounting_counts[row["accounting_inv_number"].casefold()] > 1
        )
        duplicate = duplicate or any(
            existing_id != row["asset_id"]
            and (
                existing_inv == row["inv_number"]
                or (
                    row["accounting_inv_number"]
                    and existing_accounting == row["accounting_inv_number"]
                )
            )
            for existing_id, existing_inv, existing_accounting in existing
        )
        if duplicate:
            row["status"] = "duplicate"
            row["message"] = "Инвентарный номер уже используется или повторяется в файле."

    return FixedAssetInventoryImportPreview(
        items=[FixedAssetInventoryImportPreviewItem(**row) for row in resolved]
    )


async def apply_inventory_import(
    db: AsyncSession, payload: FixedAssetInventoryImportApply
) -> int:
    rows = payload.rows
    asset_ids = [row.asset_id for row in rows]
    inv_numbers = [row.inv_number for row in rows]
    accounting_numbers = [
        row.accounting_inv_number
        for row in rows
        if row.accounting_inv_number is not None
    ]
    if len(set(asset_ids)) != len(asset_ids):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An asset appears more than once in the import",
        )
    if len({value.casefold() for value in inv_numbers}) != len(inv_numbers):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate inventory numbers in the import",
        )
    if len({value.casefold() for value in accounting_numbers}) != len(
        accounting_numbers
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate accounting numbers in the import",
        )

    assets = await repository.get_assets_for_update(db, asset_ids)
    if len(assets) != len(asset_ids):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An imported asset no longer exists",
        )
    assets_by_id = {asset.id: asset for asset in assets}
    existing = await repository.find_inventory_records(
        db,
        inventory_numbers=inv_numbers,
        accounting_numbers=accounting_numbers,
    )
    for row in rows:
        for existing_id, existing_inv, existing_accounting in existing:
            if existing_id == row.asset_id:
                continue
            if existing_inv == row.inv_number or (
                row.accounting_inv_number
                and existing_accounting == row.accounting_inv_number
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An imported inventory number is already in use",
                )

    now = datetime.now(timezone.utc)
    updated = 0
    for row in rows:
        asset = assets_by_id[row.asset_id]
        old_values = {"inv_number": asset.inv_number}
        new_values = {"inv_number": row.inv_number}
        if row.accounting_inv_number is not None:
            old_values["accounting_inv_number"] = asset.accounting_inv_number
            new_values["accounting_inv_number"] = row.accounting_inv_number
        changed = (
            asset.inv_number != row.inv_number
            or asset.inv_number_is_provisional is True
            or (
                row.accounting_inv_number is not None
                and asset.accounting_inv_number != row.accounting_inv_number
            )
        )
        if not changed:
            continue

        asset_field_changes.record_manual_changes(
            db, asset, old_values=old_values, new_values=new_values
        )
        if asset.inv_number_is_provisional is True:
            db.add(
                AssetFieldChange(
                    asset_id=asset.id,
                    field="inv_number_is_provisional",
                    old_value=True,
                    new_value=False,
                    source="toir",
                    kind="manual",
                    status="applied",
                )
            )
        asset.inv_number = row.inv_number
        asset.inv_number_is_provisional = False
        if row.accounting_inv_number is not None:
            asset.accounting_inv_number = row.accounting_inv_number
        asset.updated_at = now
        updated += 1

    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory import conflicts with existing asset data",
        ) from exc
    return updated
