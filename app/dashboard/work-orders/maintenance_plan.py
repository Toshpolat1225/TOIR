from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from ..repositories.maintenance_plan import MaintenancePlanRepository
from ..schemas.maintenance_plan import MaintenancePlanRead, MaintenancePlanCreate, MaintenancePlanUpdate
from ..schemas.pagination import Paginated


class MaintenancePlanService:
    def __init__(self, db: AsyncSession):
        self.repo = MaintenancePlanRepository(db)

    async def get_all(self, limit: int, offset: int) -> Paginated[MaintenancePlanRead]:
        items, total = await self.repo.list(limit=limit, offset=offset)
        return Paginated(items=items, total=total, limit=limit, offset=offset)

    async def create(self, item_in: MaintenancePlanCreate) -> MaintenancePlanRead:
        return await self.repo.create(item_in)

    async def get_by_id(self, item_id: UUID) -> MaintenancePlanRead:
        item = await self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance plan item not found")
        return item