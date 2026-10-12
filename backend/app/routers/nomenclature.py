from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.nomenclature import (
    NomenclatureCreate,
    NomenclatureNormCreate,
    NomenclatureNormRead,
    NomenclatureNormUpdate,
    NomenclatureRead,
    NomenclatureUpdate,
)
from app.services import nomenclature as service

router = APIRouter(tags=["nomenclature"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
NomenclatureWriter = Annotated[User, Depends(require_role("admin", "operator"))]
SortOrder = Literal["asc", "desc"]


@router.get("/nomenclature", response_model=PaginatedResponse[NomenclatureRead])
async def get_nomenclature(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    department_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
) -> PaginatedResponse[NomenclatureRead]:
    items, total = await service.list_nomenclature(
        db,
        department_id=department_id,
        q=q,
        master_only=current_user.role == "master",
        master_section_id=current_user.section_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[NomenclatureRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/nomenclature/{nomenclature_id}", response_model=NomenclatureRead
)
async def get_nomenclature_item(
    nomenclature_id: UUID, current_user: AuthenticatedUser, db: DatabaseSession
) -> NomenclatureRead:
    return await service.get_nomenclature(
        db,
        nomenclature_id,
        master_only=current_user.role == "master",
        master_section_id=current_user.section_id,
    )


@router.post(
    "/nomenclature",
    response_model=NomenclatureRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_nomenclature(
    payload: NomenclatureCreate, _: NomenclatureWriter, db: DatabaseSession
) -> NomenclatureRead:
    return await service.create_nomenclature(db, payload)


@router.patch(
    "/nomenclature/{nomenclature_id}", response_model=NomenclatureRead
)
async def patch_nomenclature(
    nomenclature_id: UUID,
    payload: NomenclatureUpdate,
    _: NomenclatureWriter,
    db: DatabaseSession,
) -> NomenclatureRead:
    return await service.update_nomenclature(db, nomenclature_id, payload)


@router.delete(
    "/nomenclature/{nomenclature_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_nomenclature(
    nomenclature_id: UUID, _: NomenclatureWriter, db: DatabaseSession
) -> Response:
    await service.delete_nomenclature(db, nomenclature_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/nomenclature-norms",
    response_model=PaginatedResponse[NomenclatureNormRead],
)
async def get_nomenclature_norms(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    department_id: UUID | None = None,
    work_type_id: UUID | None = None,
    nomenclature_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_order: SortOrder = Query(default="desc"),
) -> PaginatedResponse[NomenclatureNormRead]:
    items, total = await service.list_norms(
        db,
        department_id=department_id,
        work_type_id=work_type_id,
        nomenclature_id=nomenclature_id,
        master_only=current_user.role == "master",
        master_section_id=current_user.section_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[NomenclatureNormRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/nomenclature-norms/{norm_id}", response_model=NomenclatureNormRead
)
async def get_nomenclature_norm(
    norm_id: UUID, current_user: AuthenticatedUser, db: DatabaseSession
) -> NomenclatureNormRead:
    return await service.get_norm(
        db,
        norm_id,
        master_only=current_user.role == "master",
        master_section_id=current_user.section_id,
    )


@router.post(
    "/nomenclature-norms",
    response_model=NomenclatureNormRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_nomenclature_norm(
    payload: NomenclatureNormCreate,
    _: NomenclatureWriter,
    db: DatabaseSession,
) -> NomenclatureNormRead:
    return await service.create_norm(db, payload)


@router.patch(
    "/nomenclature-norms/{norm_id}", response_model=NomenclatureNormRead
)
async def patch_nomenclature_norm(
    norm_id: UUID,
    payload: NomenclatureNormUpdate,
    _: NomenclatureWriter,
    db: DatabaseSession,
) -> NomenclatureNormRead:
    return await service.update_norm(db, norm_id, payload)


@router.delete(
    "/nomenclature-norms/{norm_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_nomenclature_norm(
    norm_id: UUID, _: NomenclatureWriter, db: DatabaseSession
) -> Response:
    await service.delete_norm(db, norm_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
