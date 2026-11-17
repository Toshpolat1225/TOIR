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

from app.core.config import settings
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
    "wialon_counter_state",  # (was misspelled "wialon_counter_states", so it was never excluded)
    "wialon_rejected_readings",
    # append-only integration feeds: the tables themselves are the record, an audit copy only multiplies them
    "wialon_raw_receipts",
    "wialon_odometer_readings",
    "mileage_history",
    "mileage_calculation_inputs",
    "asset_meter_daily",
    "gtk_raw_snapshots",
    "gtk_sync_runs",
    "gtk_membership_observations",
    "gtk_wagon_mileage_log",
    "gtk_locomotive_mileage_checkpoints",
    # weighing-scale feed (re-derived on every pull; operator corrections `scale_corrections` ARE audited)
    "asset_position_history",  # movement-thinned track rows written by the syncs
    "scale_posts",
    "scale_cargo",
    "scale_trains",
    "scale_weighings",
    "scale_train_carriages",
}
# Columns a Wialon pull rewrites constantly: an update that touches nothing else is not an event worth auditing.
_SYNC_ONLY_COLUMNS = {
    "fixed_assets": {"wialon_last_sync", "wialon_online", "wialon_speed", "updated_at"},
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
    auth_source: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    details: dict[str, Any] = {"status_code": status_code}
    if auth_source is not None:
        details["auth_source"] = auth_source
    if extra:
        details.update(_safe_fields(extra))
    session.add(
        AuditLog(
            action=action,
            actor_type="user" if actor_id else "anonymous",
            actor_user_id=actor_id,
            actor_name=actor_name,
            module="auth",
            route=route,
            details=details,
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
            if (
                not redacted_fields_count
                and session.info.get("audit_actor_type", "system") == "system"
                and (
                    set(changes) <= _SYNC_ONLY_COLUMNS.get(table_name, set())
                    # the mileage delta of a pull is already recorded in mileage_history
                    or (table_name == "fixed_assets" and set(changes) <= _SYNC_ONLY_COLUMNS["fixed_assets"] | {"mileage"})
                    or table_name == "wialon_settings"
                )
            ):
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


def _telemetry_predicate() -> str:
    """SQL condition for audit rows that only mirror automatic feeds (the tables themselves are the record).

    Built from module constants only (no user input). A row is telemetry when the system wrote it and it is either
    a copy of an append-only feed table, a Wialon-settings counter update, or a fixed-asset update that touched
    nothing but the live-sync columns / the mileage delta (that delta is already kept in `mileage_history`).
    """
    feeds = ", ".join(f"'{name}'" for name in sorted(_OPERATIONAL_TABLES - {"audit_logs"}))
    sync_columns = ", ".join(f"'{name}'" for name in sorted(_SYNC_ONLY_COLUMNS["fixed_assets"] | {"mileage"}))
    return (
        "actor_type = 'system' AND ("
        f"object_type IN ({feeds}) "
        "OR (object_type = 'wialon_settings' AND action = 'update') "
        "OR (object_type = 'fixed_assets' AND action = 'update' AND new_values IS NOT NULL "
        "AND jsonb_typeof(new_values) = 'object' "
        f"AND NOT EXISTS (SELECT 1 FROM jsonb_object_keys(new_values) AS k WHERE k NOT IN ({sync_columns}))))"
    )


async def purge_audit_telemetry(*, apply: bool, batch_size: int = 50_000) -> dict[str, Any]:
    """Remove the telemetry audit rows written before the noise filters existed. Dry-run unless `apply`."""
    from sqlalchemy import text

    predicate = _telemetry_predicate()
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                text(f"SELECT module, object_type, count(*) FROM audit_logs WHERE {predicate} GROUP BY 1, 2 ORDER BY 3 DESC")
            )
        ).all()
        total = (await session.execute(text("SELECT count(*) FROM audit_logs"))).scalar_one()
    report: dict[str, Any] = {
        "audit_rows_total": total,
        "telemetry_rows": sum(row[2] for row in rows),
        "by_type": [{"module": row[0], "object_type": row[1], "rows": row[2]} for row in rows],
        "applied": apply,
        "deleted": 0,
    }
    if not apply:
        return report
    deleted = 0
    while True:
        async with SessionFactory() as session:
            result = await session.execute(
                text(
                    "DELETE FROM audit_logs WHERE id IN "
                    f"(SELECT id FROM audit_logs WHERE {predicate} LIMIT :batch)"
                ),
                {"batch": batch_size},
            )
            await session.commit()
        removed = result.rowcount or 0
        deleted += removed
        if removed < batch_size:
            break
    report["deleted"] = deleted
    return report


async def delete_expired_audit_logs() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audit_retention_days)
    async with SessionFactory() as session:
        result = await session.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        )
        await session.commit()
        return result.rowcount or 0


@event.listens_for(Session, "after_rollback")
def _discard_pending_audit_changes(session: Session) -> None:
    session.info.pop(_AUDIT_PENDING, None)


async def delete_expired_positions() -> int:
    from sqlalchemy import delete

    from app.models.position_history import AssetPositionHistory

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.position_history_retention_days)
    async with SessionFactory() as session:
        result = await session.execute(delete(AssetPositionHistory).where(AssetPositionHistory.at < cutoff))
        await session.commit()
        return result.rowcount or 0


async def run_audit_retention() -> None:
    while True:
        try:
            deleted = await delete_expired_audit_logs()
            if deleted:
                logger.info("Audit retention removed %s expired events", deleted)
            purged = await delete_expired_positions()
            if purged:
                logger.info("Position history retention removed %s old points", purged)
        except SQLAlchemyError as exc:
            logger.error("Audit retention cleanup failed (%s)", type(exc).__name__)
        await asyncio.sleep(24 * 60 * 60)
