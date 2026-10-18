from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.tmc_documents import TmcDocumentRead
from app.services import tmc_documents as service

router = APIRouter(prefix="/tmc-documents", tags=["TMC documents"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(require_permission("tmc.view"))]
DocumentStatus = Literal["draft", "issued", "closed"]


@router.get("", response_model=PaginatedResponse[TmcDocumentRead])
async def get_tmc_documents(
    user: AuthenticatedUser,
    db: DatabaseSession,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    department_id: UUID | None = None,
    work_order_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: Literal["doc_no", "doc_date", "status", "created_at", "updated_at"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[TmcDocumentRead]:
    items, total = await service.list_documents(
        db,
        user,
        department_id=department_id,
        status_filter=status_filter,
        work_order_id=work_order_id,
        limit=limit,
        offset=offset,
        q=q,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(
        items=items, total=total, limit=limit, offset=offset
    )
