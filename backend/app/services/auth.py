import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    unauthorized_exception,
    verify_password,
    verify_unknown_user_password,
)
from app.models.identity import LoginAttempt, RefreshToken, User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.users import validate_email

LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)


def login_attempt_key_hash(client_ip: str, email: str) -> str:
    normalized_email = email.strip().casefold()
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode("utf-8"),
        f"{client_ip}\0{normalized_email}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _raise_login_rate_limit(now: datetime, window_started_at: datetime) -> None:
    retry_after = max(
        1,
        int((window_started_at + LOGIN_FAILURE_WINDOW - now).total_seconds()),
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed login attempts; try again later",
        headers={"Retry-After": str(retry_after)},
    )


async def authenticate(
    db: AsyncSession,
    request: LoginRequest,
    client_ip: str,
) -> TokenResponse:
    key_hash = login_attempt_key_hash(client_ip, request.email)
    now = datetime.now(timezone.utc)
    cutoff = now - LOGIN_FAILURE_WINDOW
    await db.execute(delete(LoginAttempt).where(LoginAttempt.failed_at <= cutoff))
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(key_hash, 0)))
    )
    attempt_result = await db.execute(
        select(LoginAttempt)
        .where(LoginAttempt.key_hash == key_hash)
        .order_by(LoginAttempt.failed_at.asc(), LoginAttempt.id.asc())
        .with_for_update()
    )
    attempts = list(attempt_result.scalars())
    if len(attempts) >= LOGIN_FAILURE_LIMIT:
        _raise_login_rate_limit(now, attempts[0].failed_at)

    result = await db.execute(select(User).where(User.email == request.email.strip()))
    user = result.scalar_one_or_none()
    password_is_valid = False
    if user is not None:
        password_is_valid = await run_in_threadpool(
            verify_password, request.password, user.hashed_password
        )

    if user is None:
        await run_in_threadpool(verify_unknown_user_password, request.password)
    if user is None or not password_is_valid or not user.is_active:
        db.add(LoginAttempt(key_hash=key_hash, failed_at=now))
        await db.commit()
        raise unauthorized_exception()

    await db.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == key_hash))
    refresh_token = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    user.last_login_at = now
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def rotate_refresh_token(
    db: AsyncSession,
    presented_token: str,
) -> TokenResponse:
    token_hash = hash_refresh_token(presented_token)
    result = await db.execute(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    stored_token = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if (
        stored_token is None
        or stored_token.revoked_at is not None
        or stored_token.expires_at <= now
    ):
        raise unauthorized_exception()

    user_result = await db.execute(
        select(User).where(User.id == stored_token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        stored_token.revoked_at = now
        await db.commit()
        raise unauthorized_exception()

    next_refresh_token = create_refresh_token()
    stored_token.revoked_at = now
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(next_refresh_token),
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=next_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def revoke_refresh_token(db: AsyncSession, presented_token: str) -> None:
    token_hash = hash_refresh_token(presented_token)
    result = await db.execute(
        select(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .with_for_update()
    )
    stored_token = result.scalar_one_or_none()
    if stored_token is not None:
        stored_token.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def create_initial_admin(
    db: AsyncSession,
    email: str,
    full_name: str,
    password: str,
) -> UUID:
    normalized_email = validate_email(email)
    normalized_name = full_name.strip()
    if not normalized_name:
        raise ValueError("Full name is required")
    existing_user = await db.execute(select(User.id).where(User.email == normalized_email))
    if existing_user.scalar_one_or_none() is not None:
        raise ValueError("A user with this email already exists")
    existing_admin = await db.execute(select(User.id).where(User.role == "admin").limit(1))
    if existing_admin.scalar_one_or_none() is not None:
        raise ValueError("An admin user already exists")

    user = User(
        email=normalized_email,
        full_name=normalized_name,
        hashed_password=hash_password(password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id
