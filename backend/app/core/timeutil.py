"""«Today» is the Tashkent day, not the container's (UTC) day (CODEX DATA-05).

Between 00:00 and 05:00 Tashkent time the UTC date is still «yesterday»: due dates, overdue flags and daily snapshots
computed with date.today() in a UTC container were a day behind. Uzbekistan has no daylight saving, so a fixed +05:00 is exact.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=5), "Asia/Tashkent")


def today_local(now: datetime | None = None) -> date:
    """The current calendar day in Tashkent. `now` is for tests and must be timezone-aware."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(LOCAL_TZ).date()
