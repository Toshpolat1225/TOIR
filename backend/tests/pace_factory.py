"""Pace history for pg tests: since the living plan a unit with no GPS history has NO forecast (never a guessed pace)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.models.assets import MileageHistory


async def seed_pace(db, asset_id: UUID, mileage, *, per_day: int = 200, days: int = 10) -> None:
    """`days` end-of-day odometer readings ending yesterday, `per_day` km apart, so the unit's own pace is `per_day`."""
    top = Decimal(mileage)
    now = datetime.now(timezone.utc)
    for ago in range(days, 0, -1):
        db.add(MileageHistory(asset_id=asset_id, mileage=top - Decimal(per_day) * ago, source="manual",
                              recorded_at=now - timedelta(days=ago)))
    await db.flush()
