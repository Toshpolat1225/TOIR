"""Spare-part analytics endpoints (ТМЦ cards of the AI-analytics page). Included BEFORE the generic /analytics/{block} router."""
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.services import parts_analytics as service

router = APIRouter(prefix="/analytics", tags=["parts analytics"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission("analytics.view"))]


@router.get("/repair-forecast", response_model=dict[str, Any])
async def repair_forecast(
    user: Viewer,
    db: DatabaseSession,
    horizon: Literal["quarter", "half", "year"] = "quarter",
    section_id: UUID | None = None,
    include_cycles: bool = True,
) -> dict[str, Any]:
    return await service.repair_forecast(db, user, horizon=horizon, section_id=section_id, include_cycles=include_cycles)


@router.get("/parts-demand", response_model=dict[str, Any])
async def parts_demand(
    user: Viewer,
    db: DatabaseSession,
    horizon: Literal["quarter", "half", "year", "all"] = "all",
    section_id: UUID | None = None,
    include_cycles: bool = True,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await service.parts_demand(db, user, horizon=horizon, section_id=section_id, include_cycles=include_cycles, limit=limit, offset=offset)


@router.get("/parts-consumption", response_model=dict[str, Any])
async def parts_consumption(
    user: Viewer,
    db: DatabaseSession,
    months: int = Query(default=8, ge=1, le=36),
    section_id: UUID | None = None,
    limit: int = Query(default=30, ge=1, le=200),
) -> dict[str, Any]:
    return await service.parts_consumption(db, user, months=months, section_id=section_id, limit=limit)


@router.get("/stock-risk", response_model=dict[str, Any])
async def stock_risk(
    user: Viewer,
    db: DatabaseSession,
    section_id: UUID | None = None,
    status: Literal["critical", "order_now", "ok", "no_data"] | None = None,
    sort_by: str = Query(default="status", max_length=40),
    sort_dir: Literal["asc", "desc"] = "asc",
    include_cycles: bool = True,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await service.stock_risk(db, user, section_id=section_id, status=status, sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset, include_cycles=include_cycles)
