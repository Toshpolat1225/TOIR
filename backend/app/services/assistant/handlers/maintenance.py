"""to.overdue, to.schedule, to.next: read the maintenance schedule through the maintenance service (master: his section)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.maintenance import WorkType
from app.schemas.assistant import Card, CardItem
from app.services import maintenance as maintenance_service
from app.services.assistant.handlers._common import clarify, entity_for, error_card, need_asset, not_found, t, text_card
from app.services.assistant.registry import handler
from app.services.assistant.types import Ctx, Result, Slots

DISPLAY_STATUS = {"overdue": ("muddati o'tgan", "просрочено"), "upcoming": ("rejada", "запланировано"), "in_progress": ("jarayonda", "в работе"), "completed": ("bajarilgan", "выполнено")}


def _month(ctx: Ctx) -> str:
    return (ctx.now + timedelta(hours=settings.gtk_utc_offset_hours)).strftime("%Y-%m")


def _item(ctx: Ctx, i) -> CardItem:
    status = DISPLAY_STATUS.get(i.status, (i.status, i.status))
    remaining = ""
    if i.remainingKm is not None:
        remaining = t(ctx, f" · qoldi {float(i.remainingKm):.0f} km", f" · осталось {float(i.remainingKm):.0f} км")
    return CardItem(
        label=i.unit, sub=f"{i.type} · {i.startDate:%d.%m}{remaining}", value=t(ctx, *status),
        tone="bad" if i.status == "overdue" else ("info" if i.status == "in_progress" else None), href="/dashboard/maintenance",
    )


async def _schedule(ctx: Ctx):
    try:
        return await maintenance_service.get_schedule(ctx.db, ctx.user, _month(ctx))
    except HTTPException as exc:
        return exc


@handler("to.overdue")
async def overdue(ctx: Ctx, slots: Slots) -> Result:
    result = await _schedule(ctx)
    if isinstance(result, HTTPException):
        return error_card(ctx, result)
    items = [i for i in result.schedule if i.status == "overdue" and (slots.section_id is None or i.section_id == slots.section_id)]
    if not items:
        msg = t(ctx, "Muddati o'tgan ТО yo'q.", "Просроченных ТО нет.")
        return Result(cards=[text_card(msg, tone="ok")], speak=msg)
    items.sort(key=lambda i: (i.startDate, i.unit))
    card = Card(kind="list", title=t(ctx, f"Muddati o'tgan ТО: {len(items)} ta", f"Просроченные ТО: {len(items)}"), tone="bad", items=[_item(ctx, i) for i in items[:12]], href="/dashboard/maintenance")
    speak = t(ctx, f"{len(items)} ta texnik xizmatning muddati o'tgan; eng eskisi {items[0].unit}.", f"Просрочено ТО: {len(items)}; самое давнее — {items[0].unit}.")
    return Result(cards=[card], speak=speak)


@handler("to.schedule")
async def schedule(ctx: Ctx, slots: Slots) -> Result:
    result = await _schedule(ctx)
    if isinstance(result, HTTPException):
        return error_card(ctx, result)
    items = [i for i in result.schedule if i.status != "completed" and (slots.section_id is None or i.section_id == slots.section_id)]
    if not items:
        msg = t(ctx, "Bu oy uchun ТО rejalari yo'q.", "На этот месяц ТО не запланировано.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg)
    over = sum(1 for i in items if i.status == "overdue")
    card = Card(kind="list", title=t(ctx, f"ТО jadvali ({_month(ctx)}): {len(items)} ta", f"График ТО ({_month(ctx)}): {len(items)}"), tone="info", items=[_item(ctx, i) for i in items[:12]], href="/dashboard/maintenance")
    speak = t(ctx, f"Bu oy {len(items)} ta ТО, shundan {over} tasi muddati o'tgan.", f"В этом месяце ТО: {len(items)}, из них просрочено {over}.")
    return Result(cards=[card], speak=speak)


@handler("to.next")
async def next_to(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    result = await _schedule(ctx)
    if isinstance(result, HTTPException):
        return error_card(ctx, result)
    mine = sorted((i for i in result.schedule if i.asset_id == asset.id and i.status != "completed"), key=lambda i: i.startDate)
    if not mine:
        unforecasted = next((u for u in result.unforecasted if getattr(u, "asset_id", None) == asset.id), None)
        why = ""
        if unforecasted is not None and getattr(unforecasted, "reason", None):
            why = f" ({unforecasted.reason})"
        msg = t(ctx, f"{asset.inv_number} uchun bu oyda ТО rejasi yo'q{why}.", f"Для {asset.inv_number} в этом месяце ТО не запланировано{why}.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg, entities=entity_for(asset))
    first = mine[0]
    card = Card(kind="list", title=f"{asset.inv_number} · " + t(ctx, "keyingi ТО", "следующее ТО"), tone="info", items=[_item(ctx, i) for i in mine[:5]], href="/dashboard/maintenance")
    speak = t(ctx, f"{asset.inv_number} keyingi ТО: {first.type}, {first.startDate:%d.%m}.", f"Следующее ТО {asset.inv_number}: {first.type}, {first.startDate:%d.%m}.")
    return Result(cards=[card], speak=speak, entities=entity_for(asset))


@handler("to.types")
async def types(ctx: Ctx, slots: Slots) -> Result:
    """The kinds of maintenance / repair work the system knows (the work types directory)."""
    rows = (await ctx.db.execute(select(WorkType).order_by(WorkType.unit_type, WorkType.sort_order, WorkType.name).limit(40))).scalars().all()
    if not rows:
        msg = t(ctx, "Ish turlari kiritilmagan.", "Виды работ не заведены.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg)
    kind = {"locomotive": t(ctx, "lokomotiv", "локомотив"), "wagon": t(ctx, "vagon", "вагон")}
    items = [CardItem(label=r.name, sub=kind.get(r.unit_type, r.unit_type), value=r.code, href="/dashboard/maintenance") for r in rows]
    card = Card(kind="list", title=t(ctx, f"ТО va ta'mir turlari: {len(rows)} ta", f"Виды ТО и ремонта: {len(rows)}"), tone="info", items=items, href="/dashboard/maintenance")
    return Result(cards=[card], speak=t(ctx, f"{len(rows)} ta tur bor.", f"Видов работ: {len(rows)}."))
