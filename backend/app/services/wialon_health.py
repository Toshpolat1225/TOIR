"""Read-only health report of the Wialon feed: who is silent, who is unlinked, which counters are suspect or rejected.

It only reads. It exists because these problems are fixed on the Wialon side (a unit's counter configuration,
a dead tracker, a missing link), so the people who fix them need a list, not a log search.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LIST_LIMIT = 50

_SILENT = text(
    """
    SELECT a.inv_number, a.asset_type, s.last_cnm_at
    FROM wialon_counter_state s
    JOIN fixed_assets a ON a.id = s.asset_id
    WHERE (s.last_cnm_at IS NULL OR s.last_cnm_at < now() - make_interval(hours => :silent_hours))
      AND a.decommissioned_at IS NULL
    ORDER BY s.last_cnm_at NULLS FIRST, a.inv_number
    """
)
_UNMATCHED = text(
    """
    SELECT u.unit_id, u.name, u.last_message_at
    FROM wialon_units u
    WHERE NOT EXISTS (
        SELECT 1 FROM asset_source_links l
        WHERE l.source = 'wialon' AND l.external_id = u.unit_id AND l.status = 'active'
    )
    ORDER BY u.name
    """
)
_SUSPECT = text(
    """
    SELECT a.inv_number, a.asset_type, s.last_status, s.last_reason
    FROM wialon_counter_state s
    JOIN fixed_assets a ON a.id = s.asset_id
    WHERE s.suspect_absolute IS TRUE
    ORDER BY a.inv_number
    """
)
_REJECTS = text(
    """
    SELECT a.inv_number, a.asset_type, r.counter,
           count(*) AS rejects,
           count(DISTINCT r.reason) AS distinct_reasons,
           max(r.created_at) AS last_at,
           (array_agg(r.reason ORDER BY r.created_at DESC))[1] AS last_reason
    FROM wialon_rejected_readings r
    JOIN fixed_assets a ON a.id = r.asset_id
    WHERE r.created_at > now() - make_interval(days => :days)
    GROUP BY a.inv_number, a.asset_type, r.counter
    ORDER BY rejects DESC, a.inv_number
    """
)


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


async def build_report(db: AsyncSession, *, silent_hours: int = 24, reject_days: int = 7) -> dict[str, Any]:
    silent = _rows(await db.execute(_SILENT, {"silent_hours": silent_hours}))
    unmatched = _rows(await db.execute(_UNMATCHED))
    suspect = _rows(await db.execute(_SUSPECT))
    rejects = _rows(await db.execute(_REJECTS, {"days": reject_days}))
    return {
        "silent": {"hours": silent_hours, "total": len(silent), "units": silent[:LIST_LIMIT]},
        "unmatched_units": {"total": len(unmatched), "units": unmatched[:LIST_LIMIT]},
        "suspect_counters": {"total": len(suspect), "units": suspect[:LIST_LIMIT]},
        "rejected_readings": {
            "days": reject_days,
            "units_total": len(rejects),
            "readings_total": sum(row["rejects"] for row in rejects),
            "units": rejects[:LIST_LIMIT],
            "hint": (
                "A unit that is rejected over and over has its engine-hours counter (cneh) growing faster than "
                "real time: check the counter configuration of that unit in Wialon, not TOIR."
            ),
        },
    }
