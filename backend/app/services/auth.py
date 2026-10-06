import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
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
from app.models.identity import RefreshToken, User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.users import validate_email

LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)


class LoginAttemptLimiter:
    def __init__(self) -> None:
        self._failures: dict[tuple[str, str], Deque[datetime]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: tuple[str, str]) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - LOGIN_FAILURE_WINDOW
        async with self._lock:
            attempts = self._failures.get(key)
            if attempts is None:
                return
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                self._failures.pop(key, None)
                return
            if len(attempts) >= LOGIN_FAILURE_LIMIT:
                retry_after = max(
                    1, int((attempts[0] + LOGIN_FAILURE_WINDOW - now).total_seconds())
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed login attempts; try again later",
                    headers={"Retry-After": str(retry_after)},
                )

    async def record_failure(self, key: tuple[str, str]) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - LOGIN_FAILURE_WINDOW
        async with self._lock:
            stale_keys: list[tuple[str, str]] = []
            for attempt_key, attempts in self._failures.items():
                while attempts and attempts[0] <= cutoff:
                    attempts.popleft()
                if not attempts:
                    stale_keys.append(attempt_key)
            for stale_key in stale_keys:
                self._failures.pop(stale_key, None)
            self._failures.setdefault(key, deque()).append(now)

    async def clear(self, key: tuple[str, str]) -> None:
        async with self._lock:
            self._failures.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()


async def authenticate(
    db: AsyncSession,
    request: LoginRequest,
    client_ip: str,
) -> TokenResponse:
    key = (client_ip, request.email.strip().casefold())
    await login_attempt_limiter.check(key)

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
        await login_attempt_limiter.record_failure(key)
        raise unauthorized_exception()

    await login_attempt_limiter.clear(key)
    now = datetime.now(timezone.utc)
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
