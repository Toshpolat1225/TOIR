from pydantic import BaseModel, EmailStr
from .user import CurrentUserResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenResponse(Token):
    user: CurrentUserResponse


class TokenPayload(BaseModel):
    sub: str | None = None
    role: str | None = None