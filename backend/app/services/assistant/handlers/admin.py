"""admin.audit_recent: the last audit events (administrator only; re-checked here, not only by the parser)."""
from __future__ import annotations

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.schemas.assistant import Card, CardItem
from app.services.assistant.handlers._common import denied, t, text_card
from app.services.assistant.registry import handler
from app.services.assistant.types import Ctx, Result, Slots


@handler("admin.audit_recent")
async def audit_recent(ctx: Ctx, slots: Slots) -> Result:
    if ctx.user.role != "admin":
        return denied(ctx)
    rows = (await ctx.db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10))).scalars().all()
    if not rows:
        msg = t(ctx, "Audit hodisalari yo'q.", "Событий аудита нет.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg)
    items = [
        CardItem(label=f"{r.action} · {r.module}", sub=f"{r.actor_name or '—'} · {r.object_label or r.object_type or ''}", value=r.created_at.strftime("%d.%m %H:%M"), href="/dashboard/admin/audit-logs")
        for r in rows
    ]
    card = Card(kind="list", title=t(ctx, "Oxirgi audit hodisalari", "Последние события аудита"), tone="info", items=items, href="/dashboard/admin/audit-logs")
    last = rows[0]
    return Result(cards=[card], speak=t(ctx, f"Oxirgisi: {last.action}, {last.actor_name or 'noma`lum'}.", f"Последнее: {last.action}, {last.actor_name or 'неизвестно'}."))
