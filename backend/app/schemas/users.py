import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

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
    auth_source: Literal["ad"] = "ad"
    ad_username: str | None = None
    # read from the model but never sent: an internal directory identifier is not the client's business
    ad_object_guid: UUID | None = Field(default=None, exclude=True)
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ad_confirmed(self) -> bool:
        """The directory account was seen at a first successful login (its GUID is bound)."""
        return self.ad_object_guid is not None


AD_LOGIN_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")


def validate_ad_username(value: str) -> str:
    normalized = value.strip()
    if "@" in normalized:
        normalized = normalized.rpartition("@")[0]
    if AD_LOGIN_PATTERN.fullmatch(normalized) is None:
        raise ValueError("A valid Active Directory login is required")
    return normalized.lower()


class AdUserCreate(BaseModel):
    """Grant access to a directory account. There is no password field."""

    ad_username: str = Field(min_length=1, max_length=320)
    full_name: str = Field(min_length=1, max_length=300)
    role: UserRole
    section_id: UUID | None = None
    is_active: bool = True

    @field_validator("ad_username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return validate_ad_username(value)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name must not be empty")
        return normalized

    @model_validator(mode="after")
    def require_master_section(self) -> "AdUserCreate":
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
