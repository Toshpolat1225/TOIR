import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base
from app.models.assets import FixedAsset
from app.repositories import asset_models as asset_models_repository
from app.repositories import assets as assets_repository
from app.schemas.asset_data_import import (
    FixedAssetPassportImportPreviewRow,
    FixedAssetsPassportImportApplyRead,
    FixedAssetsPassportImportApplyRequest,
    FixedAssetsPassportImportPreview,
    FixedAssetsPassportImportRequest,
)
from app.services import asset_field_changes, asset_links as asset_links_service
from app.services import asset_passport

_TYPE_BY_SOURCE = {
    "вагон-самосвал": "wagon",
    "тяговой агрегат": "locomotive",
    "цистерна": "tank_car",
    "платформа": "platform",
    "тепловоз": "diesel",
    "специальный самоходный подвижной состав": "special_self_propelled",
}
_IMPORT_LIMIT = 2000
_REPLACEABLE_ASSET_CHILD_TABLES = frozenset(
    {"asset_field_changes", "asset_source_links"}
)


def _read_date(value: Any, *, optional: bool) -> date | None:
    if value is None or value == "":
        if optional:
            return None
        raise ValueError("Дата обязательна.")
    if not isinstance(value, str):
        raise ValueError("Дата должна быть текстом.")
    raw = value.strip()
    try:
        if len(raw) == 10:
            return date.fromisoformat(raw)
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("Неверный формат даты.") from exc
    if parsed.time() != time.min:
        raise ValueError("В дате не должно быть времени.")
    return parsed.date()


def _source_hash(document: Any) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _input_document(json_text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        document = json.loads(json_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файл JSON повреждён.",
        ) from exc
    if not isinstance(document, dict) or not isinstance(document.get("assets"), list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В JSON должен быть список assets.",
        )
    rows = document["assets"]
    if not rows or len(rows) > _IMPORT_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Количество строк должно быть от 1 до {_IMPORT_LIMIT}.",
        )
    if any(not isinstance(row, dict) for row in rows):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Каждая строка assets должна быть объектом.",
        )
    return document, rows


def _external_id(links: dict[str, Any], key: str, *, digits_only: bool) -> str | None:
    value = links.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Внешний ID указан неверно.")
    external_id = str(value).strip()
    if not external_id or len(external_id) > 100:
        raise ValueError("Внешний ID указан неверно.")
    if digits_only and not external_id.isdigit():
        raise ValueError("GTK ID должен состоять из цифр.")
    return external_id


async def _prepare_rows(
    db: AsyncSession, json_text: str
) -> tuple[str, list[dict[str, Any]], dict[str, int], dict[str, int], int, int]:
    document, source_rows = _input_document(json_text)
    sections = await assets_repository.list_active_sections(db)
    section_ids: dict[str, list[UUID]] = defaultdict(list)
    for section in sections:
        section_ids[section.name.strip()].append(section.id)

    prepared: list[dict[str, Any]] = []
    inventory_counts: Counter[str] = Counter()
    number_counts: Counter[tuple[str, str, str]] = Counter()
    link_counts: dict[str, Counter[str]] = {
        "wialon_id": Counter(),
        "gtk_id": Counter(),
    }
    model_types: dict[str, set[str]] = defaultdict(set)
    type_counts: Counter[str] = Counter()
    section_counts: Counter[str] = Counter()

    for row_number, raw in enumerate(source_rows, start=1):
        issue: str | None = None
        source_type = raw.get("asset_type")
        model_name = raw.get("model")
        serial_number = raw.get("serial_number")
        inv_number = raw.get("inv_number")
        section_name = raw.get("section")
        asset_type = None
        commissioned_at = None
        decommissioned_at = None
        year_built = None
        section_id = None
        wialon_id = None
        gtk_id = None
        try:
            if not isinstance(source_type, str):
                raise ValueError("Тип ОС не указан.")
            normalized_source_type = " ".join(source_type.split()).casefold()
            asset_type = _TYPE_BY_SOURCE.get(normalized_source_type)
            if asset_type is None:
                raise ValueError("Неизвестный тип ОС.")
            if not isinstance(model_name, str) or not model_name.strip():
                raise ValueError("Модель не указана.")
            model_name = model_name.strip()
            if not isinstance(serial_number, str) or not serial_number.strip():
                raise ValueError("Серийный номер не указан.")
            serial_number = serial_number.strip()
            if not isinstance(inv_number, str) or not inv_number.strip():
                raise ValueError("Инвентарный номер не указан.")
            inv_number = inv_number.strip()
            if inv_number.casefold().startswith("wialon-"):
                raise ValueError("Временный номер Wialon нельзя импортировать как реальный.")
            if not isinstance(section_name, str) or not section_name.strip():
                raise ValueError("Участок не указан.")
            section_name = section_name.strip()
            matching_sections = section_ids.get(section_name, [])
            if len(matching_sections) != 1:
                raise ValueError("Участок не найден или его название неоднозначно.")
            section_id = matching_sections[0]
            year_value = raw.get("year_built")
            if isinstance(year_value, bool) or not (
                isinstance(year_value, int)
                or isinstance(year_value, str)
                and year_value.strip().isdigit()
            ):
                raise ValueError("Год постройки указан неверно.")
            year_built = int(year_value)
            commissioned_at = _read_date(raw.get("commissioned_at"), optional=False)
            decommissioned_at = _read_date(
                raw.get("decommissioned_at"), optional=True
            )
            asset_passport.validate_passport_values(
                year_built=year_built,
                commissioned_at=commissioned_at,
                decommissioned_at=decommissioned_at,
            )
            links = raw.get("links")
            if links is None:
                links = {}
            if not isinstance(links, dict):
                raise ValueError("Связи источников указаны неверно.")
            wialon_id = _external_id(links, "wialon_id", digits_only=False)
            gtk_id = _external_id(links, "gtk_id", digits_only=True)
        except (TypeError, ValueError, OverflowError) as exc:
            issue = str(exc)

        model_normalized = (
            asset_passport.normalize_token(model_name)
            if isinstance(model_name, str) and model_name.strip()
            else ""
        )
        normalized_inventory = (
            asset_passport.normalize_token(inv_number)
            if isinstance(inv_number, str) and inv_number.strip()
            else ""
        )
        normalized_number = (
            asset_passport.normalize_token(serial_number)
            if isinstance(serial_number, str) and serial_number.strip()
            else ""
        )
        if issue is None and asset_type and model_normalized:
            model_types[model_normalized].add(asset_type)
            if normalized_inventory:
                inventory_counts[normalized_inventory] += 1
            if normalized_number and decommissioned_at is None:
                number_counts[(asset_type, model_normalized, normalized_number)] += 1
            if wialon_id:
                link_counts["wialon_id"][wialon_id] += 1
            if gtk_id:
                link_counts["gtk_id"][gtk_id] += 1
            type_counts[asset_type] += 1
            section_counts[section_name] += 1

        prepared.append(
            {
                "row_number": row_number,
                "status": "invalid" if issue else "ready",
                "issue": issue,
                "asset_type": asset_type,
                "name": (
                    f"{model_name.strip()} {serial_number.strip()}"
                    if isinstance(model_name, str)
                    and isinstance(serial_number, str)
                    else None
                ),
                "model": model_name.strip() if isinstance(model_name, str) else None,
                "model_normalized": model_normalized or None,
                "serial_number": (
                    serial_number.strip()
                    if isinstance(serial_number, str)
                    else None
                ),
                "normalized_serial_number": normalized_number or None,
                "inv_number": (
                    inv_number.strip() if isinstance(inv_number, str) else None
                ),
                "commissioned_at": commissioned_at,
                "decommissioned_at": decommissioned_at,
                "year_built": year_built,
                "section": section_name.strip() if isinstance(section_name, str) else None,
                "section_id": section_id,
                "wialon_id": wialon_id,
                "gtk_id": gtk_id,
            }
        )

    duplicate_inventory_groups = {
        number for number, count in inventory_counts.items() if count > 1
    }
    duplicate_number_groups = {
        key for key, count in number_counts.items() if count > 1
    }
    for row in prepared:
        if row["status"] != "ready":
            continue
        reasons: list[str] = []
        if row["model_normalized"] and len(
            model_types[row["model_normalized"]]
        ) > 1:
            row["status"] = "invalid"
            row["issue"] = "Одна модель указана для разных типов ОС."
            continue
        if asset_passport.normalize_token(row["inv_number"]) in duplicate_inventory_groups:
            reasons.append("Инвентарный номер повторяется в файле.")
        number_key = (
            row["asset_type"],
            row["model_normalized"],
            row["normalized_serial_number"],
        )
        if (
            row["decommissioned_at"] is None
            and row["normalized_serial_number"]
            and number_key in duplicate_number_groups
        ):
            reasons.append("Серийный номер повторяется для модели и типа ОС.")
        duplicate_external_id = any(
            row[field] and link_counts[field][row[field]] > 1
            for field in ("wialon_id", "gtk_id")
        )
        if duplicate_external_id:
            row["status"] = "invalid"
            row["issue"] = "Внешний ID повторяется в файле."
        elif reasons:
            row["status"] = "duplicate"
            row["issue"] = " ".join(dict.fromkeys(reasons))

    return (
        _source_hash(document),
        prepared,
        dict(type_counts),
        dict(section_counts),
        len(duplicate_inventory_groups),
        len(duplicate_number_groups),
    )


async def preview(
    db: AsyncSession, payload: FixedAssetsPassportImportRequest
) -> FixedAssetsPassportImportPreview:
    (
        source_hash,
        rows,
        type_counts,
        section_counts,
        duplicate_inventory_groups,
        duplicate_number_groups,
    ) = await _prepare_rows(db, payload.json_text)
    ready = sum(row["status"] in {"ready", "duplicate"} for row in rows)
    return FixedAssetsPassportImportPreview(
        source_hash=source_hash,
        total=len(rows),
        current_assets=await assets_repository.count_fixed_assets(db),
        ready=ready,
        blocked=len(rows) - ready,
        duplicate_inventory_groups=duplicate_inventory_groups,
        duplicate_number_groups=duplicate_number_groups,
        type_counts=type_counts,
        section_counts=section_counts,
        items=[FixedAssetPassportImportPreviewRow(**row) for row in rows],
    )


async def _delete_asset_rows(db: AsyncSession) -> int:
    tables = list(Base.metadata.sorted_tables)
    asset_table = FixedAsset.__table__
    asset_ids = list((await db.execute(select(asset_table.c.id))).scalars().all())
    if not asset_ids:
        return 0

    blockers: set[str] = set()
    for child_table in tables:
        if child_table.name in _REPLACEABLE_ASSET_CHILD_TABLES:
            continue
        for foreign_key in child_table.foreign_keys:
            if foreign_key.column.table is not asset_table:
                continue
            result = await db.execute(
                select(child_table.c[foreign_key.parent.name])
                .where(child_table.c[foreign_key.parent.name].in_(asset_ids))
                .limit(1)
            )
            if result.first() is not None:
                blockers.add(child_table.name)
    if blockers:
        table_list = ", ".join(sorted(blockers))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Реестр не заменён: средства связаны с другими данными "
                f"({table_list}). Сначала решите судьбу этих записей."
            ),
        )

    result = await db.execute(delete(asset_table))
    return max(result.rowcount or 0, 0)


async def apply(
    db: AsyncSession, payload: FixedAssetsPassportImportApplyRequest
) -> FixedAssetsPassportImportApplyRead:
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(1947382901, 21)"))
        (
            source_hash,
            rows,
            _,
            _,
            _,
            _,
        ) = await _prepare_rows(db, payload.json_text)
        if source_hash != payload.source_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="JSON изменился после предварительной проверки.",
            )
        if any(row["status"] == "invalid" for row in rows):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Импорт отменён: сначала исправьте все строки с ошибками.",
            )

        deleted_count = await _delete_asset_rows(db)

        section_rows = await assets_repository.list_active_sections(db)
        section_ids = {section.name.strip(): section.id for section in section_rows}
        model_ids: dict[str, tuple[str, UUID]] = {}
        imported_assets: list[FixedAsset] = []
        source_links: list[tuple[FixedAsset, str, str]] = []

        for row in rows:
            model_name = row["model"]
            normalized_name = row["model_normalized"]
            cached_model = model_ids.get(normalized_name)
            if cached_model is not None:
                if cached_model[0] != row["asset_type"]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Название модели используется для нескольких типов ОС.",
                    )
                model_id = cached_model[1]
            else:
                model = await asset_models_repository.add_if_missing(
                    db,
                    name=model_name,
                    name_normalized=normalized_name,
                    asset_type=row["asset_type"],
                    series=model_name,
                )
                if model.asset_type != row["asset_type"]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Название модели уже используется для другого типа ОС.",
                    )
                model_id = model.id
                model_ids[normalized_name] = (row["asset_type"], model_id)

            section_id = section_ids.get(row["section"])
            if section_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Участок изменился после проверки файла.",
                )
            asset = FixedAsset(
                inv_number=row["inv_number"],
                asset_type=row["asset_type"],
                section_id=section_id,
                status="operational",
                year_built=row["year_built"],
                serial_number=row["serial_number"],
                model_id=model_id,
                commissioned_at=row["commissioned_at"],
                decommissioned_at=row["decommissioned_at"],
                inv_number_is_provisional=False,
                wialon_id=row["wialon_id"],
                gtk_id=row["gtk_id"],
            )
            db.add(asset)
            imported_assets.append(asset)
            if row["wialon_id"]:
                source_links.append((asset, "wialon", row["wialon_id"]))
            if row["gtk_id"]:
                source_links.append((asset, "gtk", row["gtk_id"]))

        await db.flush()
        for asset, source, external_id in source_links:
            await asset_links_service.link(
                db,
                asset.id,
                source,
                external_id,
                by=None,
                method="import",
            )
        for asset in imported_assets:
            asset_field_changes.record_changes(
                db,
                asset,
                old_values={},
                new_values={
                    field: getattr(asset, field)
                    for field in asset_field_changes.PASSPORT_FIELD_NAMES
                },
                source="import",
                kind="manual",
            )
        await db.flush()
        await db.commit()
        return FixedAssetsPassportImportApplyRead(
            deleted_count=deleted_count,
            imported_count=len(imported_assets),
        )
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Импорт отменён из-за конфликта данных; изменения откатаны.",
        ) from exc
