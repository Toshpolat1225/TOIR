from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Nomenclature
from app.models.localization import (
    DepartmentTranslation,
    FixedAssetStatus,
    FixedAssetStatusTranslation,
    FixedAssetType,
    FixedAssetTypeTranslation,
    NomenclatureTranslation,
    SectionTranslation,
    WorkSubtaskTranslation,
    WorkTypeTranslation,
)
from app.models.maintenance import WorkSubtask, WorkType
from app.models.organization import Department, Section


@dataclass(frozen=True)
class TranslationTarget:
    model: type[Any]
    translation_model: type[Any]
    key_field: str
    foreign_key_field: str
    label_field: str


TARGETS = {
    "department": TranslationTarget(Department, DepartmentTranslation, "id", "department_id", "name"),
    "section": TranslationTarget(Section, SectionTranslation, "id", "section_id", "name"),
    "work_type": TranslationTarget(WorkType, WorkTypeTranslation, "id", "work_type_id", "name"),
    "work_subtask": TranslationTarget(WorkSubtask, WorkSubtaskTranslation, "id", "work_subtask_id", "name"),
    "nomenclature": TranslationTarget(Nomenclature, NomenclatureTranslation, "id", "nomenclature_id", "name"),
    "asset_type": TranslationTarget(FixedAssetType, FixedAssetTypeTranslation, "code", "type_code", "code"),
    "asset_status": TranslationTarget(FixedAssetStatus, FixedAssetStatusTranslation, "code", "status_code", "code"),
}


def _target(entity_type: str) -> tuple[TranslationTarget, Any, Any, Any]:
    config = TARGETS[entity_type]
    model_key = getattr(config.model, config.key_field)
    translation_key = getattr(config.translation_model, config.foreign_key_field)
    source_label = getattr(config.model, config.label_field)
    return config, model_key, translation_key, source_label


def _scope_filters(entity_type: str, master_section_id: UUID | None) -> list[Any]:
    if entity_type == "section":
        return [Section.id == master_section_id] if master_section_id else [false()]
    if entity_type == "department":
        return (
            [Department.id == select(Section.department_id).where(Section.id == master_section_id).scalar_subquery()]
            if master_section_id
            else [false()]
        )
    if entity_type == "nomenclature":
        return (
            [Nomenclature.department_id == select(Section.department_id).where(Section.id == master_section_id).scalar_subquery()]
            if master_section_id
            else [false()]
        )
    return []


async def list_entities(
    db: AsyncSession,
    *,
    entity_type: str,
    locale: str,
    q: str | None,
    limit: int,
    offset: int,
    master_section_id: UUID | None,
) -> tuple[list[dict[str, Any]], int]:
    config, model_key, translation_key, source_label = _target(entity_type)
    translation_name = config.translation_model.name
    filters: list[Any] = _scope_filters(entity_type, master_section_id)

    all_translations = (
        select(
            translation_key.label("entity_key"),
            func.jsonb_object_agg(
                config.translation_model.locale, translation_name
            ).label("translations"),
        )
        .group_by(translation_key)
        .subquery()
    )
    selected_name = func.coalesce(
        all_translations.c.translations[locale].astext, source_label
    )
    if q:
        filters.append(selected_name.ilike(f"%{q.strip()}%"))
    total_query = (
        select(func.count())
        .select_from(config.model)
        .outerjoin(
            all_translations,
            all_translations.c.entity_key == model_key,
        )
        .where(*filters)
    )
    total = (await db.execute(total_query)).scalar_one()
    query = (
        select(model_key, source_label, selected_name, all_translations.c.translations)
        .select_from(config.model)
        .outerjoin(
            all_translations,
            all_translations.c.entity_key == model_key,
        )
        .where(*filters)
        .order_by(selected_name.asc(), model_key.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(query)).all()
    return [
        {
            "id": str(row[0]),
            "source_name": row[1],
            "name": row[2],
            "locale": locale,
            "translation_missing": locale not in (row[3] or {}),
            "translations": row[3] or {},
            "missing_locales": [
                code for code in ("uz-Latn", "uz-Cyrl", "ru")
                if code not in (row[3] or {})
            ],
        }
        for row in rows
    ], total


async def get_entity(
    db: AsyncSession, *, entity_type: str, entity_id: str,
    master_section_id: UUID | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    config, model_key, translation_key, source_label = _target(entity_type)
    key: Any = entity_id
    if config.key_field == "id":
        try:
            key = UUID(entity_id)
        except ValueError:
            return None
    source = (
        await db.execute(
            select(source_label)
            .select_from(config.model)
            .where(model_key == key, *_scope_filters(entity_type, master_section_id))
        )
    ).scalar_one_or_none()
    if source is None:
        return None
    rows = (
        await db.execute(
            select(config.translation_model.locale, config.translation_model.name).where(
                translation_key == key
            )
        )
    ).all()
    return str(key), source, {locale: name for locale, name in rows}


async def get_translation_row(
    db: AsyncSession, *, entity_type: str, entity_id: str, locale: str
) -> Any | None:
    config, _, translation_key, _ = _target(entity_type)
    entity = await get_entity(db, entity_type=entity_type, entity_id=entity_id)
    if entity is None:
        return None
    key: Any = entity_id if config.key_field == "code" else UUID(entity_id)
    return (
        await db.execute(
            select(config.translation_model).where(
                translation_key == key,
                config.translation_model.locale == locale,
            )
        )
    ).scalar_one_or_none()


async def add_translation(
    db: AsyncSession, *, entity_type: str, entity_id: str, locale: str, name: str
) -> Any:
    config = TARGETS[entity_type]
    key: Any = entity_id if config.key_field == "code" else UUID(entity_id)
    row = config.translation_model(
        **{config.foreign_key_field: key, "locale": locale, "name": name}
    )
    db.add(row)
    return row
