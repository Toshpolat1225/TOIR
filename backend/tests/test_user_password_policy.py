"""Local passwords have a minimal policy when they are SET (login is unchanged: existing passwords keep working)."""
import pytest
from pydantic import ValidationError

from app.schemas.users import PasswordReset, UserCreate


def _create(password, email="someone@example.test"):
    return UserCreate(email=email, full_name="Test User", password=password, role="operator")


@pytest.mark.parametrize("bad", ["123", "short1", "1234567890", "aaaaaaaaaaaa", "abababababab"])
def test_weak_passwords_are_refused(bad):
    with pytest.raises(ValidationError):
        _create(bad)
    with pytest.raises(ValidationError):
        PasswordReset(password=bad)


def test_a_password_containing_the_login_is_refused():
    with pytest.raises(ValidationError):
        _create("someone-2026!", email="someone@example.test")


@pytest.mark.parametrize("good", ["LocalPass-123", "Other-Pass-1", "kT9#vQ2$mLx8", "длинный-пароль-2026"])
def test_reasonable_passwords_are_accepted(good):
    assert _create(good).password == good
    assert PasswordReset(password=good).password == good


def test_the_72_byte_limit_of_bcrypt_still_applies():
    with pytest.raises(ValidationError):
        _create("Ab1!" * 20)
