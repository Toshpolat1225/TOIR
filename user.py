import uuid
from pydantic import BaseModel, EmailStr
from ..models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None


class CurrentUserResponse(UserBase):
    id: uuid.UUID
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True