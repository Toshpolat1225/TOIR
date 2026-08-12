from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from ..repositories.employee import EmployeeRepository
from ..schemas.employee import EmployeeRead, EmployeeCreate, EmployeeUpdate
from ..schemas.pagination import Paginated


class EmployeeService:
    def __init__(self, db: AsyncSession):
        self.repo = EmployeeRepository(db)

    async def get_all_employees(self, limit: int, offset: int) -> Paginated[EmployeeRead]:
        employees, total = await self.repo.list(limit=limit, offset=offset)
        return Paginated(items=employees, total=total, limit=limit, offset=offset)

    async def create_employee(self, employee_in: EmployeeCreate) -> EmployeeRead:
        return await self.repo.create(employee_in)

    async def get_employee_by_id(self, employee_id: UUID) -> EmployeeRead:
        employee = await self.repo.get_by_id(employee_id)
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        return employee

    async def update_employee(self, employee_id: UUID, employee_in: EmployeeUpdate) -> EmployeeRead:
        await self.get_employee_by_id(employee_id)  # Ensure employee exists
        return await self.repo.update(employee_id, employee_in)

    async def delete_employee(self, employee_id: UUID):
        await self.get_employee_by_id(employee_id) # Ensure employee exists
        return await self.repo.delete(employee_id)