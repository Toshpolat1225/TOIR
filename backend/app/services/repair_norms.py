"""Repair consumption norms: view, correct, add, delete and import (explicit fields, server-side checks).

A norm SET is (repair kind, equipment type, optional model, optional series group). Its lines are materials, spare parts and
lubricants; a line may belong to an assembly sub-group, and an «alternative» line points at its main line.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_models import AssetModel
from app.models.identity import User
from app.models.maintenance import WorkType
from app.models.repair_norms import RepairNormItem
from app.schemas.repair_norms import RepairNormItemCreate, RepairNormItemUpdate
from app.services.audit_log import set_audit_actor

_FIRST_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
UNIT_ALIASES = {"дона": "шт.", "шт": "шт.", "шт.": "шт.", "жамланма": "компл.", "комп-т": "компл.", "компл": "компл."}
SECTIONS = ("materials", "spare_parts", "lubricants")
BASES = ("per_repair", "per_month_per_unit")


def parse_quantity(text: str) -> Decimal | None:
    """The FIRST number of the source text: «1200» -> 1200, «12/1,44-2,4» -> 12 (pieces), «20./5» -> 20. None if there is none."""
    match = _FIRST_NUMBER.search((text or "").replace(" ", " "))
    if match is None:
        return None
    try:
        return Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:
        return None


def normalize_unit(unit: str | None) -> str | None:
    value = re.sub(r"\s+", " ", (unit or "")).strip()
    if not value:
        return None
    return UNIT_ALIASES.get(value.lower(), value.lower() if "/" in value else value)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


async def list_sets(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                RepairNormItem.work_type_id, WorkType.code, RepairNormItem.asset_type, RepairNormItem.asset_model_id, RepairNormItem.norm_group,
                AssetModel.name, func.count(), func.count().filter(RepairNormItem.section == "materials"),
                func.count().filter(RepairNormItem.section == "spare_parts"), func.count().filter(RepairNormItem.section == "lubricants"),
                func.count().filter(RepairNormItem.parent_id.is_not(None)), func.max(RepairNormItem.source_file), func.max(RepairNormItem.basis),
            )
            .join(WorkType, WorkType.id == RepairNormItem.work_type_id)
            .outerjoin(AssetModel, AssetModel.id == RepairNormItem.asset_model_id)
            .group_by(RepairNormItem.work_type_id, WorkType.code, RepairNormItem.asset_type, RepairNormItem.asset_model_id, RepairNormItem.norm_group, AssetModel.name)
            .order_by(RepairNormItem.asset_type, RepairNormItem.norm_group, AssetModel.name, WorkType.code)
        )
    ).all()
    return [
        {
            "work_type_id": r[0], "work_type_code": r[1], "asset_type": r[2], "asset_model_id": r[3], "norm_group": r[4], "model_name": r[5],
            "total": r[6], "materials": r[7], "spare_parts": r[8], "lubricants": r[9], "alternatives": r[10], "source_file": r[11], "basis": r[12],
        }
        for r in rows
    ]


def _set_filter(work_type_id: UUID, asset_type: str, asset_model_id: UUID | None, norm_group: str = ""):
    return and_(
        RepairNormItem.work_type_id == work_type_id, RepairNormItem.asset_type == asset_type, RepairNormItem.norm_group == (norm_group or ""),
        RepairNormItem.asset_model_id.is_(None) if asset_model_id is None else RepairNormItem.asset_model_id == asset_model_id,
    )


async def list_items(
    db: AsyncSession, work_type_id: UUID, asset_type: str, asset_model_id: UUID | None, *,
    norm_group: str = "", q: str | None = None, section: str | None = None, limit: int = 200, offset: int = 0,
) -> tuple[list[RepairNormItem], int]:
    base = select(RepairNormItem).where(_set_filter(work_type_id, asset_type, asset_model_id, norm_group))
    if section in SECTIONS:
        base = base.where(RepairNormItem.section == section)
    if q and q.strip():
        base = base.where(RepairNormItem.name.ilike(f"%{q.strip()}%"))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(RepairNormItem.seq).limit(limit).offset(offset))).scalars().all()
    return list(rows), total


def _actor(db: AsyncSession, user: User, route: str) -> None:
    set_audit_actor(db, actor_id=user.id, actor_name=user.full_name, actor_type="user", route=route)


async def create_item(db: AsyncSession, payload: RepairNormItemCreate, user: User) -> RepairNormItem:
    if await db.get(WorkType, payload.work_type_id) is None:
        raise HTTPException(status_code=422, detail="Unknown repair kind")
    if payload.asset_model_id is not None and await db.get(AssetModel, payload.asset_model_id) is None:
        raise HTTPException(status_code=422, detail="Unknown model")
    existing_basis = (
        await db.execute(select(func.max(RepairNormItem.basis)).where(_set_filter(payload.work_type_id, payload.asset_type, payload.asset_model_id, payload.norm_group)))
    ).scalar_one()
    if existing_basis is not None and existing_basis != payload.basis:
        raise HTTPException(status_code=422, detail="This norm set uses another basis; one set cannot mix per-repair and per-month lines")
    if payload.parent_id is not None:
        parent = await db.get(RepairNormItem, payload.parent_id)
        if parent is None or parent.parent_id is not None or (parent.work_type_id, parent.asset_type, parent.asset_model_id, parent.norm_group) != (
            payload.work_type_id, payload.asset_type, payload.asset_model_id, payload.norm_group or ""
        ):
            raise HTTPException(status_code=422, detail="The parent must be a main line of the same norm set")
    next_seq = (
        await db.execute(select(func.coalesce(func.max(RepairNormItem.seq), 0) + 1).where(_set_filter(payload.work_type_id, payload.asset_type, payload.asset_model_id, payload.norm_group)))
    ).scalar_one()
    _actor(db, user, "/api/v1/repair-norms/items")
    item = RepairNormItem(
        work_type_id=payload.work_type_id, asset_type=payload.asset_type, asset_model_id=payload.asset_model_id, norm_group=payload.norm_group or "",
        seq=next_seq, section=payload.section, group_name=(payload.group_name or "").strip() or None, basis=payload.basis, name=payload.name.strip(),
        unit=normalize_unit(payload.unit), quantity=parse_quantity(payload.quantity_text), quantity_text=payload.quantity_text.strip(),
        parent_id=payload.parent_id, note=(payload.note or "").strip() or None, updated_by=user.id,
    )
    db.add(item)
    try:
        await db.commit()
    except Exception as exc:  # unknown asset type (foreign key) etc.
        await db.rollback()
        raise HTTPException(status_code=422, detail="Could not create the line; check the equipment type") from exc
    await db.refresh(item)
    return item


async def update_item(db: AsyncSession, item_id: UUID, payload: RepairNormItemUpdate, user: User) -> RepairNormItem:
    item = (await db.execute(select(RepairNormItem).where(RepairNormItem.id == item_id).with_for_update())).scalar_one_or_none()
    if item is None:
        raise _not_found()
    _actor(db, user, f"/api/v1/repair-norms/items/{item_id}")
    fields = payload.model_fields_set
    if "section" in fields and payload.section is not None:
        item.section = payload.section
    if "group_name" in fields:
        item.group_name = (payload.group_name or "").strip() or None
    if "name" in fields and payload.name is not None:
        item.name = payload.name.strip()
    if "unit" in fields:
        item.unit = normalize_unit(payload.unit)
    if "quantity_text" in fields and payload.quantity_text is not None:
        item.quantity_text = payload.quantity_text.strip()
        item.quantity = parse_quantity(payload.quantity_text)
    if "note" in fields:
        item.note = (payload.note or "").strip() or None
    item.updated_by = user.id
    item.updated_at = func.now()
    await db.commit()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, item_id: UUID, user: User) -> None:
    item = await db.get(RepairNormItem, item_id)
    if item is None:
        raise _not_found()
    _actor(db, user, f"/api/v1/repair-norms/items/{item_id}")
    await db.delete(item)  # the alternative lines of this line go with it (ON DELETE CASCADE)
    await db.commit()


async def delete_set(db: AsyncSession, work_type_id: UUID, asset_type: str, asset_model_id: UUID | None, user: User, norm_group: str = "") -> int:
    _actor(db, user, "/api/v1/repair-norms/sets")
    result = await db.execute(delete(RepairNormItem).where(_set_filter(work_type_id, asset_type, asset_model_id, norm_group)))
    await db.commit()
    return result.rowcount or 0


# ── import ────────────────────────────────────────────────────────────────────

async def import_set(
    db: AsyncSession, rows: list[dict[str, str]], *, work_type_code: str, asset_type: str, model_name: str | None,
    source_file: str, source_sheet: str, commit: bool = False, norm_group: str = "", basis: str = "per_repair",
) -> dict[str, Any]:
    """Load one cleaned CSV as a norm set. Refuses a set that already has lines (never mixes two imports). Dry-run unless `commit`."""
    if basis not in BASES:
        raise ValueError(f"Unknown basis: {basis}")
    work_type = (await db.execute(select(WorkType).where(WorkType.code == work_type_code))).scalar_one_or_none()
    if work_type is None:
        raise ValueError(f"Unknown repair kind: {work_type_code}")
    model_id: UUID | None = None
    if model_name:
        models = (await db.execute(select(AssetModel).where(AssetModel.name == model_name))).scalars().all()
        if len(models) != 1:
            raise ValueError(f"Model '{model_name}': expected exactly one, found {len(models)}")
        model_id = models[0].id
    existing = (await db.execute(select(func.count()).select_from(RepairNormItem).where(_set_filter(work_type.id, asset_type, model_id, norm_group)))).scalar_one()
    if existing:
        raise ValueError(f"This norm set already has {existing} lines; delete it first if you want to load it again")
    report: dict[str, Any] = {
        "work_type": work_type_code, "asset_type": asset_type, "model": model_name, "norm_group": norm_group, "basis": basis, "rows": len(rows),
        "lines": 0, "alternatives": 0, "groups": 0, "bad_rows": [], "committed": commit,
    }
    items: dict[int, RepairNormItem] = {}
    group_names: set[str] = set()
    for number, row in enumerate(rows, start=2):
        try:
            seq = int(row["seq"])
            section = row["section"].strip()
            name = row["name"].strip()
            text_value = row["quantity_text"].strip()
            if section not in SECTIONS or not name or not text_value or seq in items:
                raise ValueError("incomplete")
        except (KeyError, ValueError):
            report["bad_rows"].append({"row": number})
            continue
        quantity = parse_quantity(text_value)
        if quantity is None:  # a norm without a number is not a norm (e.g. a signature line): it stops the whole load
            report["bad_rows"].append({"row": number, "why": "quantity text has no number"})
            continue
        parent_seq = row.get("parent_seq", "").strip()
        parent = items.get(int(parent_seq)) if parent_seq else None
        if parent_seq and parent is None:
            report["bad_rows"].append({"row": number, "why": "parent line not found"})
            continue
        group_name = (row.get("group_name") or "").strip() or None
        if group_name:
            group_names.add(group_name)
        items[seq] = RepairNormItem(
            work_type_id=work_type.id, asset_type=asset_type, asset_model_id=model_id, norm_group=norm_group, seq=seq, section=section,
            group_name=group_name, basis=basis, name=name, unit=normalize_unit(row.get("unit")), quantity=quantity, quantity_text=text_value,
            note=(row.get("note") or "").strip() or None, source_file=source_file, source_sheet=source_sheet,
        )
        items[seq]._parent_obj = parent  # type: ignore[attr-defined]
        report["lines"] += 1
        report["alternatives"] += 1 if parent is not None else 0
    report["groups"] = len(group_names)
    if not commit or report["bad_rows"]:
        return report
    db.add_all(items.values())
    await db.flush()
    for item in items.values():
        parent = getattr(item, "_parent_obj", None)
        if parent is not None:
            item.parent_id = parent.id
    await db.commit()
    return report


def load_manifest(path: str) -> list[dict[str, str]]:
    import json
    import os

    with open(path, encoding="utf-8-sig") as handle:
        entries = json.load(handle)
    if not isinstance(entries, list) or not entries:
        raise ValueError("The manifest must be a non-empty JSON list")
    base = os.path.dirname(os.path.abspath(path))
    out = []
    for entry in entries:
        for key in ("file", "work_type_code", "asset_type", "source_file"):
            if not str(entry.get(key, "")).strip():
                raise ValueError(f"Manifest entry without '{key}'")
        out.append({
            # the CSV sits next to the manifest: only its file name counts, so the manifest works from any folder
            "file": os.path.join(base, os.path.basename(entry["file"])),
            "work_type_code": entry["work_type_code"], "asset_type": entry["asset_type"], "model_name": entry.get("model_name") or "",
            "source_file": entry["source_file"], "source_sheet": entry.get("source_sheet", ""),
            "norm_group": entry.get("norm_group", ""), "basis": entry.get("basis", "per_repair"),
        })
    return out
