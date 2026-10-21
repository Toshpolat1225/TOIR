from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.identity import User
from app.schemas.wialon import WialonSyncResult, WialonSyncStatus
from app.services import wialon as service

router = APIRouter(prefix="/wialon", tags=["wialon pull"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_role("admin"))]


@router.post("/sync", response_model=WialonSyncResult)
async def post_wialon_sync(_: AdminUser, db: DatabaseSession) -> WialonSyncResult:
    return await service.sync_wialon_assets(db)


@router.get("/status", response_model=WialonSyncStatus)
async def get_wialon_sync_status(
    _: AdminUser, db: DatabaseSession
) -> WialonSyncStatus:
    return await service.get_sync_status(db)
