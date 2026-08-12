from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from ..repositories.maintenance_interval import MaintenanceIntervalRepository
from ..schemas.maintenance_interval import MaintenanceIntervalRead, MaintenanceIntervalCreate, MaintenanceIntervalUpdate
from ..schemas.pagination import Paginated


class MaintenanceIntervalService:
    def __init__(self, db: AsyncSession):
        self.repo = MaintenanceIntervalRepository(db)

    async def get_all(self, limit: int, offset: int) -> Paginated[MaintenanceIntervalRead]:
        items, total = await self.repo.list(limit=limit, offset=offset)
        return Paginated(items=items, total=total, limit=limit, offset=offset)

    async def create(self, item_in: MaintenanceIntervalCreate) -> MaintenanceIntervalRead:
        return await self.repo.create(item_in)

    async def get_by_id(self, item_id: UUID) -> MaintenanceIntervalRead:
        item = await self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance interval not found")
        return item