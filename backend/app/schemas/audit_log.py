from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AuditAction = Literal["create", "update", "delete", "login", "logout", "other"]


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: AuditAction
    actor_type: Literal["user", "system", "anonymous"]
    actor_user_id: UUID | None
    actor_name: str | None
    module: str
    route: str
    object_type: str | None
    object_id: str | None
    object_label: str | None
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    details: dict[str, Any] | None
    created_at: datetime


class AuditActorOption(BaseModel):
    id: UUID
    name: str


class AuditLogFilters(BaseModel):
    users: list[AuditActorOption]
    modules: list[str]
