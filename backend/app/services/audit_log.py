import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import Select, Text, cast, delete, event, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.database import SessionFactory
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

_AUDIT_PENDING = "audit_pending"
_OPERATIONAL_TABLES = {
    "audit_logs",
    "login_attempts",
    "refresh_tokens",
    "daily_readiness_snapshots",
    "gtk_carriages",
    "gtk_locomotives",
    "gtk_train_members",
    "gtk_trains",
    "wialon_counter_states",
    "wialon_rejected_readings",
}
_SENSITIVE_PARTS = (
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "credential",
    "hash",
    "error",
)
_LABEL_FIELDS = ("name", "full_name", "number", "code", "title", "email")


def _is_sensitive_field(name: str) -> bool:
    return any(part in name.casefold() for part in _SENSITIVE_PARTS)


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str):
            return value[:2000]
        return value
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _safe_value(value.value)
    if isinstance(value, dict):
        return {
            str(key): _safe_value(item)
            for key, item in value.items()
            if not _is_sensitive_field(str(key))
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in list(value)[:100]]
    return str(value)[:2000]


def _safe_fields(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_value(value)
        for key, value in values.items()
        if not _is_sensitive_field(key)
    }


def _object_values(target: object, mapper: Any) -> dict[str, Any]:
    return _safe_fields(
        {
            attribute.key: getattr(target, attribute.key, None)
            for attribute in mapper.column_attrs
        }
    )


def set_audit_actor(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    actor_name: str | None,
    actor_type: str,
    route: str | None = None,
    request_state: Any = None,
) -> None:
    sync_session = session.sync_session
    sync_session.info.update(
        audit_actor_id=actor_id,
        audit_actor_name=actor_name,
        audit_actor_type=actor_type,
        audit_route=route,
        audit_request_state=request_state,
    )
    if request_state is not None:
        request_state.audit_actor_id = actor_id
        request_state.audit_actor_name = actor_name
        request_state.audit_actor_type = actor_type


def set_audit_system_context(session: AsyncSession, module: str) -> None:
    sync_session = session.sync_session
    if sync_session.info.get("audit_actor_id") is not None:
        return
    sync_session.info.update(
        audit_actor_type="system",
        audit_actor_name=f"Система {module.upper()}",
        audit_route=f"/system/{module}-sync",
    )


def add_auth_audit_event(
    session: AsyncSession,
    *,
    action: str,
    actor_id: UUID | None,
    actor_name: str | None,
    route: str,
    status_code: int,
) -> None:
    session.add(
        AuditLog(
            action=action,
            actor_type="user" if actor_id else "anonymous",
            actor_user_id=actor_id,
            actor_name=actor_name,
            module="auth",
            route=route,
            details={"status_code": status_code},
        )
    )


@event.listens_for(Session, "before_flush")
def _collect_model_changes(
    session: Session, _flush_context: Any, _instances: Any
) -> None:
    pending = session.info.setdefault(_AUDIT_PENDING, [])
    for target in tuple(session.new) + tuple(session.dirty) + tuple(session.deleted):
        state = inspect(target)
        mapper = state.mapper
        table_name = mapper.local_table.name
        if table_name in _OPERATIONAL_TABLES or (
            table_name == "wialon_units" and target not in session.new
        ):
            continue

        if target in session.new:
            action = "create"
            old_values = None
            new_values = _object_values(target, mapper)
        elif target in session.deleted:
            action = "delete"
            old_values = _object_values(target, mapper)
            new_values = None
        else:
            changes: dict[str, tuple[Any, Any]] = {}
            redacted_fields_count = 0
            for attribute in mapper.column_attrs:
                history = state.attrs[attribute.key].history
                if history.has_changes():
                    if _is_sensitive_field(attribute.key):
                        redacted_fields_count += 1
                        continue
                    before = history.deleted[0] if history.deleted else None
                    after = history.added[0] if history.added else None
                    changes[attribute.key] = (_safe_value(before), _safe_value(after))
            if not changes and not redacted_fields_count:
                continue
            old_values = {key: pair[0] for key, pair in changes.items()}
            new_values = {key: pair[1] for key, pair in changes.items()}
            action = "update"

        pending.append(
            {
                "target": target,
                "action": action,
                "table": table_name,
                "old_values": old_values,
                "new_values": new_values,
                "details": (
                    {"redacted_fields_count": redacted_fields_count}
                    if action == "update" and redacted_fields_count
                    else None
                ),
            }
        )


@event.listens_for(Session, "after_flush_postexec")
def _write_model_changes(session: Session, _flush_context: Any) -> None:
    pending = session.info.pop(_AUDIT_PENDING, [])
    if not pending:
        return

    request_state = session.info.get("audit_request_state")
    if request_state is not None:
        request_state.audit_model_changes = True

    actor_id = session.info.get("audit_actor_id")
    actor_type = session.info.get("audit_actor_type", "system")
    route = session.info.get("audit_route") or "/"
    route_parts = route.strip("/").split("/")
    if route_parts[0] == "system" and len(route_parts) > 1:
        module = route_parts[1].removesuffix("-sync")
    else:
        module = route_parts[2] if len(route_parts) > 2 else "system"
    for item in pending:
        target = item["target"]
        mapper = inspect(target).mapper
        item_module = module
        item_route = route
        if actor_type == "system" and item["table"].startswith("gtk_"):
            item_module = "gtk"
            item_route = "/system/gtk-sync"
        elif actor_type == "system" and item["table"].startswith("wialon_"):
            item_module = "wialon"
            item_route = "/system/wialon-sync"
        identity = inspect(target).identity
        if identity:
            object_id = str(identity[0])
        else:
            object_id = None
        label = next(
            (
                str(getattr(target, field))
                for field in _LABEL_FIELDS
                if getattr(target, field, None) not in (None, "")
            ),
            None,
        )
        session.add(
            AuditLog(
                action=item["action"],
                actor_type=actor_type,
                actor_user_id=actor_id,
                actor_name=session.info.get("audit_actor_name")
                or {"gtk": "Система GTK", "wialon": "Система Wialon"}.get(item_module),
                module=item_module,
                route=item_route,
                object_type=item["table"],
                object_id=object_id,
                object_label=label[:500] if label else None,
                old_values=item["old_values"],
                new_values=(
                    _object_values(target, mapper)
                    if item["action"] == "create"
                    else item["new_values"]
                ),
                details=item["details"],
            )
        )


def build_audit_query(
    *,
    action: str | None = None,
    actor_id: UUID | None = None,
    module: str | None = None,
    object_query: str | None = None,
    query: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Select[tuple[AuditLog]]:
    statement = select(AuditLog)
    if action:
        statement = statement.where(AuditLog.action == action)
    if actor_id:
        statement = statement.where(AuditLog.actor_user_id == actor_id)
    if module:
        statement = statement.where(AuditLog.module == module)
    if object_query:
        pattern = f"%{object_query.strip()}%"
        statement = statement.where(
            AuditLog.object_label.ilike(pattern)
            | AuditLog.object_type.ilike(pattern)
            | AuditLog.object_id.ilike(pattern)
        )
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            AuditLog.actor_name.ilike(pattern)
            | AuditLog.module.ilike(pattern)
            | AuditLog.route.ilike(pattern)
            | AuditLog.object_label.ilike(pattern)
            | AuditLog.object_type.ilike(pattern)
            | AuditLog.object_id.ilike(pattern)
            | cast(AuditLog.old_values, Text).ilike(pattern)
            | cast(AuditLog.new_values, Text).ilike(pattern)
        )
    if date_from:
        statement = statement.where(
            AuditLog.created_at >= normalize_audit_datetime(date_from)
        )
    if date_to:
        statement = statement.where(
            AuditLog.created_at <= normalize_audit_datetime(date_to)
        )
    return statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


def normalize_audit_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def delete_expired_audit_logs() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    async with SessionFactory() as session:
        result = await session.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        )
        await session.commit()
        return result.rowcount or 0


@event.listens_for(Session, "after_rollback")
def _discard_pending_audit_changes(session: Session) -> None:
    session.info.pop(_AUDIT_PENDING, None)


async def run_audit_retention() -> None:
    while True:
        try:
            deleted = await delete_expired_audit_logs()
            if deleted:
                logger.info("Audit retention removed %s expired events", deleted)
        except SQLAlchemyError as exc:
            logger.error("Audit retention cleanup failed (%s)", type(exc).__name__)
        await asyncio.sleep(24 * 60 * 60)
