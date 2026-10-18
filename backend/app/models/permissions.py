from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (CheckConstraint("action IN ('view','create','update','delete','export','approve','manage_permissions','manage_users','manage_reference_data')", name="ck_permissions_action"),)

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    module: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        CheckConstraint("role IN ('admin','operator','master','management')", name="ck_role_permissions_role"),
        UniqueConstraint("role", "permission_code", name="uq_role_permissions_role_code"),
        Index("ix_role_permissions_role", "role"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    role: Mapped[str] = mapped_column(Text, nullable=False)
    permission_code: Mapped[str] = mapped_column(Text, ForeignKey("permissions.code", ondelete="CASCADE"), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class PermissionAudit(Base):
    __tablename__ = "permission_audit"
    __table_args__ = (
        CheckConstraint("target_role IN ('admin','operator','master','management')", name="ck_permission_audit_role"),
        Index("ix_permission_audit_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    target_role: Mapped[str] = mapped_column(Text, nullable=False)
    permission_code: Mapped[str] = mapped_column(Text, nullable=False)
    previous_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    new_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
