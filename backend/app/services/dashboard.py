from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.repositories import dashboard as repository


async def dashboard_summary(
    db: AsyncSession, user: User, *, section_id: UUID | None
) -> dict[str, Any]:
    if user.role == "master":
        if user.section_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Master user must be assigned to a section",
            )
        effective_section = user.section_id
    else:
        effective_section = section_id
    from datetime import date

    return await repository.dashboard_summary(
        db, section_id=effective_section, today=date.today()
    )
