from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import hash_password
from app.models.identity import RefreshToken, User
from app.repositories import references as references_repository
from app.repositories.users import USER_SORT_FIELDS, get_user, get_user_by_email, list_users
from app.schemas.users import (
    AdUserCreate,
    ConvertToAd,
    PasswordReset,
    UserCreate,
    UserUpdate,
)
from app.services.audit_log import add_auth_audit_event


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
    q: str | None = None,
    is_active: bool | None = None,
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
        q=q,
        is_active=is_active,
    )


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    if payload.role == "admin":
        raise HTTPException(status_code=403, detail="Admin accounts can only be created by the initial setup")
    if await get_user_by_email(db, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )
    if payload.section_id is not None and await references_repository.get_non_archived_section(
        db, payload.section_id
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot assign an archived or missing section to a user",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=await run_in_threadpool(hash_password, payload.password),
        auth_source="local",
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


async def create_ad_user(db: AsyncSession, payload: AdUserCreate) -> User:
    """Grant TOIR access to a directory account. No password is stored.

    The account is not looked up in the directory here (no service account is
    configured); its existence and objectGUID are confirmed at the first
    successful login.
    """
    if payload.role == "admin":
        raise HTTPException(status_code=403, detail="Admin accounts can only be created by the initial setup")
    email = f"{payload.ad_username}@{settings.ad_domain.lower()}"
    if await get_user_by_email(db, email) is not None or (
        await db.scalar(select(User.id).where(User.ad_username == payload.ad_username))
    ) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this login already exists",
        )
    if payload.section_id is not None and await references_repository.get_non_archived_section(
        db, payload.section_id
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot assign an archived or missing section to a user",
        )
    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=None,
        auth_source="ad",
        ad_username=payload.ad_username,
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
            detail="Could not create user; verify the login and section",
        ) from exc
    await db.refresh(user)
    return user


async def convert_user_to_ad(
    db: AsyncSession,
    user_id: UUID,
    payload: ConvertToAd,
    actor: User | None,
) -> User:
    """Explicit admin action: a local account becomes a directory account.

    The password hash is erased, sessions are revoked, the event is audited.
    ``actor`` is None only for the server-side CLI.
    """
    # Read before any rollback expires the actor instance (it may share this session).
    actor_id = actor.id if actor is not None else None
    actor_name = actor.full_name if actor is not None else "CLI"
    await db.execute(select(func.pg_advisory_xact_lock(782134992)))
    user = await get_user(db, user_id)
    if user is None:
        await db.rollback()
        raise _not_found()
    if actor_id is not None and user.id == actor_id:
        await db.rollback()
        raise HTTPException(status_code=409, detail="You cannot convert your own account")
    if user.auth_source == "ad":
        await db.rollback()
        raise HTTPException(status_code=409, detail="The account already uses Active Directory")
    taken = await db.scalar(
        select(User.id).where(User.ad_username == payload.ad_username, User.id != user.id)
    )
    if taken is not None:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This directory login is already assigned")

    user.auth_source = "ad"
    user.ad_username = payload.ad_username
    user.ad_object_guid = None
    user.hashed_password = None
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    add_auth_audit_event(
        db,
        action="other",
        actor_id=actor_id,
        actor_name=actor_name,
        route="/api/v1/users/convert-to-ad",
        status_code=200,
        auth_source="ad",
        extra={
            "event": "convert_to_ad",
            "target_user_id": str(user.id),
            "ad_username": payload.ad_username,
        },
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not convert user; the login is already assigned",
        ) from exc
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user_id: UUID,
    payload: UserUpdate,
    actor_id: UUID,
) -> User:
    await db.execute(select(func.pg_advisory_xact_lock(782134992)))
    user = await get_user(db, user_id)
    if user is None:
        raise _not_found()

    changes = payload.model_dump(exclude_unset=True)
    next_role = changes.get("role", user.role)
    if user.role != "admin" and next_role == "admin":
        await db.rollback()
        raise HTTPException(status_code=403, detail="Admin role assignment is protected")
    next_active = changes.get("is_active", user.is_active)
    if user.id == actor_id and not next_active:
        await db.rollback()
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
    if user.role == "admin" and (next_role != "admin" or not next_active):
        active_admins = await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
        )
        if active_admins.scalar_one() <= 1:
            await db.rollback()
            raise HTTPException(status_code=409, detail="The last active admin cannot be demoted or deactivated")
    if user.role == "admin" and next_role != "admin":
        await db.rollback()
        raise HTTPException(status_code=403, detail="The admin role is protected")
    next_section_id = changes.get("section_id", user.section_id)
    if next_role == "master" and next_section_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Master users must be assigned to a section",
        )
    if (
        next_section_id is not None
        and (
            next_section_id != user.section_id
            or (next_role == "master" and user.role != "master")
        )
        and await references_repository.get_non_archived_section(db, next_section_id) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot assign an archived or missing section to a user",
        )

    for field_name, value in changes.items():
        setattr(user, field_name, value)
    if user.is_active is False:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
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
    if user.auth_source != "local":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Directory accounts have no local password",
        )

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
