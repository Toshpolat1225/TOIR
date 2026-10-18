from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(require_permission("dashboard.view"))]


@router.get("/summary")
async def get_dashboard_summary(
    user: AuthenticatedUser,
    db: DatabaseSession,
    section_id: UUID | None = None,
) -> DashboardSummary:
    return await dashboard_summary(db, user, section_id=section_id)
