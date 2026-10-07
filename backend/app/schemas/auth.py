from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.users import validate_email

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("password")
    @classmethod
    def ensure_bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    refresh_token: str
    expires_in: int = Field(gt=0)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
