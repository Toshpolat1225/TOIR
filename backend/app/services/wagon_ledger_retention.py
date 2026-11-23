"""Retention of the wagon mileage ledger.

An open train membership grows with every run, so each run writes a longer row and marks the shorter one «superseded».
Those intermediate rows pile up (thousands per hour). The ACTIVE rows are the result; superseded rows older than the
retention window are removed. Chain links that pointed at a removed row are cut (supersedes_id -> NULL), nothing else is touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from app.core.database import SessionFactory

DEFAULT_RETENTION_DAYS = 14


async def purge_superseded(*, older_than_days: int = DEFAULT_RETENTION_DAYS, apply: bool, batch_size: int = 5_000, now: datetime | None = None) -> dict[str, Any]:
    """Dry-run unless `apply`. Only status='superseded' rows older than the window are ever deleted."""
    if older_than_days < 1:
        raise ValueError("older_than_days must be at least 1")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=older_than_days)
    async with SessionFactory() as session:
        counts = (
            await session.execute(
                text(
                    "SELECT count(*) FILTER (WHERE status = 'active'), count(*) FILTER (WHERE status = 'superseded'), "
                    "count(*) FILTER (WHERE status = 'superseded' AND created_at < :cutoff), count(*) FROM wagon_mileage_ledger"
                ),
                {"cutoff": cutoff},
            )
        ).one()
    report: dict[str, Any] = {
        "cutoff": cutoff.isoformat(), "older_than_days": older_than_days, "rows_total": counts[3],
        "active_rows": counts[0], "superseded_rows": counts[1], "would_delete": counts[2], "applied": apply, "deleted": 0,
    }
    if not apply:
        return report
    deleted = 0
    while True:
        async with SessionFactory() as session:
            ids = [
                row[0]
                for row in (
                    await session.execute(
                        text("SELECT id FROM wagon_mileage_ledger WHERE status = 'superseded' AND created_at < :cutoff LIMIT :batch"),
                        {"cutoff": cutoff, "batch": batch_size},
                    )
                ).all()
            ]
            if not ids:
                break
            await session.execute(text("UPDATE wagon_mileage_ledger SET supersedes_id = NULL WHERE supersedes_id = ANY(:ids)"), {"ids": ids})
            result = await session.execute(
                text("DELETE FROM wagon_mileage_ledger WHERE id = ANY(:ids) AND status = 'superseded'"), {"ids": ids}
            )
            await session.commit()
        deleted += result.rowcount or 0
        if len(ids) < batch_size:
            break
    report["deleted"] = deleted
    return report
