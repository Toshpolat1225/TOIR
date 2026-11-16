import hashlib
import logging
import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
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
from app.services import ad_auth
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.users import validate_email
from app.services.audit_log import add_auth_audit_event, set_audit_actor

logger = logging.getLogger(__name__)

LOGIN_FAILURE_LIMIT = 5
# AD locks an account after 5 wrong passwords in 10 minutes; ours trips earlier.
AD_LOGIN_FAILURE_LIMIT = 3
# Per source IP over all directory logins (stops one host from guessing many accounts).
AD_IP_FAILURE_LIMIT = 20
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
MAX_LOCAL_PASSWORD_BYTES = 72
REFRESH_REUSE_GRACE = timedelta(seconds=30)


def ad_login_name(identifier: str) -> str | None:
    """The directory login for this identifier, or None for a local-only account."""
    if not settings.ad_auth_enabled:
        return None
    value = identifier.strip()
    if "@" in value:
        local, _, domain = value.rpartition("@")
        if domain.lower() != settings.ad_domain.lower():
            return None
        value = local
    return value.lower() if ad_auth.is_valid_login(value) else None


async def _find_login_user(
    db: AsyncSession, identifier: str, ad_login: str | None
) -> User | None:
    if ad_login is not None:
        user = await db.scalar(
            select(User).where(User.auth_source == "ad", User.ad_username == ad_login)
        )
        if user is not None:
            return user
    return await db.scalar(select(User).where(User.email == identifier.strip()))


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
    ad_login = ad_login_name(request.email)
    user = await _find_login_user(db, request.email, ad_login)
    # The backend that checks the password is decided by the account's stored
    # auth_source, never by the shape of the typed login.
    if user is not None:
        source = user.auth_source
        ad_login = user.ad_username.lower() if user.ad_username else ad_login
    else:
        source = "ad" if ad_login is not None else "local"
    if source == "ad" and ad_login is not None:
        # One counter per directory account (not per IP) so that we stay below
        # AD's own lock threshold.
        key_hash = login_attempt_key_hash("ad-account", ad_login)
        failure_limit = AD_LOGIN_FAILURE_LIMIT
        ip_key_hash = login_attempt_key_hash(client_ip, "\0ad-ip")
    else:
        key_hash = login_attempt_key_hash(client_ip, request.email)
        failure_limit = LOGIN_FAILURE_LIMIT
        ip_key_hash = None
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
    ip_attempts: list[LoginAttempt] = []
    if ip_key_hash is not None:
        ip_attempts = list(
            (
                await db.execute(
                    select(LoginAttempt)
                    .where(LoginAttempt.key_hash == ip_key_hash)
                    .order_by(LoginAttempt.failed_at.asc(), LoginAttempt.id.asc())
                )
            ).scalars()
        )
    if len(attempts) >= failure_limit or len(ip_attempts) >= AD_IP_FAILURE_LIMIT:
        window_start = (
            attempts[0].failed_at
            if len(attempts) >= failure_limit
            else ip_attempts[0].failed_at
        )
        add_auth_audit_event(
            db,
            action="login",
            actor_id=None,
            actor_name=request.email.strip(),
            route="/api/v1/auth/login",
            status_code=429,
            auth_source=source,
        )
        await db.commit()
        _raise_login_rate_limit(now, window_start)

    password_is_valid = False
    pending_guid: UUID | None = None
    local_ok_to_check = len(request.password.encode("utf-8")) <= MAX_LOCAL_PASSWORD_BYTES
    if user is None:
        # No TOIR account: nothing is created and the directory is not asked
        # (TOIR must not become a password oracle for domain accounts).
        if local_ok_to_check:
            await run_in_threadpool(verify_unknown_user_password, request.password)
    elif user.auth_source == "ad":
        if not settings.ad_auth_enabled or not user.ad_username:
            logger.warning("Directory login refused for %s: AD login is disabled", user.id)
        else:
            try:
                identity = await run_in_threadpool(
                    ad_auth.verify_password, user.ad_username, request.password
                )
                password_is_valid = True
            except ad_auth.AdRejected as rejected:
                # The AD code (52e wrong password, 775 locked, 533 disabled ...) goes to
                # the log for the administrator only; the user always sees one message.
                logger.info(
                    "AD login rejected for %s (ad code %s)",
                    user.ad_username,
                    rejected.ad_code or "-",
                )
            except ad_auth.AdUnavailable:
                add_auth_audit_event(
                    db,
                    action="login",
                    actor_id=None,
                    actor_name=request.email.strip(),
                    route="/api/v1/auth/login",
                    status_code=503,
                    auth_source="ad",
                )
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Directory service is unavailable; try again later",
                )
            if password_is_valid:
                # The directory account is bound to its objectGUID at the first
                # successful login; a different GUID later means the login now
                # belongs to another person.
                guid = UUID(identity.guid)
                if user.ad_object_guid is not None and user.ad_object_guid != guid:
                    logger.warning("AD objectGUID mismatch for TOIR user %s", user.id)
                    password_is_valid = False
                elif user.ad_object_guid is None:
                    owner = await db.scalar(
                        select(User.id).where(User.ad_object_guid == guid, User.id != user.id)
                    )
                    if owner is not None:
                        logger.warning("AD objectGUID of TOIR user %s is bound elsewhere", user.id)
                        password_is_valid = False
                    else:
                        pending_guid = guid
    elif local_ok_to_check and user.hashed_password:
        password_is_valid = await run_in_threadpool(
            verify_password, request.password, user.hashed_password
        )
    if user is None or not password_is_valid or not user.is_active:
        db.add(LoginAttempt(key_hash=key_hash, failed_at=now))
        if ip_key_hash is not None:
            db.add(LoginAttempt(key_hash=ip_key_hash, failed_at=now))
        add_auth_audit_event(
            db,
            action="login",
            actor_id=None,
            actor_name=request.email.strip(),
            route="/api/v1/auth/login",
            status_code=401,
            auth_source=source,
        )
        await db.commit()
        raise unauthorized_exception()

    await db.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == key_hash))
    set_audit_actor(
        db,
        actor_id=user.id,
        actor_name=user.full_name,
        actor_type="user",
        route="/api/v1/auth/login",
    )
    add_auth_audit_event(
        db,
        action="login",
        actor_id=user.id,
        actor_name=user.full_name,
        route="/api/v1/auth/login",
        status_code=200,
        auth_source=user.auth_source,
    )
    if pending_guid is not None:
        user.ad_object_guid = pending_guid
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
        stored_token is not None
        and stored_token.revoked_at is not None
        and stored_token.expires_at > now
        and now - stored_token.revoked_at > REFRESH_REUSE_GRACE
    ):
        # A token that was already rotated or revoked comes back long after the fact: it was copied. Cut every
        # session of that user (they sign in again) and leave a trace. Two tabs refreshing at the same moment
        # present the same token within seconds: that is the grace period and is only refused.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored_token.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        add_auth_audit_event(
            db,
            action="other",
            actor_id=stored_token.user_id,
            actor_name=None,
            route="/api/v1/auth/refresh",
            status_code=401,
            extra={"event": "refresh_token_reuse"},
        )
        await db.commit()
        raise unauthorized_exception()
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

    set_audit_actor(
        db,
        actor_id=user.id,
        actor_name=user.full_name,
        actor_type="user",
        route="/api/v1/auth/refresh",
    )
    add_auth_audit_event(
        db,
        action="login",
        actor_id=user.id,
        actor_name=user.full_name,
        route="/api/v1/auth/refresh",
        status_code=200,
    )
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
        user_result = await db.execute(select(User).where(User.id == stored_token.user_id))
        user = user_result.scalar_one_or_none()
        actor_name = user.full_name if user is not None else None
        set_audit_actor(
            db,
            actor_id=stored_token.user_id,
            actor_name=actor_name,
            actor_type="user",
            route="/api/v1/auth/logout",
        )
        add_auth_audit_event(
            db,
            action="logout",
            actor_id=stored_token.user_id,
            actor_name=actor_name,
            route="/api/v1/auth/logout",
            status_code=204,
        )
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
