from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PERMISSIONS
from app.models.permissions import PermissionAudit, RolePermission
from app.repositories.permissions import get_role_grants, list_role_permissions

ROLES = {"admin", "operator", "master", "management"}


async def read_role(db: AsyncSession, role: str) -> dict:
    if role not in ROLES:
        raise HTTPException(status_code=404, detail="Role not found")
    rows = await list_role_permissions(db, role)
    return {"role": role, "permissions": [
        {"code": item.code, "module": item.module, "action": item.action, "label": item.label, "granted": granted}
        for item, granted in rows
    ], "changed": []}


async def update_role(db: AsyncSession, role: str, granted: list[str], actor_id) -> dict:
    if role not in ROLES:
        raise HTTPException(status_code=404, detail="Role not found")
    if role == "admin":
        raise HTTPException(status_code=403, detail="The admin role is protected")
    requested = set(granted)
    if len(requested) != len(granted) or requested - PERMISSIONS.keys():
        raise HTTPException(status_code=422, detail="Unknown or duplicate permission")
    elevated = {"permissions.manage_permissions", "users.manage_users", "asset_catalogs.manage_reference_data", "translations.manage_reference_data"}
    if requested & elevated:
        raise HTTPException(status_code=403, detail="Protected permissions can only remain on the admin role")
    current = await get_role_grants(db, role)
    changed = sorted(current ^ requested)
    if not changed:
        return await read_role(db, role)
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(782134991)"))
        for code in changed:
            db.add(PermissionAudit(actor_user_id=actor_id, target_role=role, permission_code=code,
                                   previous_granted=code in current, new_granted=code in requested,
                                   created_at=datetime.now(timezone.utc)))
        await db.execute(delete(RolePermission).where(RolePermission.role == role))
        db.add_all([RolePermission(role=role, permission_code=code, granted=code in requested) for code in PERMISSIONS])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    result = await read_role(db, role)
    result["changed"] = changed
    return result
