"""Granting access to directory accounts (no local accounts exist any more: AUTH-01)."""
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.audit_log import AuditLog
from app.models.identity import RefreshToken, User
from app.schemas.users import AdUserCreate
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
