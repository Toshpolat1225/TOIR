import hashlib
import logging
import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    unauthorized_exception,
)
from app.models.identity import LoginAttempt, RefreshToken, User
from app.services import ad_auth
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.audit_log import add_auth_audit_event, set_audit_actor

logger = logging.getLogger(__name__)

LOGIN_FAILURE_LIMIT = 5
# AD locks an account after 5 wrong passwords in 10 minutes; ours trips earlier.
AD_LOGIN_FAILURE_LIMIT = 3
# Per source IP over all directory logins (stops one host from guessing many accounts).
AD_IP_FAILURE_LIMIT = 20
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
EMERGENCY_SESSION_MINUTES = 15
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
    source = "ad"  # the directory is the only way in (AUTH-01): TOIR keeps no passwords of its own
    if user is not None and user.ad_username:
        ad_login = user.ad_username.lower()
    if ad_login is not None:
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
    if user is None:
        # No TOIR account: nothing is created and the directory is not asked
        # (TOIR must not become a password oracle for domain accounts).
        pass
    else:
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
            expires_at=next_refresh_expiry(
                created_at=stored_token.created_at, expires_at=stored_token.expires_at, now=now
            ),
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


def next_refresh_expiry(*, created_at: datetime, expires_at: datetime, now: datetime) -> datetime:
    """Expiry of the refresh token that replaces `expires_at`'s token.

    A normal session slides (a fresh full lifetime at every refresh). A short one, like an emergency session,
    keeps its original deadline: refreshing must never turn 15 minutes into 7 days.
    """
    normal = timedelta(days=settings.refresh_token_expire_days)
    if expires_at - created_at < normal / 2:
        return expires_at
    return now + normal


async def issue_emergency_session(
    db: AsyncSession,
    identifier: str,
    *,
    operator: str,
    now: datetime | None = None,
) -> str:
    """A 15-minute session for an ACTIVE directory administrator, started only from the server shell.

    Not an HTTP endpoint and not a password: it is for the case when the domain is down. Every use is written to
    the audit log with the operator; the token itself is never logged. Returns the refresh token.
    """
    now = now or datetime.now(timezone.utc)
    value = identifier.strip()
    user = (
        await db.execute(
            select(User).where(or_(User.email == value.lower(), User.ad_username == value.lower()))
        )
    ).scalar_one_or_none()
    if user is None or not user.is_active or user.role != "admin" or user.auth_source != "ad":
        raise ValueError("Emergency session is only for an active directory administrator")
    token = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(token),
            expires_at=now + timedelta(minutes=EMERGENCY_SESSION_MINUTES),
        )
    )
    add_auth_audit_event(
        db,
        action="login",
        actor_id=user.id,
        actor_name=user.full_name,
        route="cli:emergency-session",
        status_code=200,
        auth_source="ad",
        extra={"event": "emergency_session", "operator": operator, "ttl_minutes": EMERGENCY_SESSION_MINUTES},
    )
    await db.commit()
    return token


async def create_first_ad_admin(db: AsyncSession, email: str, ad_username: str, full_name: str) -> UUID:
    """The very first administrator of a fresh install: a directory account, no password. Only while no admin exists."""
    from app.schemas.users import validate_ad_username, validate_email

    normalized_email = validate_email(email)
    login = validate_ad_username(ad_username)
    name = full_name.strip()
    if not name:
        raise ValueError("Full name is required")
    if (await db.execute(select(User.id).where(User.role == "admin").limit(1))).scalar_one_or_none() is not None:
        raise ValueError("An admin user already exists")
    user = User(email=normalized_email, full_name=name, auth_source="ad", ad_username=login, role="admin", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id
