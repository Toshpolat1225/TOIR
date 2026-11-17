from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.asset_history import AssetHistory
from app.schemas.asset_map import AssetMapRead, AssetUnplacedPage
from app.schemas.train_formation import LiveTrains
from app.services import asset_history as history_service
from app.services import train_formation
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


@router.get("/map/unplaced", response_model=AssetUnplacedPage)
async def read_unplaced_assets(
    user: MapViewer,
    db: DatabaseSession,
    reason: Annotated[
        Literal[
            "no_link", "no_position", "wialon_unit_missing", "wialon_no_fix", "gtk_locomotive_only", "gtk_carriage_missing", "gtk_no_coords",
            "train_no_gps",
        ] | None,
        Query(),
    ] = None,
    asset_type: Annotated[str | None, Query(max_length=40)] = None,
    section_id: Annotated[UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    only_linkable: Annotated[bool, Query()] = False,
    sort_by: Annotated[str, Query(max_length=20)] = "reason",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssetUnplacedPage:
    return await service.get_unplaced(
        db, user, reason=reason, asset_type=asset_type, section_id=section_id, q=q, only_linkable=only_linkable,
        sort_by=sort_by, descending=sort_dir == "desc", limit=limit, offset=offset,
    )


@router.get("/map/history", response_model=AssetHistory)
async def read_asset_history(
    user: MapViewer,
    db: DatabaseSession,
    asset_id: Annotated[UUID | None, Query()] = None,
    carriage_gtk_id: Annotated[int | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> AssetHistory:
    """Where a wagon or locomotive was, behind which traction unit, and what it was doing (master: own section only, 404 otherwise)."""
    return await history_service.asset_history(db, user, asset_id=asset_id, carriage_gtk_id=carriage_gtk_id, days=days)


@router.get("/map/trains", response_model=LiveTrains)
async def read_live_trains(user: MapViewer, db: DatabaseSession) -> LiveTrains:
    """Open GTK trains drawn to scale: every vehicle (locomotive, motor car, wagons in GTK order) with its centre, heading and size."""
    return await train_formation.live_trains(db, user)
