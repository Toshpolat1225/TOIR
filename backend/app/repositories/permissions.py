from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permissions import Permission, RolePermission


async def list_role_permissions(db: AsyncSession, role: str):
    result = await db.execute(
        select(Permission, RolePermission.granted)
        .outerjoin(RolePermission, (RolePermission.permission_code == Permission.code) & (RolePermission.role == role))
        .order_by(Permission.module, Permission.action, Permission.code)
    )
    return [(permission, granted is True) for permission, granted in result.all()]


async def get_role_grants(db: AsyncSession, role: str) -> set[str]:
    result = await db.execute(select(RolePermission.permission_code).where(RolePermission.role == role, RolePermission.granted.is_(True)))
    return set(result.scalars())
