"""AUTH-01 (CODEX): the system keeps no passwords of its own. Sign-in is the domain (AD) only.
The only exception is an audited, short-lived emergency session started from the server shell (never over HTTP).

No database needed: structure checks and unit tests with a fake session.
"""
import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def test_security_module_has_no_password_hashing():
    from app.core import security

    for name in ("hash_password", "verify_password", "password_context", "_dummy_password_hash"):
        assert not hasattr(security, name), name


def test_user_model_has_no_password_column_and_only_ad_source():
    from app.models.identity import User

    assert "hashed_password" not in User.__table__.columns
    checks = " ".join(str(c.sqltext) for c in User.__table__.constraints if hasattr(c, "sqltext"))
    assert "'local'" not in checks


def test_no_local_account_routes():
    from app.main import app

    seen = {(r.path, m) for r in app.routes if hasattr(r, "methods") for m in r.methods}
    assert ("/api/v1/users", "POST") not in seen
    assert not [p for p, _ in seen if p.endswith("/reset-password")]
    assert not [p for p, _ in seen if p.endswith("/convert-to-ad")]


def test_services_have_no_local_password_paths():
    from app.services import auth, users

    assert not hasattr(auth, "create_initial_admin")
    assert not hasattr(auth, "MAX_LOCAL_PASSWORD_BYTES")
    for name in ("create_user", "reset_user_password", "convert_user_to_ad"):
        assert not hasattr(users, name), name


def test_schemas_have_no_password_inputs_and_user_read_is_ad_only():
    from typing import get_args

    from app.schemas import users as schemas

    for name in ("UserCreate", "PasswordReset", "ConvertToAd", "validate_password_policy"):
        assert not hasattr(schemas, name), name
    assert get_args(schemas.UserRead.model_fields["auth_source"].annotation) == ("ad",)


def test_cli_has_no_password_commands_but_has_emergency_session():
    from app import cli

    parser = cli.build_parser() if hasattr(cli, "build_parser") else None
    names = _subcommands(parser) if parser is not None else set(re.findall(r'add_parser\(\s*"([^"]+)"', (BACKEND / "app" / "cli.py").read_text(encoding="utf-8")))
    assert "create-admin" not in names and "user-convert-to-ad" not in names
    assert "emergency-session" in names


def _subcommands(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_password_libraries_are_not_dependencies():
    text = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "passlib" not in text and "bcrypt" not in text


# ── emergency session ──────────────────────────────────────────────────────────

def _admin(**overrides):
    base = dict(id=uuid4(), full_name="Admin A", email="a@x", role="admin", is_active=True, auth_source="ad", ad_username="admin.a")
    base.update(overrides)
    return SimpleNamespace(**base)


def _db(user):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_emergency_session_is_short_audited_and_for_an_active_ad_admin_only():
    from app.models.audit_log import AuditLog
    from app.models.identity import RefreshToken
    from app.services import auth

    admin = _admin()
    db = _db(admin)
    token = await auth.issue_emergency_session(db, "admin.a", operator="server-shell", now=NOW)
    assert isinstance(token, str) and len(token) >= 32
    added = [c.args[0] for c in db.add.call_args_list]
    refresh = next(o for o in added if isinstance(o, RefreshToken))
    assert refresh.user_id == admin.id and refresh.expires_at == NOW + timedelta(minutes=auth.EMERGENCY_SESSION_MINUTES)
    assert auth.EMERGENCY_SESSION_MINUTES == 15
    audit = next(o for o in added if isinstance(o, AuditLog))
    assert "emergency_session" in str(audit.details) and "server-shell" in str(audit.details)
    assert token not in str(audit.details)  # the secret itself is never written to the log
    db.commit.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [None, _admin(role="operator"), _admin(is_active=False)])
async def test_emergency_session_refuses_everyone_else(user):
    from app.services import auth

    db = _db(user)
    with pytest.raises(ValueError):
        await auth.issue_emergency_session(db, "someone", operator="server-shell", now=NOW)
    db.add.assert_not_called()


def test_a_short_session_is_not_extended_by_rotation_but_a_normal_one_is():
    from app.core.config import settings
    from app.services import auth

    created = NOW - timedelta(minutes=5)
    emergency_expiry = created + timedelta(minutes=15)
    assert auth.next_refresh_expiry(created_at=created, expires_at=emergency_expiry, now=NOW) == emergency_expiry
    normal_created = NOW - timedelta(days=2)
    normal_expiry = normal_created + timedelta(days=settings.refresh_token_expire_days)
    assert auth.next_refresh_expiry(created_at=normal_created, expires_at=normal_expiry, now=NOW) == NOW + timedelta(days=settings.refresh_token_expire_days)
