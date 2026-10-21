from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import WialonSettings


async def get_sync_settings(db: AsyncSession) -> WialonSettings | None:
    result = await db.execute(
        select(WialonSettings).where(WialonSettings.id == 1)
    )
    return result.scalar_one_or_none()


async def save_sync_status(
    db: AsyncSession, *, synced_at: datetime, status: str
) -> None:
    row = await get_sync_settings(db)
    if row is None:
        row = WialonSettings(id=1)
        db.add(row)
    row.last_sync_at = synced_at
    row.last_sync_status = status
    row.updated_at = synced_at
    await db.commit()
