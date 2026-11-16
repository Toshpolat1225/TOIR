"""Active Directory login: unit tests (no network) and PostgreSQL flow tests."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.config import settings as real_settings
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.identity import LoginAttempt, RefreshToken, User
from app.schemas.auth import LoginRequest
from app.services import ad_auth
from app.services import auth as auth_service


# ---------------------------------------------------------------- ad_auth unit

def test_invalid_login_or_empty_password_never_reaches_a_server():
    with patch.object(ad_auth, "_check_one_server") as server:
        for login, password in (
            ("a b", "x"),
            ("user)(uid=*", "x"),
            ("", "x"),
            ("good.login", ""),
            ("good.login", "   "),
        ):
            with pytest.raises(ad_auth.AdRejected):
                ad_auth.verify_password(login, password)
        server.assert_not_called()


def test_wrong_password_is_not_retried_on_the_second_controller():
    with patch.object(
        ad_auth, "_check_one_server", side_effect=ad_auth.AdRejected("52e")
    ) as server:
        with pytest.raises(ad_auth.AdRejected):
            ad_auth.verify_password("good.login", "bad")
    assert server.call_count == 1


def test_network_error_fails_over_to_the_second_controller():
    identity = ad_auth.AdIdentity("guid", "good.login", "Name", None)
    with patch.object(
        ad_auth, "_check_one_server", side_effect=[OSError("down"), identity]
    ) as server:
        assert ad_auth.verify_password("good.login", "pw") == identity
    assert [call.args[0] for call in server.call_args_list] == [
        "dc-r.agmk.uz",
        "dc.agmk.uz",
    ]


def test_all_controllers_down_is_unavailable_not_rejected():
    with patch.object(ad_auth, "_check_one_server", side_effect=OSError("down")):
        with pytest.raises(ad_auth.AdUnavailable):
            ad_auth.verify_password("good.login", "pw")


class _FakeConnection:
    def __init__(self, *, bind_ok, result=None, whoami="u:AGMK\\good.login", entries=1):
        self._bind_ok = bind_ok
        self.result = result or {}
        self._whoami = whoami
        self._entries = entries
        self.response = []
        self.extend = SimpleNamespace(
            standard=SimpleNamespace(who_am_i=lambda: self._whoami)
        )
        self.searched = None
        self.unbound = False

    def bind(self):
        return self._bind_ok

    def search(self, base, flt, **kwargs):
        self.searched = (base, flt)
        guid = uuid4()
        entry = {
            "type": "searchResEntry",
            "raw_attributes": {"objectGUID": [guid.bytes_le]},
            "attributes": {
                "sAMAccountName": "good.login",
                "displayName": ["Good Login"],
                "mail": [],
            },
        }
        self.response = [entry] * self._entries
        self.guid = guid

    def unbind(self):
        self.unbound = True


def _run_check(connection):
    with patch.object(ad_auth.ldap3, "Connection", return_value=connection):
        return ad_auth._check_one_server("dc-r.agmk.uz", "good.login", "pw")


def test_bind_ok_returns_identity_found_by_whoami_login_with_escaping():
    connection = _FakeConnection(bind_ok=True, whoami="u:AGMK\\good.login")
    identity = _run_check(connection)
    assert identity.login == "good.login"
    assert identity.guid == str(connection.guid)
    assert identity.name == "Good Login" and identity.mail is None
    assert "(sAMAccountName=good.login)" in connection.searched[1]
    assert connection.unbound is True


def test_whoami_value_is_escaped_in_the_search_filter():
    connection = _FakeConnection(bind_ok=True, whoami="u:AGMK\\a*)(b")
    _run_check(connection)
    assert "a\\2a\\29\\28b" in connection.searched[1]


def test_invalid_credentials_is_rejected_with_the_ad_code():
    connection = _FakeConnection(
        bind_ok=False,
        result={"result": 49, "message": "80090308: LdapErr ... data 52e, v4563"},
    )
    with pytest.raises(ad_auth.AdRejected) as rejected:
        _run_check(connection)
    assert rejected.value.ad_code == "52e"


def test_unexpected_bind_failure_is_unavailable_and_not_a_password_error():
    connection = _FakeConnection(bind_ok=False, result={"result": 53})
    with pytest.raises(ad_auth.AdUnavailable):
        _run_check(connection)


def test_zero_or_two_directory_entries_are_rejected():
    for count in (0, 2):
        with pytest.raises(ad_auth.AdRejected):
            _run_check(_FakeConnection(bind_ok=True, entries=count))


def test_malformed_whoami_is_rejected():
    with pytest.raises(ad_auth.AdRejected):
        _run_check(_FakeConnection(bind_ok=True, whoami="dn:cn=x"))


def test_login_name_mapping_only_for_agmk_domain_when_enabled():
    on = real_settings.model_copy(update={"ad_auth_enabled": True})
    off = real_settings.model_copy(update={"ad_auth_enabled": False})
    with patch.object(auth_service, "settings", on):
        assert auth_service.ad_login_name("T.Turakulov") == "t.turakulov"
        assert auth_service.ad_login_name("t.turakulov@agmk.uz") == "t.turakulov"
        assert auth_service.ad_login_name("t.turakulov@AGMK.UZ") == "t.turakulov"
        assert auth_service.ad_login_name("someone@other.com") is None
        assert auth_service.ad_login_name("bad login") is None
    with patch.object(auth_service, "settings", off):
        assert auth_service.ad_login_name("t.turakulov") is None


def test_login_request_accepts_bare_login_and_long_directory_passwords():
    assert LoginRequest(email="T.Turakulov", password="x" * 100).email == "t.turakulov"
    assert LoginRequest(email="a@b.uz", password="p").email == "a@b.uz"
    for bad in ("bad login", "a b@c.uz", "x)(y"):
        with pytest.raises(ValueError):
            LoginRequest(email=bad, password="p")


# ------------------------------------------------------------- flow with PG

pytestmark_pg = [pytest.mark.pg, pytest.mark.asyncio]


async def _make_user(*, active=True, password="LocalPass-123", source="ad", guid=None):
    tag = uuid4().hex[:10]
    login = f"adtest-{tag}"
    user_id = uuid4()
    async with SessionFactory() as db:
        db.add(
            User(
                id=user_id,
                email=f"{login}@agmk.uz",
                full_name="AD Test",
                hashed_password=hash_password(password) if source == "local" else None,
                auth_source=source,
                ad_username=login if source == "ad" else None,
                ad_object_guid=guid,
                role="admin",
                is_active=active,
            )
        )
        await db.commit()
    return user_id, login


async def _cleanup(user_id, login):
    async with SessionFactory() as db:
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        await db.execute(delete(LoginAttempt))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


def _settings(**update):
    return real_settings.model_copy(update={"ad_auth_enabled": True, **update})


async def _login(identifier, password, ip="10.0.0.1"):
    async with SessionFactory() as db:
        return await auth_service.authenticate(
            db, LoginRequest(email=identifier, password=password), ip
        )


@pytest.mark.pg
@pytest.mark.asyncio
async def test_ad_success_logs_in_the_existing_user_without_local_password():
    user_id, login = await _make_user()
    identity = ad_auth.AdIdentity(str(uuid4()), login, "AD Test", None)
    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(ad_auth, "verify_password", return_value=identity) as check,
        ):
            tokens = await _login(login, "the-domain-password-is-not-the-local-one")
            assert tokens.access_token and tokens.refresh_token
            check.assert_called_once()
            # the full email form works the same way
            assert (await _login(f"{login}@agmk.uz", "x")).access_token
    finally:
        await _cleanup(user_id, login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_ad_success_without_a_toir_user_is_refused_and_creates_nothing():
    login = f"ghost-{uuid4().hex[:8]}"
    identity = ad_auth.AdIdentity(str(uuid4()), login, "Ghost", None)
    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(ad_auth, "verify_password", return_value=identity),
        ):
            with pytest.raises(HTTPException) as denied:
                await _login(login, "pw")
        assert denied.value.status_code == 401
        async with SessionFactory() as db:
            assert (
                await db.scalar(select(User).where(User.email == f"{login}@agmk.uz"))
            ) is None
    finally:
        await _cleanup(uuid4(), login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_inactive_toir_user_is_refused_even_with_a_valid_directory_password():
    user_id, login = await _make_user(active=False)
    identity = ad_auth.AdIdentity(str(uuid4()), login, "x", None)
    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(ad_auth, "verify_password", return_value=identity),
        ):
            with pytest.raises(HTTPException) as denied:
                await _login(login, "pw")
        assert denied.value.status_code == 401
    finally:
        await _cleanup(user_id, login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_wrong_directory_password_locks_after_three_failures_before_ad_does():
    user_id, login = await _make_user()
    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(
                ad_auth, "verify_password", side_effect=ad_auth.AdRejected("52e")
            ) as check,
        ):
            for _ in range(3):
                with pytest.raises(HTTPException) as bad:
                    await _login(login, "wrong", ip="10.0.0.9")
                assert bad.value.status_code == 401
            # the 4th attempt (even from another IP) is stopped by OUR counter
            with pytest.raises(HTTPException) as locked:
                await _login(login, "wrong", ip="10.0.0.77")
            assert locked.value.status_code == 429
            assert check.call_count == 3  # AD never sees a 4th wrong password
    finally:
        await _cleanup(user_id, login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_directory_down_is_503_for_ad_users_and_never_uses_a_local_password():
    user_id, login = await _make_user()
    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(ad_auth, "verify_password", side_effect=ad_auth.AdUnavailable()),
        ):
            with pytest.raises(HTTPException) as down:
                await _login(login, "anything")
            assert down.value.status_code == 503
    finally:
        await _cleanup(user_id, login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_local_user_with_agmk_email_never_reaches_the_directory():
    user_id, login = await _make_user(source="local", password="LocalPass-123")
    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(ad_auth, "verify_password") as check,
        ):
            assert (await _login(f"{login}@agmk.uz", "LocalPass-123")).access_token
            with pytest.raises(HTTPException) as wrong:
                await _login(f"{login}@agmk.uz", "bad")
            assert wrong.value.status_code == 401
            check.assert_not_called()
    finally:
        await _cleanup(user_id, login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_same_password_is_checked_by_the_backend_of_the_account_source():
    same = "Same-Password-1"
    ad_id, ad_login = await _make_user(source="ad")
    local_id, local_login = await _make_user(source="local", password=same)
    try:
        identity = ad_auth.AdIdentity(str(uuid4()), ad_login, "x", None)
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(ad_auth, "verify_password", return_value=identity) as check,
            patch.object(auth_service, "verify_password", return_value=True) as local_check,
        ):
            await _login(ad_login, same)
            assert check.call_count == 1 and local_check.call_count == 0
            await _login(f"{local_login}@agmk.uz", same)
            assert check.call_count == 1 and local_check.call_count == 1
        async with SessionFactory() as db:
            rows = (
                await db.execute(
                    select(AuditLog.details).where(
                        AuditLog.action == "login", AuditLog.module == "auth"
                    )
                )
            ).scalars().all()
        sources = [row.get("auth_source") for row in rows]
        assert "ad" in sources and "local" in sources
    finally:
        await _cleanup(ad_id, ad_login)
        await _cleanup(local_id, local_login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_ad_user_is_refused_when_ad_login_is_disabled():
    user_id, login = await _make_user(source="ad")
    try:
        with (
            patch.object(
                auth_service,
                "settings",
                real_settings.model_copy(update={"ad_auth_enabled": False}),
            ),
            patch.object(ad_auth, "verify_password") as check,
        ):
            with pytest.raises(HTTPException) as denied:
                await _login(f"{login}@agmk.uz", "pw")
            assert denied.value.status_code == 401
            check.assert_not_called()
    finally:
        await _cleanup(user_id, login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_first_login_binds_object_guid_and_a_different_guid_is_refused_later():
    user_id, login = await _make_user(source="ad")
    first = uuid4()
    try:
        with patch.object(auth_service, "settings", _settings()):
            with patch.object(
                ad_auth,
                "verify_password",
                return_value=ad_auth.AdIdentity(str(first), login, "x", None),
            ):
                assert (await _login(login, "pw")).access_token
            async with SessionFactory() as db:
                assert (await db.get(User, user_id)).ad_object_guid == first
            with patch.object(
                ad_auth,
                "verify_password",
                return_value=ad_auth.AdIdentity(str(uuid4()), login, "x", None),
            ):
                with pytest.raises(HTTPException) as denied:
                    await _login(login, "pw")
                assert denied.value.status_code == 401
            with patch.object(
                ad_auth,
                "verify_password",
                return_value=ad_auth.AdIdentity(str(first), login, "x", None),
            ):
                assert (await _login(login, "pw")).access_token
    finally:
        await _cleanup(user_id, login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_guid_already_bound_to_another_user_is_refused():
    shared = uuid4()
    owner_id, owner_login = await _make_user(source="ad", guid=shared)
    other_id, other_login = await _make_user(source="ad")
    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(
                ad_auth,
                "verify_password",
                return_value=ad_auth.AdIdentity(str(shared), other_login, "x", None),
            ),
        ):
            with pytest.raises(HTTPException) as denied:
                await _login(other_login, "pw")
            assert denied.value.status_code == 401
            async with SessionFactory() as db:
                assert (await db.get(User, other_id)).ad_object_guid is None
    finally:
        await _cleanup(owner_id, owner_login)
        await _cleanup(other_id, other_login)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_database_rejects_inconsistent_credential_rows():
    from sqlalchemy.exc import IntegrityError

    bad_rows = [
        dict(auth_source="ad", hashed_password=hash_password("x"), ad_username="bad1"),
        dict(auth_source="ad", hashed_password=None, ad_username=None),
        dict(auth_source="local", hashed_password=None, ad_username=None),
        dict(auth_source="local", hashed_password=hash_password("x"), ad_username="bad2"),
        dict(auth_source="other", hashed_password=hash_password("x"), ad_username=None),
    ]
    for row in bad_rows:
        async with SessionFactory() as db:
            db.add(
                User(
                    email=f"bad-{uuid4().hex[:8]}@agmk.uz",
                    full_name="Bad",
                    role="operator",
                    **row,
                )
            )
            with pytest.raises(IntegrityError):
                await db.commit()


def test_password_opening_a_different_account_than_typed_is_rejected():
    # The guide's UPN trap: typed "victim", AD bound the attacker's own account.
    attacker = ad_auth.AdIdentity(str(uuid4()), "attacker", "Attacker", None)
    with patch.object(ad_auth, "_check_one_server", return_value=attacker):
        with pytest.raises(ad_auth.AdRejected) as rejected:
            ad_auth.verify_password("victim", "attackers-own-password")
    assert rejected.value.ad_code == "login-mismatch"


def test_typed_login_case_difference_is_not_a_mismatch():
    identity = ad_auth.AdIdentity(str(uuid4()), "T.Turakulov", "T", None)
    with patch.object(ad_auth, "_check_one_server", return_value=identity):
        assert ad_auth.verify_password("t.turakulov", "pw") == identity


@pytest.mark.pg
@pytest.mark.asyncio
async def test_one_ip_guessing_many_accounts_is_stopped_by_the_ip_limit():
    from app.services.auth import AD_IP_FAILURE_LIMIT

    try:
        with (
            patch.object(auth_service, "settings", _settings()),
            patch.object(
                ad_auth, "verify_password", side_effect=ad_auth.AdRejected("525")
            ) as check,
        ):
            for index in range(AD_IP_FAILURE_LIMIT):
                with pytest.raises(HTTPException) as bad:
                    await _login(f"victim{index}-{uuid4().hex[:6]}", "x", ip="10.9.9.9")
                assert bad.value.status_code == 401
            calls_before = check.call_count
            with pytest.raises(HTTPException) as locked:
                await _login("another-account", "x", ip="10.9.9.9")
            assert locked.value.status_code == 429
            assert check.call_count == calls_before  # AD is not asked at all
            # a different IP is not affected
            with pytest.raises(HTTPException) as other_ip:
                await _login("another-account", "x", ip="10.8.8.8")
            assert other_ip.value.status_code == 401
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(LoginAttempt))
            await db.commit()
