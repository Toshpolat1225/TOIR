import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.users import validate_email

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, value: str) -> str:
        """An email, or a bare directory login such as ``t.turakulov``."""
        normalized = value.strip()
        if "@" in normalized:
            return validate_email(normalized)
        if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", normalized) is None:
            raise ValueError("A valid login or email address is required")
        return normalized.lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    refresh_token: str
    expires_in: int = Field(gt=0)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
