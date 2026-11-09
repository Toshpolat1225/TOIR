import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory, get_db
from app.core.security import require_role
from app.models.audit_log import AuditLog
from app.models.identity import User
from app.schemas.audit_log import (
    AuditAction,
    AuditActorOption,
    AuditLogFilters,
    AuditLogRead,
)
from app.schemas.common import PaginatedResponse
from app.services.audit_log import build_audit_query, normalize_audit_datetime

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_role("admin"))]


def _filters(
    action: AuditAction | None,
    actor_id: UUID | None,
    module: str | None,
    object_q: str | None,
    q: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select[tuple[AuditLog]]:
    if (
        date_from is not None
        and date_to is not None
        and normalize_audit_datetime(date_from)
        > normalize_audit_datetime(date_to)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from must not be later than date_to",
        )
    return build_audit_query(
        action=action,
        actor_id=actor_id,
        module=module,
        object_query=object_q,
        query=q,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("", response_model=PaginatedResponse[AuditLogRead])
async def list_audit_logs(
    _: AdminUser,
    db: DatabaseSession,
    action: AuditAction | None = None,
    actor_id: UUID | None = None,
    module: Annotated[str | None, Query(max_length=100)] = None,
    object_q: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AuditLogRead]:
    statement = _filters(action, actor_id, module, object_q, q, date_from, date_to)
    total = await db.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    result = await db.execute(statement.limit(limit).offset(offset))
    return PaginatedResponse[AuditLogRead](
        items=list(result.scalars().all()),
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/filters", response_model=AuditLogFilters)
async def get_audit_log_filters(
    _: AdminUser,
    db: DatabaseSession,
) -> AuditLogFilters:
    user_rows = await db.execute(
        select(AuditLog.actor_user_id, func.max(AuditLog.actor_name))
        .where(AuditLog.actor_user_id.is_not(None))
        .group_by(AuditLog.actor_user_id)
        .order_by(func.max(AuditLog.actor_name))
        .limit(500)
    )
    module_rows = await db.scalars(
        select(AuditLog.module).distinct().order_by(AuditLog.module).limit(200)
    )
    users = [
        AuditActorOption(id=actor_id, name=name or str(actor_id))
        for actor_id, name in user_rows.all()
        if actor_id is not None
    ]
    return AuditLogFilters(users=users, modules=list(module_rows.all()))


@router.get("/export.csv")
async def export_audit_logs(
    _: AdminUser,
    action: AuditAction | None = None,
    actor_id: UUID | None = None,
    module: Annotated[str | None, Query(max_length=100)] = None,
    object_q: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
    statement = _filters(action, actor_id, module, object_q, q, date_from, date_to)

    async def csv_rows() -> AsyncIterator[str]:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Дата и время",
                "Тип действия",
                "Пользователь",
                "Раздел",
                "Маршрут",
                "Объект",
                "ID объекта",
                "Старые значения",
                "Новые значения",
            ]
        )
        yield "\ufeff" + output.getvalue()
        output.seek(0)
        output.truncate(0)
        async with SessionFactory() as session:
            result = await session.stream_scalars(statement)
            async for event_row in result:
                writer.writerow(
                    [
                        event_row.created_at.isoformat(),
                        event_row.action,
                        _csv_safe(event_row.actor_name or event_row.actor_type),
                        _csv_safe(event_row.module),
                        _csv_safe(event_row.route),
                        _csv_safe(event_row.object_label or event_row.object_type),
                        _csv_safe(event_row.object_id),
                        json.dumps(event_row.old_values, ensure_ascii=False),
                        json.dumps(event_row.new_values, ensure_ascii=False),
                    ]
                )
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

    return StreamingResponse(
        csv_rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-logs.csv"'},
    )


@router.get("/{log_id}", response_model=AuditLogRead)
async def get_audit_log(
    log_id: UUID,
    _: AdminUser,
    db: DatabaseSession,
) -> AuditLog:
    event_row = await db.get(AuditLog, log_id)
    if event_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log entry not found",
        )
    return event_row


def _csv_safe(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = value.replace("\r", " ").replace("\n", " ")
    return f"'{cleaned}" if cleaned.startswith(("=", "+", "-", "@")) else cleaned
