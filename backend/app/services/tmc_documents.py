from typing import Any
from uuid import UUID
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.repositories import tmc_documents as repository
from app.repositories import work_orders as work_orders_repository


def _master_section(user: User) -> UUID | None:
    if user.role == "master":
        if user.section_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Master user must be assigned to a section",
            )
        return user.section_id
    return None


async def list_documents(
    db: AsyncSession,
    user: User,
    *,
    department_id: UUID | None,
    status_filter: str | None,
    work_order_id: UUID | None,
    limit: int,
    offset: int,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date_from must be before or equal to date_to")
    master_section_id = _master_section(user)
    if work_order_id is not None and master_section_id is not None:
        work_order = await work_orders_repository.get_order(
            db, work_order_id, master_section_id=master_section_id
        )
        if work_order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found")
    try:
        return await repository.list_documents(
            db,
            section_id=master_section_id,
            department_id=department_id,
            status_filter=status_filter,
            work_order_id=work_order_id,
            limit=limit,
            offset=offset,
            q=q,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported sort field") from exc
