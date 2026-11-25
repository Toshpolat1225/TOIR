"""Import rows into assets AND into the migration journal; or only record rows that were already written.

Modes:
  apply       write the value into the asset (only where it is still empty) and journal it
  record_only the value is already in the asset (an earlier import): check it equals the file, then only journal it
Dry-run by default: nothing is written unless `commit=True`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.data_migration import DataMigrationBatch, DataMigrationItem
from app.services.data_migration import FIELD_SPECS, _text


def load_manifest(path: str) -> list[dict[str, str]]:
    """A UTF-8 JSON list of {file, name, source_file, field}: batch names with Cyrillic stay out of the command line."""
    import json
    import os

    with open(path, encoding="utf-8-sig") as handle:
        entries = json.load(handle)
    if not isinstance(entries, list) or not entries:
        raise ValueError("The manifest must be a non-empty JSON list")
    base = os.path.dirname(os.path.abspath(path))
    out = []
    for entry in entries:
        for key in ("file", "name", "source_file"):
            if not str(entry.get(key, "")).strip():
                raise ValueError(f"Manifest entry without '{key}'")
        out.append({
            "file": entry["file"] if os.path.isabs(entry["file"]) else os.path.join(base, entry["file"]),
            "name": entry["name"], "source_file": entry["source_file"], "field": entry.get("field", "last_maint_date"),
        })
    return out


def _norm_serial(value: str | None) -> str:
    return (value or "").strip().lstrip("0")


async def import_rows(
    db: AsyncSession,
    rows: list[dict[str, str]],
    *,
    batch_name: str,
    source_file: str,
    field: str,
    record_only: bool = False,
    commit: bool = False,
    description: str | None = None,
) -> dict[str, Any]:
    spec = FIELD_SPECS.get(field)
    if spec is None:
        raise ValueError(f"Unsupported field: {field}")
    existing = list(
        (await db.execute(select(DataMigrationBatch).where(DataMigrationBatch.name == batch_name, DataMigrationBatch.source_file == source_file))).scalars().all()
    )
    for old_batch in existing:
        still_applied = (
            await db.execute(select(func.count()).select_from(DataMigrationItem).where(DataMigrationItem.batch_id == old_batch.id, DataMigrationItem.status == "applied"))
        ).scalar_one()
        if still_applied:
            raise ValueError("A batch with this name and source file already exists")
    # every earlier batch with this name was fully reverted: it stays as history, the file can be loaded again
    report: dict[str, Any] = {
        "rows": len(rows), "to_journal": 0, "written_to_assets": 0, "not_found": [], "ambiguous": [], "bad_value": [],
        "already_has_other_value": [], "mismatch_with_asset": [], "committed": commit, "mode": "record_only" if record_only else "apply",
    }
    planned: list[tuple[FixedAsset, Any, dict[str, str]]] = []
    seen: set[Any] = set()
    for number, row in enumerate(rows, start=2):
        inv = (row.get("inv") or "").strip()
        try:
            value = spec.parse((row.get("date") or "").strip())
        except Exception:
            report["bad_value"].append({"row": number, "inv": inv, "value": row.get("date")})
            continue
        assets = list((await db.execute(select(FixedAsset).where(FixedAsset.inv_number == inv))).scalars().all())
        if len(assets) > 1 and (row.get("serial") or "").strip():
            wanted = _norm_serial(row.get("serial"))
            assets = [a for a in assets if _norm_serial(a.serial_number) == wanted]
        if not assets:
            report["not_found"].append({"row": number, "inv": inv})
            continue
        if len(assets) > 1:
            report["ambiguous"].append({"row": number, "inv": inv})
            continue
        asset = assets[0]
        if asset.id in seen:
            report["ambiguous"].append({"row": number, "inv": inv, "why": "asset appears twice in the file"})
            continue
        current = getattr(asset, spec.attribute)
        if record_only:
            if current != value:
                report["mismatch_with_asset"].append({"row": number, "inv": inv, "asset_value": _text(current), "file_value": _text(value)})
                continue
        elif current is not None and current != value:
            report["already_has_other_value"].append({"row": number, "inv": inv, "asset_value": _text(current)})
            continue
        seen.add(asset.id)
        planned.append((asset, value, row))
    report["to_journal"] = len(planned)
    if not commit or not planned:
        return report
    for old_batch in existing:
        old_batch.name = f"{old_batch.name} [отменён {str(old_batch.id)[:8]}]"
    if existing:
        await db.flush()
    batch = DataMigrationBatch(name=batch_name, source_file=source_file, field=field, description=description)
    db.add(batch)
    await db.flush()
    for asset, value, row in planned:
        old = getattr(asset, spec.attribute)
        db.add(DataMigrationItem(
            batch_id=batch.id, asset_id=asset.id, old_value=None if record_only else _text(old), new_value=_text(value),
            raw_value=(row.get("raw") or "").strip() or None, status="applied",
        ))
        if not record_only and old != value:
            setattr(asset, spec.attribute, value)
            report["written_to_assets"] += 1
    await db.commit()
    report["batch_id"] = str(batch.id)
    return report
