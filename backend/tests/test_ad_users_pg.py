"""Granting access to directory accounts, converting local accounts, API guards."""
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.identity import RefreshToken, User
from app.routers import users as users_router
from app.schemas.users import AdUserCreate, ConvertToAd, PasswordReset, UserCreate
from app.services import users as users_service


def _login() -> str:
    return f"adgrant-{uuid4().hex[:8]}"


async def _delete(*emails_or_logins: str) -> None:
    async with SessionFactory() as db:
        for value in emails_or_logins:
            ids = (
                await db.execute(
                    select(User.id).where(
                        (User.email == value) | (User.ad_username == value)
                    )
                )
            ).scalars().all()
            if ids:
                await db.execute(delete(RefreshToken).where(RefreshToken.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))
        await db.commit()


def test_ad_username_validation_rejects_ldap_special_characters_and_has_no_password():
    for bad in ("a*b", "a(b", "a)b", "a\\b", "a b", "", "x)(uid=*"):
        with pytest.raises(ValidationError):
            AdUserCreate(ad_username=bad, full_name="N", role="operator")
        with pytest.raises(ValidationError):
            ConvertToAd(ad_username=bad)
    ok = AdUserCreate(ad_username="T.Turakulov@agmk.uz", full_name=" N ", role="operator")
    assert ok.ad_username == "t.turakulov" and ok.full_name == "N"
    assert "password" not in AdUserCreate.model_fields
    with pytest.raises(ValidationError):
        AdUserCreate(ad_username="m1", full_name="N", role="master")


@pytest.mark.pg
@pytest.mark.asyncio
async def test_grant_creates_a_passwordless_directory_user_and_rejects_duplicates():
    login = _login()
    try:
        async with SessionFactory() as db:
            user = await users_service.create_ad_user(
                db, AdUserCreate(ad_username=login, full_name="Grant Test", role="operator")
            )
            assert user.auth_source == "ad"
            assert user.hashed_password is None
            assert user.ad_username == login
            assert user.ad_object_guid is None  # confirmed at the first login
            assert user.email == f"{login}@agmk.uz"
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as dup:
                await users_service.create_ad_user(
                    db,
                    AdUserCreate(ad_username=login.upper(), full_name="X", role="operator"),
                )
            assert dup.value.status_code == 409
            with pytest.raises(HTTPException) as admin:
                await users_service.create_ad_user(
                    db, AdUserCreate(ad_username=_login(), full_name="X", role="admin")
                )
            assert admin.value.status_code == 403
    finally:
        await _delete(login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_local_creation_stays_local_and_password_reset_is_refused_for_ad():
    local_email = f"{_login()}@example.com"
    ad_login = _login()
    try:
        async with SessionFactory() as db:
            local = await users_service.create_user(
                db,
                UserCreate(
                    email=local_email, full_name="L", password="LocalPass-123", role="operator"
                ),
            )
            assert local.auth_source == "local" and local.hashed_password
            ad_user = await users_service.create_ad_user(
                db, AdUserCreate(ad_username=ad_login, full_name="A", role="operator")
            )
            await users_service.reset_user_password(
                db, local.id, PasswordReset(password="Other-Pass-1")
            )
            with pytest.raises(HTTPException) as refused:
                await users_service.reset_user_password(
                    db, ad_user.id, PasswordReset(password="Other-Pass-1")
                )
            assert refused.value.status_code == 409
    finally:
        await _delete(local_email, ad_login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_convert_erases_the_hash_revokes_sessions_and_is_audited():
    email = f"{_login()}@example.com"
    ad_login = _login()
    try:
        async with SessionFactory() as db:
            actor = User(
                email=f"{_login()}@example.com",
                full_name="Actor",
                hashed_password=hash_password("x"),
                role="admin",
            )
            target = User(
                email=email,
                full_name="Target",
                hashed_password=hash_password("x"),
                role="operator",
            )
            db.add_all([actor, target])
            await db.flush()
            db.add(
                RefreshToken(
                    user_id=target.id,
                    token_hash=uuid4().hex,
                    expires_at=__import__("datetime").datetime(2099, 1, 1),
                )
            )
            await db.commit()
            actor_email, target_id, actor_id = actor.email, target.id, actor.id

            with pytest.raises(HTTPException) as self_convert:
                await users_service.convert_user_to_ad(
                    db, actor_id, ConvertToAd(ad_username=_login()), actor
                )
            assert self_convert.value.status_code == 409
            await db.refresh(actor)  # the rollback above expired it

            converted = await users_service.convert_user_to_ad(
                db, target_id, ConvertToAd(ad_username=ad_login), actor
            )
            assert converted.auth_source == "ad"
            assert converted.hashed_password is None
            assert converted.ad_username == ad_login

            with pytest.raises(HTTPException) as again:
                await users_service.convert_user_to_ad(
                    db, target_id, ConvertToAd(ad_username=_login()), actor
                )
            assert again.value.status_code == 409

        async with SessionFactory() as db:
            tokens = (
                await db.execute(select(RefreshToken).where(RefreshToken.user_id == target_id))
            ).scalars().all()
            assert tokens and all(token.revoked_at is not None for token in tokens)
            events = (
                await db.execute(
                    select(AuditLog).where(AuditLog.action == "other")
                )
            ).scalars().all()
            events = [e for e in events if e.details.get("event") == "convert_to_ad"]
            mine = [e for e in events if e.details.get("target_user_id") == str(target_id)]
            assert mine and mine[0].details["auth_source"] == "ad"
            assert mine[0].actor_user_id == actor_id
            serialized = str([e.details for e in events])
            assert "$2" not in serialized  # no hash ever reaches the audit log
    finally:
        await _delete(email, ad_login, actor_email)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_convert_refuses_a_login_already_assigned_to_someone_else():
    email = f"{_login()}@example.com"
    taken = _login()
    try:
        async with SessionFactory() as db:
            await users_service.create_ad_user(
                db, AdUserCreate(ad_username=taken, full_name="Owner", role="operator")
            )
            local = await users_service.create_user(
                db,
                UserCreate(email=email, full_name="L", password="LocalPass-123", role="operator"),
            )
            with pytest.raises(HTTPException) as conflict:
                await users_service.convert_user_to_ad(
                    db, local.id, ConvertToAd(ad_username=taken), None
                )
            assert conflict.value.status_code == 409
            await db.refresh(local)
            assert local.auth_source == "local" and local.hashed_password
    finally:
        await _delete(email, taken)


def test_only_administrators_may_create_local_accounts_or_convert():
    non_admin = User(email="o@example.com", full_name="O", role="operator")
    admin = User(email="a@example.com", full_name="A", role="admin")
    with pytest.raises(HTTPException) as denied:
        users_router._require_admin_role(non_admin)
    assert denied.value.status_code == 403
    users_router._require_admin_role(admin)
