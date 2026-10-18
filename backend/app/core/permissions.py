from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.identity import User
from app.models.permissions import RolePermission

# Explicit action catalog. Each endpoint names the precise permission it needs.
PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "dashboard.view": ("dashboard", "view", "Dashboard"),
    "realtime.view": ("realtime", "view", "Realtime notifications"),
    "assets.view": ("assets", "view", "Fixed assets"),
    "assets.create": ("assets", "create", "Fixed assets"),
    "assets.update": ("assets", "update", "Fixed assets"),
    "assets.delete": ("assets", "delete", "Fixed assets"),
    "asset_catalogs.view": ("asset_catalogs", "view", "Asset type and status catalogs"),
    "asset_catalogs.manage_reference_data": ("asset_catalogs", "manage_reference_data", "Asset type and status catalogs"),
    "organization.view": ("organization", "view", "Organization and employees"),
    "organization.create": ("organization", "create", "Organization and employees"),
    "organization.update": ("organization", "update", "Organization and employees"),
    "organization.delete": ("organization", "delete", "Organization and employees"),
    "work_orders.view": ("work_orders", "view", "Work orders"),
    "work_orders.create": ("work_orders", "create", "Work orders"),
    "work_orders.update": ("work_orders", "update", "Work orders"),
    "work_orders.delete": ("work_orders", "delete", "Work orders"),
    "maintenance.view": ("maintenance", "view", "Maintenance"),
    "maintenance.update": ("maintenance", "update", "Maintenance"),
    "inventory.view": ("inventory", "view", "Nomenclature and norms"),
    "inventory.create": ("inventory", "create", "Nomenclature and norms"),
    "inventory.update": ("inventory", "update", "Nomenclature and norms"),
    "inventory.delete": ("inventory", "delete", "Nomenclature and norms"),
    "tmc.view": ("tmc", "view", "TMC documents"),
    "reports.view": ("reports", "view", "Reports"),
    "reports.export": ("reports", "export", "Reports"),
    "analytics.view": ("analytics", "view", "Analytics"),
    "users.view": ("users", "view", "Users"),
    "users.manage_users": ("users", "manage_users", "Users"),
    "users.set_active": ("users", "update", "Change user active status"),
    "permissions.manage_permissions": ("permissions", "manage_permissions", "Permissions"),
    "translations.view": ("translations", "view", "Translations"),
    "translations.manage_reference_data": ("translations", "manage_reference_data", "Translations"),
    "ml.view": ("ml", "view", "AI insights"),
    "ml.create": ("ml", "create", "AI analysis"),
    "maintenance_settings.view": ("maintenance_settings", "view", "Maintenance settings"),
    "maintenance_settings.update": ("maintenance_settings", "update", "Maintenance settings"),
}

ROLE_DEFAULTS: dict[str, frozenset[str]] = {
    "admin": frozenset(PERMISSIONS),
    "operator": frozenset({"realtime.view", "dashboard.view", "assets.view", "assets.create", "assets.update", "assets.delete", "asset_catalogs.view", "organization.view", "organization.create", "organization.update", "organization.delete", "work_orders.view", "work_orders.create", "work_orders.update", "maintenance.view", "maintenance.update", "inventory.view", "inventory.create", "inventory.update", "inventory.delete", "tmc.view", "reports.view", "reports.export", "analytics.view", "maintenance_settings.view", "maintenance_settings.update", "translations.view", "ml.view"}),
    "master": frozenset({"realtime.view", "dashboard.view", "assets.view", "asset_catalogs.view", "organization.view", "work_orders.view", "work_orders.create", "work_orders.update", "maintenance.view", "maintenance_settings.view", "inventory.view", "tmc.view", "reports.view", "reports.export", "analytics.view", "translations.view", "ml.view"}),
    "management": frozenset({"realtime.view", "dashboard.view", "assets.view", "asset_catalogs.view", "organization.view", "work_orders.view", "work_orders.create", "work_orders.update", "work_orders.delete", "maintenance.view", "maintenance.update", "maintenance_settings.view", "maintenance_settings.update", "inventory.view", "tmc.view", "reports.view", "reports.export", "analytics.view", "translations.view", "ml.view"}),
}


def require_permission(code: str):
    if code not in PERMISSIONS:
        raise ValueError(f"Unknown permission: {code}")

    async def dependency(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if user.role == "admin":
            return user
        result = await db.execute(
            select(RolePermission.granted).where(
                RolePermission.role == user.role,
                RolePermission.permission_code == code,
            )
        )
        if result.scalar_one_or_none() is not True:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


async def user_has_permission(db: AsyncSession, user: User, code: str) -> bool:
    if code not in PERMISSIONS:
        return False
    if user.role == "admin":
        return True
    result = await db.execute(
        select(RolePermission.granted).where(
            RolePermission.role == user.role,
            RolePermission.permission_code == code,
        )
    )
    return result.scalar_one_or_none() is True
