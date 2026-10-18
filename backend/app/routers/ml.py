from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.ml import MlAnalyzeResponse, MlInsightRead
from app.services import ml as service

router = APIRouter(prefix="/ml", tags=["machine learning"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_permission("ml.create"))]
InsightType = Literal["anomaly", "prediction", "efficiency"]
InsightSeverity = Literal["low", "medium", "high", "critical"]


@router.post("/analyze", response_model=MlAnalyzeResponse)
async def post_analyze(_: AdminUser, db: DatabaseSession) -> MlAnalyzeResponse:
    return await service.analyze_fleet(db)


@router.get("/insights", response_model=PaginatedResponse[MlInsightRead])
async def get_insights(
    user: Annotated[User, Depends(require_permission("ml.view"))],
    db: DatabaseSession,
    asset_id: UUID | None = None,
    insight_type: InsightType | None = None,
    severity: InsightSeverity | None = None,
    is_resolved: bool | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[MlInsightRead]:
    items, total = await service.list_insights(
        db,
        user,
        asset_id=asset_id,
        insight_type=insight_type,
        severity=severity,
        is_resolved=is_resolved,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)
