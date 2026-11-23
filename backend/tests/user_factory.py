"""Test users are directory (AD) users: no password of any kind (AUTH-01)."""
from uuid import uuid4


def ad_user() -> dict:
    """Keyword arguments for `User(...)`: a unique passwordless directory login."""
    return {"auth_source": "ad", "ad_username": f"zz-{uuid4().hex[:14]}"}
