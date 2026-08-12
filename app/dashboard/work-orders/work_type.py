from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status

from ..repositories.work_type import WorkTypeRepository
from ..schemas.work_type import WorkTypeRead, WorkTypeCreate, WorkTypeUpdate
from ..schemas.pagination import Paginated
from ..database import get_db


class WorkTypeService:
    def __init__(self, db: AsyncSession):
        self.repo = WorkTypeRepository(db)

    async def get_all(
        self, limit: int, offset: int, unit_type: str | None = None
    ) -> Paginated[WorkTypeRead]:
        filters = {}
        if unit_type:
            filters["unit_type"] = unit_type
        items, total = await self.repo.list(
            limit=limit, offset=offset, sort_by="sort_order", **filters
        )
        return Paginated(items=items, total=total, limit=limit, offset=offset)

    async def create(self, item_in: WorkTypeCreate) -> WorkTypeRead:
        return await self.repo.create(item_in)

    async def get_by_id(self, item_id: UUID) -> WorkTypeRead:
        item = await self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Work type not found"
            )
        return item


def get_work_type_service(db: AsyncSession = Depends(get_db)) -> WorkTypeService:
    return WorkTypeService(db)