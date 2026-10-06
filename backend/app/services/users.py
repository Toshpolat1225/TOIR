from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import hash_password
from app.models.identity import RefreshToken, User
from app.repositories.users import USER_SORT_FIELDS, get_user, get_user_by_email, list_users
from app.schemas.users import PasswordReset, UserCreate, UserUpdate


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found",
    )


async def list_users_page(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[User], int]:
    if sort_by not in USER_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported sort field",
        )
    return await list_users(
        db,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        descending=sort_order == "desc",
    )


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    if await get_user_by_email(db, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=await run_in_threadpool(hash_password, payload.password),
        role=payload.role,
        section_id=payload.section_id,
        is_active=payload.is_active,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create user; verify the email and section",
        ) from exc
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user_id: UUID,
    payload: UserUpdate,
) -> User:
    user = await get_user(db, user_id)
    if user is None:
        raise _not_found()

    changes = payload.model_dump(exclude_unset=True)
    next_role = changes.get("role", user.role)
    next_section_id = changes.get("section_id", user.section_id)
    if next_role == "master" and next_section_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Master users must be assigned to a section",
        )

    for field_name, value in changes.items():
        setattr(user, field_name, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not update user; verify the assigned section",
        ) from exc
    await db.refresh(user)
    return user


async def reset_user_password(
    db: AsyncSession,
    user_id: UUID,
    payload: PasswordReset,
) -> None:
    user = await get_user(db, user_id)
    if user is None:
        raise _not_found()

    user.hashed_password = await run_in_threadpool(hash_password, payload.password)
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
