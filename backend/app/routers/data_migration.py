from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.data_migration import (
    DataMigrationBatchRead,
    DataMigrationItemRead,
    DataMigrationItemUpdate,
    DataMigrationRevertResult,
)
from app.services import data_migration as service

router = APIRouter(prefix="/data-migrations", tags=["data migration"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission("data_migration.view"))]
Manager = Annotated[User, Depends(require_permission("data_migration.manage"))]


@router.get("", response_model=list[DataMigrationBatchRead])
async def list_batches(_: Viewer, db: DatabaseSession) -> list[dict]:
    return await service.list_batches(db)


@router.get("/{batch_id}/items", response_model=PaginatedResponse[DataMigrationItemRead])
async def list_items(
    _: Viewer,
    db: DatabaseSession,
    batch_id: UUID,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[Literal["applied", "reverted"] | None, Query(alias="status")] = None,
    sort_by: str = "inv_number",
    sort_dir: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[DataMigrationItemRead]:
    items, total = await service.list_items(
        db, batch_id, q=q, status_filter=status_filter, sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset
    )
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.patch("/items/{item_id}", response_model=DataMigrationItemRead)
async def update_item(item_id: int, payload: DataMigrationItemUpdate, user: Manager, db: DatabaseSession) -> dict:
    return await service.update_item(db, item_id, payload.new_value, user)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revert_item(item_id: int, user: Manager, db: DatabaseSession) -> Response:
    """«Delete» = roll the value back to what it was before the migration (the journal row stays as «reverted»)."""
    await service.revert_item(db, item_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{batch_id}/revert", response_model=DataMigrationRevertResult)
async def revert_batch(batch_id: UUID, user: Manager, db: DatabaseSession) -> dict:
    return await service.revert_batch(db, batch_id, user)
