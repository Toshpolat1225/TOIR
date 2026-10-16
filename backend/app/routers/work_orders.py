from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.work_orders import (
    NormCheckRequest,
    NormCheckResult,
    TemplateItemRead,
    WorkOrderCreate,
    WorkOrderRead,
    WorkOrderUpdate,
)
from app.services import work_orders as service
from app.services import ml as ml_service

router = APIRouter(prefix="/work-orders", tags=["work orders"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
WorkOrderCreator = Annotated[
    User, Depends(require_role("admin", "management", "operator", "master"))
]
WorkOrderWriter = Annotated[
    User, Depends(require_role("admin", "management", "operator", "master"))
]
WorkOrderDeleter = Annotated[User, Depends(require_role("admin", "management"))]
SortOrder = Literal["asc", "desc"]


@router.get("", response_model=PaginatedResponse[WorkOrderRead])
async def get_work_orders(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    status_filter: str | None = Query(default=None, alias="status", max_length=100),
    open_only: bool = Query(default=False, alias="open"),
    section_id: UUID | None = None,
    department_id: UUID | None = None,
    fixed_asset_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_order: SortOrder = Query(default="desc"),
) -> PaginatedResponse[WorkOrderRead]:
    items, total = await service.list_orders(
        db,
        current_user,
        status_filter=status_filter,
        open_only=open_only,
        section_id=section_id,
        department_id=department_id,
        fixed_asset_id=fixed_asset_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/norm-check", response_model=list[NormCheckResult])
async def post_norm_check(
    payload: NormCheckRequest, current_user: AuthenticatedUser, db: DatabaseSession
) -> list[NormCheckResult]:
    return await service.check_norms(db, current_user, payload)


@router.get("/template-items", response_model=list[TemplateItemRead])
async def get_template_items(
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    work_type_id: UUID,
    department_id: UUID,
) -> list[TemplateItemRead]:
    return [
        TemplateItemRead(**item)
        for item in await service.list_template_items(
            db, current_user, work_type_id, department_id
        )
    ]


@router.get("/{order_id}", response_model=WorkOrderRead)
async def get_work_order(
    order_id: UUID, current_user: AuthenticatedUser, db: DatabaseSession
) -> WorkOrderRead:
    return await service.get_order(db, current_user, order_id)


@router.post("", response_model=WorkOrderRead, status_code=status.HTTP_201_CREATED)
async def post_work_order(
    payload: WorkOrderCreate, current_user: WorkOrderCreator, db: DatabaseSession
) -> WorkOrderRead:
    return await service.create_order(db, current_user, payload)


@router.patch("/{order_id}", response_model=WorkOrderRead)
async def patch_work_order(
    order_id: UUID,
    payload: WorkOrderUpdate,
    current_user: WorkOrderWriter,
    db: DatabaseSession,
    background_tasks: BackgroundTasks,
) -> WorkOrderRead:
    result = await service.update_order(db, current_user, order_id, payload)
    if payload.status == "completed":
        background_tasks.add_task(ml_service.analyze_completed_order, order_id)
    return result


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_work_order(
    order_id: UUID, _: WorkOrderDeleter, db: DatabaseSession
) -> Response:
    await service.delete_order(db, order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
