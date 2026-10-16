from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.repositories import tmc_documents as repository


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
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    return await repository.list_documents(
        db,
        section_id=_master_section(user),
        department_id=department_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
