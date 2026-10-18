from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.users import PasswordReset, UserCreate, UserRead, UserUpdate
from app.services.users import (
    create_user,
    list_users_page,
    reset_user_password,
    update_user,
)

router = APIRouter(prefix="/users", tags=["users"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_permission("users.manage_users"))]


@router.get("", response_model=PaginatedResponse[UserRead])
async def get_users(
    _: AdminUser,
    db: DatabaseSession,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = "desc",
) -> PaginatedResponse[UserRead]:
    users, total = await list_users_page(
        db,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[UserRead](
        items=users,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_user(
    payload: UserCreate,
    _: AdminUser,
    db: DatabaseSession,
) -> User:
    return await create_user(db, payload)


@router.patch("/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: UUID,
    payload: UserUpdate,
    _: AdminUser,
    db: DatabaseSession,
) -> User:
    return await update_user(db, user_id, payload)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def post_password_reset(
    user_id: UUID,
    payload: PasswordReset,
    _: AdminUser,
    db: DatabaseSession,
) -> Response:
    await reset_user_password(db, user_id, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
