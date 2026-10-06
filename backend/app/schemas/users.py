import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UserRole = Literal["admin", "operator", "master", "management"]


def validate_email(value: str) -> str:
    normalized = value.strip()
    if (
        len(normalized) > 320
        or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized) is None
    ):
        raise ValueError("A valid email address is required")
    return normalized.lower()


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: UserRole
    section_id: UUID | None
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=300)
    password: str = Field(min_length=1, max_length=256)
    role: UserRole
    section_id: UUID | None = None
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name must not be empty")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def require_master_section(self) -> "UserCreate":
        if self.role == "master" and self.section_id is None:
            raise ValueError("Master users must be assigned to a section")
        return self


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=300)
    role: UserRole | None = None
    section_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name must not be empty")
        return normalized

    @model_validator(mode="after")
    def require_patch_field_and_non_null_values(self) -> "UserUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for field_name in ("full_name", "role", "is_active"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class PasswordReset(BaseModel):
    password: str = Field(min_length=1, max_length=256)

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value
