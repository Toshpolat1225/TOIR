"""Work orders: counts, lists, and the three confirmed writes (create, set status, comment). Reads go through the work order service (master: his section);
a write intent only builds a PendingAction; the executor re-checks scope and permission and calls the same service the UI uses. Nothing deletes."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.permissions import user_has_permission
from app.models.maintenance import WorkType
from app.models.organization import Employee
from app.schemas.assistant import Card, CardItem, CardRow, EntityRef
from app.schemas.work_orders import WorkOrderCreate, WorkOrderRepairInput, WorkOrderUpdate
from app.services import work_orders as wo_service
from app.services.assistant.handlers._common import (
    asset_from_context, clarify, denied, entity_for, error_card, need_asset, not_found, t, text_card,
)
from app.services.assistant.registry import action, handler
from app.services.assistant.types import AssetRef, Ctx, PendingAction, Result, Slots

STATUS_NAMES = {
    "pending": ("kutilmoqda", "ожидает"), "in_progress": ("jarayonda", "в работе"), "completed": ("bajarildi", "выполнен"), "cancelled": ("bekor qilindi", "отменён"),
}
ALLOWED = {"pending": {"in_progress", "cancelled"}, "in_progress": {"completed", "cancelled"}}
DEFAULT_DESCRIPTION = ("Naryad (ovoz/matn)", "Наряд (голос/текст)")


def status_text(ctx: Ctx, status: str) -> str:
    pair = STATUS_NAMES.get(status, (status, status))
    return t(ctx, *pair)


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


async def _list(ctx: Ctx, *, status_filter: str | None = None, open_only: bool = False, section_id: UUID | None = None, asset_id: UUID | None = None, q: str | None = None, limit: int = 10):
    return await wo_service.list_orders(
        ctx.db, ctx.user, status_filter=status_filter, open_only=open_only, section_id=section_id, department_id=None, fixed_asset_id=asset_id, executor_id=None,
        work_type_id=None, material_q=None, date_from=None, date_to=None, q=q, limit=limit, offset=0, sort_by="created_at", sort_order="desc",
    )


def _item(ctx: Ctx, o) -> CardItem:
    return CardItem(
        label=o.number, sub=f"{o.asset_inv_number} · {o.description[:80]}", value=status_text(ctx, o.status) + (t(ctx, " · kechikkan", " · просрочен") if o.is_overdue else ""),
        tone="bad" if o.is_overdue else ("info" if o.status == "in_progress" else None), href="/dashboard/work-orders",
        entity=EntityRef(kind="work_order", id=str(o.id), label=o.number),
    )


# ---- reads -------------------------------------------------------------------------------------------------
@handler("wo.count")
async def count(ctx: Ctx, slots: Slots) -> Result:
    try:
        counts: dict[str, int] = {}
        for status in ("pending", "in_progress"):
            _items, total = await _list(ctx, status_filter=status, section_id=slots.section_id, limit=1)
            counts[status] = total
        _done, completed = await _list(ctx, status_filter="completed", section_id=slots.section_id, limit=1)
    except HTTPException as exc:
        return error_card(ctx, exc)
    open_total = counts["pending"] + counts["in_progress"]
    rows = [
        CardRow(label=t(ctx, "Ochiq", "Открытых"), value=str(open_total), tone="warn" if open_total else "ok"),
        CardRow(label=status_text(ctx, "pending"), value=str(counts["pending"])),
        CardRow(label=status_text(ctx, "in_progress"), value=str(counts["in_progress"])),
        CardRow(label=t(ctx, "Bajarilgan (jami)", "Выполнено (всего)"), value=str(completed)),
    ]
    card = Card(kind="metric", title=t(ctx, "Naryadlar soni", "Количество нарядов"), rows=rows, href="/dashboard/work-orders")
    speak = t(ctx, f"Ochiq naryadlar {open_total} ta: {counts['pending']} kutilmoqda, {counts['in_progress']} jarayonda.", f"Открытых нарядов {open_total}: ожидают {counts['pending']}, в работе {counts['in_progress']}.")
    return Result(cards=[card], speak=speak)


@handler("wo.list")
async def list_(ctx: Ctx, slots: Slots) -> Result:
    """The section/global list (open orders by default, or the status asked for); the orders of ONE asset are `wo.by_asset`."""
    try:
        orders, total = await _list(ctx, status_filter=slots.status if slots.status in STATUS_NAMES else None, open_only=slots.status not in STATUS_NAMES, section_id=slots.section_id, limit=10)
    except HTTPException as exc:
        return error_card(ctx, exc)
    if not orders:
        msg = t(ctx, "Mos naryad topilmadi.", "Подходящих нарядов нет.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg)
    card = Card(kind="list", title=t(ctx, f"Naryadlar: {total} ta", f"Наряды: {total}"), tone="info", items=[_item(ctx, o) for o in orders], href="/dashboard/work-orders")
    speak = t(ctx, f"{total} ta naryad topildi; oxirgisi {orders[0].number}.", f"Найдено нарядов: {total}; последний {orders[0].number}.")
    return Result(cards=[card], speak=speak, entities=[EntityRef(kind="work_order", id=str(orders[0].id), label=orders[0].number)])


@handler("wo.by_asset")
async def by_asset(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    try:
        orders, total = await _list(ctx, asset_id=asset.id, limit=10)  # every status, newest first (the service scopes a master)
    except HTTPException as exc:
        return error_card(ctx, exc)
    if not orders:
        msg = t(ctx, f"{asset.inv_number} bo'yicha naryad yo'q.", f"По {asset.inv_number} нарядов нет.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg, entities=entity_for(asset))
    open_n = sum(1 for o in orders if o.status in ("pending", "in_progress"))
    card = Card(kind="list", title=f"{asset.inv_number} · " + t(ctx, f"naryadlar: {total} ta", f"наряды: {total}"), tone="info", items=[_item(ctx, o) for o in orders], href="/dashboard/work-orders")
    speak = t(ctx, f"{asset.inv_number} bo'yicha {total} ta naryad, ochiq: {open_n}.", f"По {asset.inv_number} нарядов: {total}, открытых: {open_n}.")
    return Result(cards=[card], speak=speak, entities=entity_for(asset))


# ---- finding an order by the number the user said ------------------------------------------------------------
async def _find_order(ctx: Ctx, number: str | None) -> tuple[Any | None, Result | None]:
    digits = _digits(number)
    if len(digits) < 3:
        return None, clarify(ctx, "Naryad raqamini ayting (kamida 3 ta raqam).", "Назовите номер наряда (минимум 3 цифры).", ["naryad 153045"])
    try:
        orders, _total = await _list(ctx, q=digits, limit=50)
        if not orders:  # the number may be spoken without its leading part: also search by the tail only
            orders, _total = await _list(ctx, q=None, limit=200)
    except HTTPException as exc:
        return None, error_card(ctx, exc)
    exact = [o for o in orders if _digits(o.number) == digits]
    tail = [o for o in orders if _digits(o.number).endswith(digits)]
    found = exact or tail
    if not found:
        return None, not_found(ctx, "Bunday naryad topilmadi", "Такой наряд не найден")
    if len(found) > 1:
        title = t(ctx, "Bir nechta naryad mos keldi: qaysi biri?", "Подходит несколько нарядов: какой именно?")
        return None, Result(cards=[Card(kind="list", title=title, tone="info", items=[_item(ctx, o) for o in found[:8]])], speak=title, status="needs_clarification")
    return found[0], None


def _pending(ctx: Ctx, kind: str, payload: dict[str, Any], summary_uz: str, summary_ru: str, *, title_uz: str, title_ru: str, entity: list[EntityRef], risk: str = "low") -> Result:
    summary = t(ctx, summary_uz, summary_ru)
    card = Card(kind="confirm", title=t(ctx, title_uz, title_ru), subtitle=summary, tone="warn", rows=[CardRow(label=t(ctx, "Amal", "Действие"), value=summary)])
    return Result(cards=[card], speak=summary + t(ctx, " Tasdiqlaysizmi?", " Подтверждаете?"), pending=PendingAction(kind=kind, payload=payload, summary=summary, risk=risk), entities=entity)  # type: ignore[arg-type]


# ---- wo.create -----------------------------------------------------------------------------------------------
async def _pick_executor(ctx: Ctx, section_id: UUID) -> Employee | None:
    rows = (await ctx.db.execute(select(Employee).where(Employee.section_id == section_id, Employee.is_active.is_(True)).order_by(Employee.full_name).limit(1))).scalars().all()
    return rows[0] if rows else None


async def _pick_work_type(ctx: Ctx, description: str) -> WorkType | None:
    words = [w for w in re.findall(r"\w{4,}", description.lower())]
    all_types = (await ctx.db.execute(select(WorkType).order_by(WorkType.sort_order, WorkType.name))).scalars().all()
    for w in words:
        for wt in all_types:
            if w in wt.name.lower() or w in wt.code.lower():
                return wt
    return all_types[0] if all_types else None


@handler("wo.create")
async def create(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    if not await user_has_permission(ctx.db, ctx.user, "work_orders.create"):
        return denied(ctx)
    if asset.section_id is None:
        return clarify(ctx, f"{asset.inv_number} uchastkaga biriktirilmagan: naryad ochib bo'lmaydi.", f"{asset.inv_number} не привязан к участку: наряд создать нельзя.")
    if ctx.master_section_id is not None and asset.section_id != ctx.master_section_id:
        return not_found(ctx, "Texnika topilmadi", "Техника не найдена")
    description = (slots.text or "").strip() or t(ctx, *DEFAULT_DESCRIPTION)
    executor = await _pick_executor(ctx, asset.section_id)
    if executor is None:
        return clarify(ctx, "Uchastkada faol ijrochi yo'q: naryadni sahifadan oching.", "На участке нет активного исполнителя: создайте наряд на странице.")
    work_type = await _pick_work_type(ctx, description)
    if work_type is None:
        return clarify(ctx, "Ish turlari ma'lumotnomasi bo'sh: naryadni sahifadan oching.", "Справочник видов работ пуст: создайте наряд на странице.")
    payload = {"asset_id": str(asset.id), "description": description, "executor_id": str(executor.id), "work_type_id": str(work_type.id), "order_kind": "unplanned", "priority": "normal"}
    return _pending(
        ctx, "wo.create", payload,
        f"Naryad ochish: {asset.inv_number} · {description} · ijrochi {executor.full_name} · ish turi {work_type.name}.",
        f"Создать наряд: {asset.inv_number} · {description} · исполнитель {executor.full_name} · вид работ {work_type.name}.",
        title_uz="Naryad ochishni tasdiqlang", title_ru="Подтвердите создание наряда", entity=entity_for(asset),
    )


@action("wo.create")
async def create_confirmed(ctx: Ctx, payload: dict[str, Any]) -> Result:
    if not await user_has_permission(ctx.db, ctx.user, "work_orders.create"):
        return denied(ctx)
    try:
        body = WorkOrderCreate(
            fixed_asset_id=UUID(payload["asset_id"]), order_kind=payload.get("order_kind", "unplanned"), priority=payload.get("priority", "normal"),
            executor_id=UUID(payload["executor_id"]), description=payload["description"],
            repairs=[WorkOrderRepairInput(work_type_id=UUID(payload["work_type_id"]))],
        )
        created = await wo_service.create_order(ctx.db, ctx.user, body)  # re-checks the master's section and every business rule
    except HTTPException as exc:
        return error_card(ctx, exc)
    card = Card(
        kind="text", title=t(ctx, f"Naryad ochildi: {created.number}", f"Наряд создан: {created.number}"), tone="ok", href="/dashboard/work-orders",
        rows=[CardRow(label=t(ctx, "Texnika", "Техника"), value=created.asset_inv_number), CardRow(label=t(ctx, "Holati", "Статус"), value=status_text(ctx, created.status))],
    )
    return Result(cards=[card], speak=t(ctx, f"Naryad {created.number} ochildi.", f"Наряд {created.number} создан."), entities=[EntityRef(kind="work_order", id=str(created.id), label=created.number)])


# ---- wo.set_status -------------------------------------------------------------------------------------------
@handler("wo.set_status")
async def set_status(ctx: Ctx, slots: Slots) -> Result:
    if not await user_has_permission(ctx.db, ctx.user, "work_orders.update"):
        return denied(ctx)
    if slots.status not in STATUS_NAMES:
        return clarify(ctx, "Qaysi holatga o'tkazay: jarayonda, bajarildi yoki bekor?", "В какой статус перевести: в работе, выполнен или отменён?", ["jarayonda", "bajarildi", "bekor"])
    order, ask = await _find_order(ctx, slots.work_order)
    if order is None:
        return ask  # type: ignore[return-value]
    if order.status == slots.status:
        msg = t(ctx, f"{order.number} allaqachon «{status_text(ctx, order.status)}» holatida.", f"{order.number} уже в статусе «{status_text(ctx, order.status)}».")
        return Result(cards=[text_card(msg, tone="info")], speak=msg, entities=[EntityRef(kind="work_order", id=str(order.id), label=order.number)])
    if slots.status not in ALLOWED.get(order.status, set()):
        msg = t(ctx, f"{order.number}: «{status_text(ctx, order.status)}» holatidan «{status_text(ctx, slots.status)}» holatiga o'tib bo'lmaydi.",
                f"{order.number}: переход «{status_text(ctx, order.status)}» → «{status_text(ctx, slots.status)}» недопустим.")
        return Result(cards=[Card(kind="error", title=msg, tone="bad")], speak=msg, status="error")
    return _pending(
        ctx, "wo.set_status", {"order_id": str(order.id), "status": slots.status},
        f"Naryad {order.number}: {status_text(ctx, order.status)} → {status_text(ctx, slots.status)}.", f"Наряд {order.number}: {status_text(ctx, order.status)} → {status_text(ctx, slots.status)}.",
        title_uz="Holatni o'zgartirishni tasdiqlang", title_ru="Подтвердите смену статуса", entity=[EntityRef(kind="work_order", id=str(order.id), label=order.number)],
        risk="medium" if slots.status == "cancelled" else "low",
    )


@action("wo.set_status")
async def set_status_confirmed(ctx: Ctx, payload: dict[str, Any]) -> Result:
    if not await user_has_permission(ctx.db, ctx.user, "work_orders.update"):
        return denied(ctx)
    try:
        order_id = UUID(payload["order_id"])
        await wo_service.get_order(ctx.db, ctx.user, order_id)  # 404 for another section's order
        updated = await wo_service.update_order(ctx.db, ctx.user, order_id, WorkOrderUpdate(status=payload["status"]))
    except HTTPException as exc:
        return error_card(ctx, exc)
    msg = t(ctx, f"Naryad {updated.number}: {status_text(ctx, updated.status)}.", f"Наряд {updated.number}: {status_text(ctx, updated.status)}.")
    return Result(cards=[Card(kind="text", title=msg, tone="ok", href="/dashboard/work-orders")], speak=msg, entities=[EntityRef(kind="work_order", id=str(updated.id), label=updated.number)])


# ---- wo.comment ----------------------------------------------------------------------------------------------
@handler("wo.comment")
async def comment(ctx: Ctx, slots: Slots) -> Result:
    if not await user_has_permission(ctx.db, ctx.user, "work_orders.update"):
        return denied(ctx)
    text = (slots.text or "").strip()
    if not text:
        return clarify(ctx, "Izoh matnini ayting.", "Продиктуйте текст комментария.")
    order, ask = await _find_order(ctx, slots.work_order)
    if order is None:
        return ask  # type: ignore[return-value]
    if order.status in ("completed", "cancelled"):
        msg = t(ctx, f"{order.number} yakunlangan: izoh qo'shib bo'lmaydi.", f"{order.number} завершён: комментарий добавить нельзя.")
        return Result(cards=[Card(kind="error", title=msg, tone="bad")], speak=msg, status="error")
    return _pending(
        ctx, "wo.comment", {"order_id": str(order.id), "text": text[:500]},
        f"Naryad {order.number} ga izoh: «{text[:120]}».", f"Комментарий к наряду {order.number}: «{text[:120]}».",
        title_uz="Izohni tasdiqlang", title_ru="Подтвердите комментарий", entity=[EntityRef(kind="work_order", id=str(order.id), label=order.number)],
    )


@action("wo.comment")
async def comment_confirmed(ctx: Ctx, payload: dict[str, Any]) -> Result:
    if not await user_has_permission(ctx.db, ctx.user, "work_orders.update"):
        return denied(ctx)
    try:
        order_id = UUID(payload["order_id"])
        current = await wo_service.get_order(ctx.db, ctx.user, order_id)
        stamp = (ctx.now + timedelta(hours=settings.gtk_utc_offset_hours)).strftime("%d.%m %H:%M")
        line = f"[{stamp} · {ctx.user.full_name or ctx.user.email}] {payload['text']}"
        note = f"{current.note}\n{line}" if current.note else line
        updated = await wo_service.update_order(ctx.db, ctx.user, order_id, WorkOrderUpdate(note=note))
    except HTTPException as exc:
        return error_card(ctx, exc)
    msg = t(ctx, f"Izoh {updated.number} ga qo'shildi.", f"Комментарий добавлен к наряду {updated.number}.")
    return Result(cards=[Card(kind="text", title=msg, tone="ok", href="/dashboard/work-orders")], speak=msg, entities=[EntityRef(kind="work_order", id=str(updated.id), label=updated.number)])
