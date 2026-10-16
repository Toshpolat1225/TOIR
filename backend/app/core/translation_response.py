from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.localization import (
    DepartmentTranslation,
    FixedAssetStatusTranslation,
    FixedAssetTypeTranslation,
    NomenclatureTranslation,
    SectionTranslation,
    WorkSubtaskTranslation,
    WorkTypeTranslation,
)


async def _lookup(
    db: AsyncSession, model: type[Any], key_name: str, ids: set[Any], locale: str
) -> dict[Any, str]:
    if not ids:
        return {}
    key = getattr(model, key_name)
    rows = (
        await db.execute(
            select(key, model.name).where(key.in_(ids), model.locale == locale)
        )
    ).all()
    return {entity_id: name for entity_id, name in rows}


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def localize_reference_response(
    db: AsyncSession, *, path: str, locale: str, payload: Any
) -> Any:
    """Append localized labels but keep canonical names and identifiers intact."""
    if not isinstance(payload, (dict, list)):
        return payload

    sections: set[UUID] = set()
    departments: set[UUID] = set()
    work_types: set[UUID] = set()
    subtasks: set[UUID] = set()
    nomenclature: set[UUID] = set()
    asset_types: set[str] = set()
    asset_statuses: set[str] = set()
    nodes: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            nodes.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    if path.startswith("/sections"):
        sections.update(filter(None, (_uuid(node.get("id")) for node in nodes if "name" in node)))
    elif path.startswith("/departments"):
        departments.update(filter(None, (_uuid(node.get("id")) for node in nodes if "name" in node)))
    elif path.startswith("/work-types"):
        work_types.update(filter(None, (_uuid(node.get("id")) for node in nodes if "name" in node)))
        for node in nodes:
            if "subtasks" in node:
                subtasks.update(
                    filter(None, (_uuid(item.get("id")) for item in node["subtasks"] if isinstance(item, dict)))
                )
    elif path.startswith("/work-subtasks"):
        subtasks.update(filter(None, (_uuid(node.get("id")) for node in nodes if "name" in node)))
    elif path.startswith("/nomenclature"):
        nomenclature.update(filter(None, (_uuid(node.get("id")) for node in nodes if "name" in node)))

    for node in nodes:
        if node.get("section_id"):
            value = _uuid(node["section_id"])
            if value:
                sections.add(value)
        if node.get("department_id"):
            value = _uuid(node["department_id"])
            if value:
                departments.add(value)
        if node.get("work_type_id"):
            value = _uuid(node["work_type_id"])
            if value:
                work_types.add(value)
        if path == "/dashboard/summary" and node.get("work_type_ids"):
            work_types.update(
                filter(None, (_uuid(item.strip()) for item in str(node["work_type_ids"]).split(",")))
            )
        if node.get("nomenclature_id"):
            value = _uuid(node["nomenclature_id"])
            if value:
                nomenclature.add(value)
        if path.startswith("/fixed-assets") or path in ("/reports/fixed-assets", "/dashboard/summary"):
            if node.get("asset_type"):
                asset_types.add(str(node["asset_type"]))
            if node.get("status"):
                asset_statuses.add(str(node["status"]))

    lookup = {
        "section": await _lookup(db, SectionTranslation, "section_id", sections, locale),
        "department": await _lookup(db, DepartmentTranslation, "department_id", departments, locale),
        "work_type": await _lookup(db, WorkTypeTranslation, "work_type_id", work_types, locale),
        "work_subtask": await _lookup(db, WorkSubtaskTranslation, "work_subtask_id", subtasks, locale),
        "nomenclature": await _lookup(db, NomenclatureTranslation, "nomenclature_id", nomenclature, locale),
        "asset_type": await _lookup(db, FixedAssetTypeTranslation, "type_code", asset_types, locale),
        "asset_status": await _lookup(db, FixedAssetStatusTranslation, "status_code", asset_statuses, locale),
    }

    for node in nodes:
        entity = None
        if path.startswith("/sections") and "id" in node and "name" in node:
            entity = ("section", _uuid(node["id"]), "name")
        elif path.startswith("/departments") and "id" in node and "name" in node:
            entity = ("department", _uuid(node["id"]), "name")
        elif path.startswith("/work-types") and "work_type_id" in node and "name" in node:
            entity = ("work_subtask", _uuid(node["id"]), "name")
        elif path.startswith("/work-types") and "id" in node and "name" in node:
            entity = ("work_type", _uuid(node["id"]), "name")
        elif path.startswith("/work-subtasks") and "id" in node and "name" in node:
            entity = ("work_subtask", _uuid(node["id"]), "name")
        elif path.startswith("/nomenclature") and "id" in node and "name" in node:
            entity = ("nomenclature", _uuid(node["id"]), "name")
        if entity:
            kind, entity_id, key = entity
            translation = lookup[kind].get(entity_id) if entity_id else None
            node["localized_name"] = translation or node[key]
            node["translation_missing"] = translation is None
        if node.get("department_id") and node.get("department_name"):
            entity_id = _uuid(node["department_id"])
            translation = lookup["department"].get(entity_id) if entity_id else None
            node["localized_department_name"] = translation or node["department_name"]
            node["department_translation_missing"] = translation is None
        section_name_field = "section_name" if node.get("section_name") else "section"
        if node.get("section_id") and node.get(section_name_field):
            entity_id = _uuid(node["section_id"])
            translation = lookup["section"].get(entity_id) if entity_id else None
            node["localized_section_name"] = translation or node[section_name_field]
            if section_name_field == "section":
                node["localized_section"] = translation or node[section_name_field]
            node["section_translation_missing"] = translation is None
        if node.get("work_type_id") and node.get("work_type_name"):
            entity_id = _uuid(node["work_type_id"])
            translation = lookup["work_type"].get(entity_id) if entity_id else None
            node["localized_work_type_name"] = translation or node["work_type_name"]
            node["work_type_translation_missing"] = translation is None
        elif node.get("work_type_id") and node.get("work_type"):
            entity_id = _uuid(node["work_type_id"])
            translation = lookup["work_type"].get(entity_id) if entity_id else None
            node["localized_work_type"] = translation or node["work_type"]
            node["work_type_translation_missing"] = translation is None
        if path == "/dashboard/summary" and node.get("work_type_ids") and node.get("repair_kind"):
            ids = [
                _uuid(item.strip())
                for item in str(node["work_type_ids"]).split(",")
            ]
            codes = str(node["repair_kind"]).split(",")
            labels = [lookup["work_type"].get(entity_id) if entity_id else None for entity_id in ids]
            node["localized_repair_kind"] = ", ".join(
                label or code.strip()
                for code, label in zip(codes, labels, strict=False)
            )
            node["repair_kind_translation_missing"] = any(label is None for label in labels)
        if node.get("nomenclature_id") and node.get("name"):
            entity_id = _uuid(node["nomenclature_id"])
            translation = lookup["nomenclature"].get(entity_id) if entity_id else None
            node["localized_nomenclature_name"] = translation or node["name"]
            node["nomenclature_translation_missing"] = translation is None
        if (path.startswith("/fixed-assets") or path in ("/reports/fixed-assets", "/dashboard/summary")) and node.get("asset_type"):
            type_label = lookup["asset_type"].get(node["asset_type"])
            status_label = lookup["asset_status"].get(node.get("status"))
            node["asset_type_label"] = type_label or node["asset_type"]
            node["asset_status_label"] = status_label or node.get("status")
            node["asset_type_translation_missing"] = type_label is None
            node["asset_status_translation_missing"] = status_label is None
    return payload
