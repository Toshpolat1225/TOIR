from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.repositories import conflict_views
from app.schemas.asset_field_changes import (
    AssetConflictRow,
    AssetFieldChangeRead,
    WialonCounterBlockList,
    WialonCounterBlockRead,
)
from app.schemas.common import PaginatedResponse
from app.services import asset_field_changes as service

router = APIRouter(prefix="/asset-conflicts", tags=["asset conflicts"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
ConflictManager = Annotated[User, Depends(require_permission("asset_conflicts.manage"))]


@router.get("", response_model=PaginatedResponse[AssetConflictRow])
async def list_asset_conflicts(
    _: ConflictManager,
    db: DatabaseSession,
    status_filter: Annotated[
        Literal["pending", "applied", "accepted", "rejected"],
        Query(alias="status"),
    ] = "pending",
    source: Annotated[str | None, Query(max_length=32)] = None,
    field: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AssetConflictRow]:
    rows, total = await conflict_views.list_field_conflicts(
        db,
        status=status_filter,
        source=source,
        field=field,
        q=q,
        limit=limit,
        offset=offset,
    )
    items = [
        AssetConflictRow(
            **AssetFieldChangeRead.model_validate(change).model_dump(),
            asset_inv_number=inv_number,
            asset_serial_number=serial_number,
            asset_type=asset_type,
        )
        for change, inv_number, serial_number, asset_type in rows
    ]
    return PaginatedResponse[AssetConflictRow](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/wialon-counters", response_model=WialonCounterBlockList)
async def list_wialon_counter_blocks(
    user: ConflictManager,
    db: DatabaseSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> WialonCounterBlockList:
    # A master sees only the locomotives of his own section (server-side).
    section_id = None
    if user.role == "master":
        if user.section_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Master user must be assigned to a section",
            )
        section_id = user.section_id
    rows, total, summary = await conflict_views.list_blocked_counters(
        db, q=q, section_id=section_id, limit=limit, offset=offset
    )
    return WialonCounterBlockList(
        items=[WialonCounterBlockRead(**row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        **summary,
    )


@router.post("/{change_id}/accept", response_model=AssetFieldChangeRead)
async def accept_asset_conflict(
    change_id: int,
    user: ConflictManager,
    db: DatabaseSession,
) -> AssetFieldChangeRead:
    return await service.accept_conflict(db, change_id, user.id)


@router.post("/{change_id}/reject", response_model=AssetFieldChangeRead)
async def reject_asset_conflict(
    change_id: int,
    user: ConflictManager,
    db: DatabaseSession,
) -> AssetFieldChangeRead:
    return await service.reject_conflict(db, change_id, user.id)
