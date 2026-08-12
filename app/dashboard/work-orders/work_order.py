from datetime import date
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status

from ..repositories.work_order import WorkOrderRepository
from ..repositories.fixed_asset import FixedAssetRepository
from ..repositories.section import SectionRepository
from ..repositories.department import DepartmentRepository
from ..repositories.employee import EmployeeRepository
from ..repositories.work_type import WorkTypeRepository
from ..schemas.work_order import WorkOrderRead, WorkOrderCreate, WorkOrderUpdate
from ..schemas.pagination import Paginated
from ..database import get_db


class WorkOrderService:
    def __init__(self, db: AsyncSession):
        self.repo = WorkOrderRepository(db)
        self.asset_repo = FixedAssetRepository(db)
        self.section_repo = SectionRepository(db)
        self.department_repo = DepartmentRepository(db)
        self.employee_repo = EmployeeRepository(db)
        self.work_type_repo = WorkTypeRepository(db)

    async def get_all_work_orders(
        self,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
        status: str | None = None,
        section_id: UUID | None = None,
        department_id: UUID | None = None,
        fixed_asset_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
    ) -> Paginated[WorkOrderRead]:
        filters = {}
        if status:
            filters["status"] = status
        if section_id:
            filters["section_id"] = section_id
        if department_id:
            filters["department_id"] = department_id
        if fixed_asset_id:
            filters["fixed_asset_id"] = fixed_asset_id

        work_orders, total = await self.repo.list_with_filters(
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            date_from=date_from,
            date_to=date_to,
            search_query=q,
            **filters,
        )
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
        if wo_in.section_id:
            section = await self.section_repo.get_by_id(wo_in.section_id)
            if not section:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        if wo_in.department_id:
            department = await self.department_repo.get_by_id(wo_in.department_id)
            if not department:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        if wo_in.employee_id:
            employee = await self.employee_repo.get_by_id(wo_in.employee_id)
            if not employee:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        if wo_in.work_type_id:
            work_type = await self.work_type_repo.get_by_id(wo_in.work_type_id)
            if not work_type:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work type not found")

        return await self.repo.create(wo_in)

    async def get_work_order_by_id(self, wo_id: str) -> WorkOrderRead:
        work_order = await self.repo.get_by_id_with_related(wo_id)
        if not work_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found"
            )
        return work_order

    async def update_work_order(
        self, wo_id: str, wo_in: WorkOrderUpdate
    ) -> WorkOrderRead:
        existing_wo = await self.get_work_order_by_id(wo_id)

        # Status transition validation
        if wo_in.status and existing_wo.status != wo_in.status:
            allowed_transitions = {
                "draft": ["planned"],
                "planned": ["in_progress", "cancelled"],
                "in_progress": ["completed", "cancelled"],
                "completed": [],
                "cancelled": [],
            }
            if wo_in.status not in allowed_transitions.get(existing_wo.status, []):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid status transition from '{existing_wo.status}' to '{wo_in.status}'",
                )

        return await self.repo.update(wo_id, wo_in)


def get_work_order_service(db: AsyncSession = Depends(get_db)) -> WorkOrderService:
    return WorkOrderService(db)