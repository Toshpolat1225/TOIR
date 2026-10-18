from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RoleName = Literal["admin", "operator", "master", "management"]


class PermissionRead(BaseModel):
    code: str
    module: str
    action: str
    label: str
    granted: bool


class RolePermissionSet(BaseModel):
    granted: list[str] = Field(max_length=200)
    model_config = ConfigDict(extra="forbid")


class RolePermissionResponse(BaseModel):
    role: RoleName
    permissions: list[PermissionRead]
    changed: list[str] = Field(default_factory=list)
