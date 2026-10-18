from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.core.security import get_current_user
from app.models.identity import User
from app.models.permissions import RolePermission
from app.schemas.permissions import RoleName, RolePermissionResponse, RolePermissionSet
from app.services.permissions import read_role, update_role

router = APIRouter(prefix="/permissions", tags=["permissions"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
PermissionManager = Annotated[User, Depends(require_permission("permissions.manage_permissions"))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.get("/me")
async def get_my_permissions(user: AuthenticatedUser, db: DatabaseSession) -> dict[str, list[str]]:
    if user.role == "admin":
        from app.core.permissions import PERMISSIONS
        return {"permissions": sorted(PERMISSIONS)}
    result = await db.execute(
        select(RolePermission.permission_code).where(
            RolePermission.role == user.role, RolePermission.granted.is_(True)
        )
    )
    return {"permissions": sorted(result.scalars().all())}


@router.get("/{role}", response_model=RolePermissionResponse)
async def get_role_permissions(role: RoleName, _: PermissionManager, db: DatabaseSession):
    return await read_role(db, role)


@router.put("/{role}", response_model=RolePermissionResponse)
async def put_role_permissions(role: RoleName, payload: RolePermissionSet, user: PermissionManager, db: DatabaseSession):
    return await update_role(db, role, payload.granted, user.id)
