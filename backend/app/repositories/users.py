from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User

USER_SORT_FIELDS = frozenset(
    {"email", "full_name", "role", "created_at", "updated_at", "last_login_at"}
)


async def list_users(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
    sort_by: str,
    descending: bool,
) -> tuple[list[User], int]:
    if sort_by not in USER_SORT_FIELDS:
        raise ValueError("Unsupported user sort field")
    sort_column = getattr(User, sort_by)
    order_column = sort_column.desc() if descending else sort_column.asc()
    count_result = await db.execute(select(func.count()).select_from(User))
    total = count_result.scalar_one()
    users_result = await db.execute(
        select(User)
        .order_by(order_column, User.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(users_result.scalars().all()), total


async def get_user(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()
