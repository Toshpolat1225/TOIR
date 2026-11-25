from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.repair_norms import RepairNormItemCreate, RepairNormItemRead, RepairNormItemUpdate, RepairNormSetRead
from app.services import repair_norms as service

router = APIRouter(prefix="/repair-norms", tags=["repair norms"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission("inventory.view"))]
Creator = Annotated[User, Depends(require_permission("inventory.create"))]
Updater = Annotated[User, Depends(require_permission("inventory.update"))]
Deleter = Annotated[User, Depends(require_permission("inventory.delete"))]


@router.get("/sets", response_model=list[RepairNormSetRead])
async def list_sets(_: Viewer, db: DatabaseSession) -> list[dict]:
    return await service.list_sets(db)


@router.get("/items", response_model=PaginatedResponse[RepairNormItemRead])
async def list_items(
    _: Viewer,
    db: DatabaseSession,
    work_type_id: UUID,
    asset_type: Annotated[str, Query(min_length=1, max_length=40)],
    asset_model_id: UUID | None = None,
    norm_group: Annotated[str, Query(max_length=200)] = "",
    q: Annotated[str | None, Query(max_length=100)] = None,
    section: Literal["materials", "spare_parts", "lubricants"] | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[RepairNormItemRead]:
    items, total = await service.list_items(db, work_type_id, asset_type, asset_model_id, norm_group=norm_group, q=q, section=section, limit=limit, offset=offset)
    return PaginatedResponse(items=[RepairNormItemRead.model_validate(i, from_attributes=True) for i in items], total=total, limit=limit, offset=offset)


@router.post("/items", response_model=RepairNormItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(payload: RepairNormItemCreate, user: Creator, db: DatabaseSession) -> RepairNormItemRead:
    return RepairNormItemRead.model_validate(await service.create_item(db, payload, user), from_attributes=True)


@router.patch("/items/{item_id}", response_model=RepairNormItemRead)
async def update_item(item_id: UUID, payload: RepairNormItemUpdate, user: Updater, db: DatabaseSession) -> RepairNormItemRead:
    return RepairNormItemRead.model_validate(await service.update_item(db, item_id, payload, user), from_attributes=True)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, user: Deleter, db: DatabaseSession) -> Response:
    await service.delete_item(db, item_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sets", status_code=status.HTTP_204_NO_CONTENT)
async def delete_set(
    user: Deleter,
    db: DatabaseSession,
    work_type_id: UUID,
    asset_type: Annotated[str, Query(min_length=1, max_length=40)],
    asset_model_id: UUID | None = None,
    norm_group: Annotated[str, Query(max_length=200)] = "",
) -> Response:
    await service.delete_set(db, work_type_id, asset_type, asset_model_id, user, norm_group)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
