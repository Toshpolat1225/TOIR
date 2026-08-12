from datetime import date
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from ..repositories.work_order import WorkOrderRepository
from ..repositories.fixed_asset import FixedAssetRepository
from ..schemas.work_order import WorkOrderRead, WorkOrderCreate, WorkOrderUpdate
from ..schemas.pagination import Paginated


class WorkOrderService:
    def __init__(self, db: AsyncSession):
        self.repo = WorkOrderRepository(db)
        self.asset_repo = FixedAssetRepository(db)

    async def get_all_work_orders(
        self, limit: int, offset: int, status: str | None = None, section_id: UUID | None = None
    ) -> Paginated[WorkOrderRead]:
        filters = {}
        if status:
            filters["status"] = status
        if section_id:
            filters["section_id"] = section_id
        
        work_orders, total = await self.repo.list(limit=limit, offset=offset, **filters)
        return Paginated(items=work_orders, total=total, limit=limit, offset=offset)

    async def create_work_order(self, wo_in: WorkOrderCreate) -> WorkOrderRead:
        # Validate that the fixed asset exists
        if wo_in.fixed_asset_id:
            asset = await self.asset_repo.get_by_id(wo_in.fixed_asset_id)
            if not asset:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Fixed asset with id {wo_in.fixed_asset_id} not found",
                )
        return await self.repo.create(wo_in)

    async def get_work_order_by_id(self, wo_id: str) -> WorkOrderRead:
        work_order = await self.repo.get_by_id(wo_id)
        if not work_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found")
        return work_order