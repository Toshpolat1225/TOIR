from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.asset_map import AssetMapRead
from app.services import asset_map as service

router = APIRouter(tags=["map"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
# The map sits next to Analytics and uses its permission (no new permission to seed).
MapViewer = Annotated[User, Depends(require_permission("analytics.view"))]


@router.get("/map/assets", response_model=AssetMapRead)
async def read_asset_map(
    user: MapViewer,
    db: DatabaseSession,
    asset_type: Annotated[str | None, Query(max_length=40)] = None,
    source: Annotated[Literal["wialon", "gtk", "train"] | None, Query()] = None,
    section_id: Annotated[UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> AssetMapRead:
    return await service.get_asset_map(db, user, asset_type=asset_type, source=source, section_id=section_id, q=q)
