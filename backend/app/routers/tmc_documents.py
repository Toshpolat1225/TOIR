from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.tmc_documents import TmcDocumentRead
from app.services import tmc_documents as service

router = APIRouter(prefix="/tmc-documents", tags=["TMC documents"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
DocumentStatus = Literal["draft", "issued", "closed"]


@router.get("", response_model=PaginatedResponse[TmcDocumentRead])
async def get_tmc_documents(
    user: AuthenticatedUser,
    db: DatabaseSession,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    department_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[TmcDocumentRead]:
    items, total = await service.list_documents(
        db,
        user,
        department_id=department_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items, total=total, limit=limit, offset=offset
    )
