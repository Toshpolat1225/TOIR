from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from typing import Dict, Any, Optional

from ..config import settings
from ..schemas.auth import TokenPayload


def create_access_token(data: Dict[str, Any]) -> str:
    """
    Creates a new JWT access token.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes a JWT access token and returns its payload.
    Returns None if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        # You might want to validate the payload structure here with Pydantic
        # TokenPayload(**payload)
        return payload
    except JWTError:
        return None