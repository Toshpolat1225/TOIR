"""Read-only queries for the conflicts page (passport conflicts + Wialon counter blocks)."""
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_field_changes import AssetFieldChange
from app.models.assets import FixedAsset

BLOCK_REASON = "same_time_different_odometer"
BLOCKED_READING_REASONS = (
    "same_time_different_odometer",
    "counter_state_blocked_by_unresolved_conflict",
)


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_field_conflicts(
    db: AsyncSession,
    *,
    status: str,
    source: str | None,
    field: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[AssetFieldChange, str, str | None, str]], int]:
    filters: list[Any] = [AssetFieldChange.status == status]
    if source:
        filters.append(AssetFieldChange.source == source)
    if field:
        filters.append(AssetFieldChange.field == field)
    if q:
        pattern = _like(q.strip())
        filters.append(
            or_(
                FixedAsset.inv_number.ilike(pattern, escape="\\"),
                FixedAsset.serial_number.ilike(pattern, escape="\\"),
            )
        )
    base = (
        select(AssetFieldChange)
        .join(FixedAsset, FixedAsset.id == AssetFieldChange.asset_id)
        .where(*filters)
    )
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = await db.execute(
        select(
            AssetFieldChange,
            FixedAsset.inv_number,
            FixedAsset.serial_number,
            FixedAsset.asset_type,
        )
        .join(FixedAsset, FixedAsset.id == AssetFieldChange.asset_id)
        .where(*filters)
        .order_by(AssetFieldChange.created_at.desc(), AssetFieldChange.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [tuple(row) for row in rows.all()], total


_BLOCKED_FROM = """
FROM wialon_counter_state s
JOIN fixed_assets a ON a.id = s.asset_id
WHERE s.last_reason = :block_reason
  AND a.asset_type IN ('locomotive', 'diesel')
"""


async def list_blocked_counters(
    db: AsyncSession,
    *,
    q: str | None,
    section_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    where = ""
    params: dict[str, Any] = {"block_reason": BLOCK_REASON}
    if q:
        where += " AND (a.inv_number ILIKE :q ESCAPE '\\' OR a.serial_number ILIKE :q ESCAPE '\\')"
        params["q"] = _like(q.strip())
    if section_id is not None:
        where += " AND a.section_id = :section_id"
        params["section_id"] = section_id

    affected = """
        (SELECT count(DISTINCT c.object_gtk_id)
           FROM gtk_train_members lm
           JOIN asset_source_links l
             ON l.source = 'gtk' AND l.status = 'active'
            AND l.external_id = lm.object_gtk_id::text
           JOIN gtk_train_members c
             ON c.train_gtk_id = lm.train_gtk_id AND c.kind = 'carriage'
            AND c.observed_to IS NULL
          WHERE lm.kind = 'locomotive' AND lm.observed_to IS NULL
            AND l.asset_id = a.id)
    """
    total = (
        await db.execute(
            text(f"SELECT count(*) {_BLOCKED_FROM} {where}"), params
        )
    ).scalar_one()
    summary_row = (
        await db.execute(
            text(
                f"SELECT count(*) AS locomotives, "
                f"coalesce(sum({affected}), 0) AS wagons {_BLOCKED_FROM} {where}"
            ),
            params,
        )
    ).one()
    rows = await db.execute(
        text(
            f"""
            SELECT a.id AS asset_id, a.inv_number, a.serial_number, a.asset_type,
                   a.section_id, a.wialon_id,
                   s.updated_at AS blocked_since, s.last_cnm, s.last_cnm_at,
                   (SELECT count(*) FROM wialon_odometer_readings r
                     WHERE r.asset_id = a.id
                       AND r.received_at > now() - interval '24 hours'
                       AND r.rejection_reason = ANY(:reasons)) AS blocked_readings_24h,
                   {affected} AS affected_wagons
            {_BLOCKED_FROM} {where}
            ORDER BY affected_wagons DESC, a.inv_number
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            **params,
            "reasons": list(BLOCKED_READING_REASONS),
            "limit": limit,
            "offset": offset,
        },
    )
    summary = {
        "blocked_locomotives": int(summary_row.locomotives),
        "affected_wagons": int(summary_row.wagons),
    }
    return [dict(row._mapping) for row in rows.all()], total, summary
