from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.asset_matching import UnmatchedSourceObjectRead
from app.schemas.common import PaginatedResponse
from app.services import asset_matching as service

router = APIRouter(prefix="/asset-links", tags=["asset links"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AssetLinkViewer = Annotated[User, Depends(require_permission("asset_links.view"))]


@router.get(
    "/unmatched",
    response_model=PaginatedResponse[UnmatchedSourceObjectRead],
)
async def list_unmatched_source_objects(
    _: AssetLinkViewer,
    db: DatabaseSession,
    source: Literal["gtk", "wialon"],
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[UnmatchedSourceObjectRead]:
    items, total = await service.list_unmatched(
        db, source=source, limit=limit, offset=offset
    )
    return PaginatedResponse[UnmatchedSourceObjectRead](
        items=items, total=total, limit=limit, offset=offset
    )
