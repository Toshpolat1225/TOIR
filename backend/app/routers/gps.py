from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.gps import GpsAssetDetail, GpsOverview
from app.services import gps_overview as service

router = APIRouter(tags=["gps"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
# Next to the map, under Analytics: the same permission (nothing new to seed).
GpsViewer = Annotated[User, Depends(require_permission("analytics.view"))]


@router.get("/gps/overview", response_model=GpsOverview)
async def read_gps_overview(
    user: GpsViewer,
    db: DatabaseSession,
    days: Annotated[int, Query(ge=1, le=31)] = 7,
    q: Annotated[str | None, Query(max_length=100)] = None,
    section_id: Annotated[UUID | None, Query()] = None,
    verdict: Annotated[
        Literal[
            "confirmed", "diverged", "gtk_stale", "wialon_stale", "both_stale_agree", "both_stale_apart", "wialon_only", "gtk_only", "no_position",
        ] | None,
        Query(),
    ] = None,
    only_issues: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GpsOverview:
    """Every locomotive with the Wialon and the GTK tracker side by side: position verdict, daily distances, week totals (master: own section only)."""
    return await service.get_overview(db, user, days=days, q=q, section_id=section_id, verdict=verdict, only_issues=only_issues, limit=limit, offset=offset)


@router.get("/gps/assets/{asset_id}", response_model=GpsAssetDetail)
async def read_gps_asset(
    asset_id: UUID,
    user: GpsViewer,
    db: DatabaseSession,
    days: Annotated[int, Query(ge=1, le=31)] = 7,
    track_days: Annotated[int, Query(ge=1, le=14)] = 2,
) -> GpsAssetDetail:
    """One locomotive: both live fixes, the day-by-day table of both trackers and both stored tracks (a stranger's section: 404)."""
    return await service.get_asset_detail(db, user, asset_id, days=days, track_days=track_days)
