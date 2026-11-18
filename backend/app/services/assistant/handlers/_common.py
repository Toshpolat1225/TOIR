"""Shared helpers of the handlers: two-language strings, number formatting, asset resolution with scope, error cards."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from app.schemas.assistant import Card, CardItem, CardRow, EntityRef, Suggestion
from app.services import assets as assets_service
from app.services.assistant.types import AssetRef, Ctx, Result, Slots

TYPE_NAMES = {
    "locomotive": ("Lokomotiv (elektrovoz)", "Локомотив (электровоз)"),
    "diesel": ("Teplovoz", "Тепловоз"),
    "special_self_propelled": ("Maxsus o'ziyurar", "Спецсамоходный"),
    "wagon": ("Vagon-samosval", "Вагон-самосвал"),
    "tank_car": ("Sisterna", "Цистерна"),
    "platform": ("Platforma", "Платформа"),
}


def t(ctx: Ctx, uz: str, ru: str) -> str:
    """Every user-facing string exists in both languages; the user's language wins."""
    return uz if ctx.locale == "uz" else ru


def type_name(ctx: Ctx, asset_type: str | None) -> str:
    if not asset_type:
        return "—"
    pair = TYPE_NAMES.get(asset_type)
    return t(ctx, pair[0], pair[1]) if pair else asset_type


def km(metres: float | int | Decimal | None, places: int = 1) -> str:
    if metres is None:
        return "—"
    return f"{float(metres) / 1000:,.{places}f}".replace(",", " ") + " km"


def km_value(value: float | int | Decimal | None, places: int = 1) -> str:
    """A value that is already in kilometres."""
    if value is None:
        return "—"
    return f"{float(value):,.{places}f}".replace(",", " ") + " km"


def tonnes(value: float | int | Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.1f}".replace(",", " ") + " t"


def ago(ctx: Ctx, minutes: float | None) -> str:
    if minutes is None:
        return "—"
    if minutes < 1:
        return t(ctx, "hozirgina", "только что")
    if minutes < 90:
        return t(ctx, f"{minutes:.0f} daq. oldin", f"{minutes:.0f} мин назад")
    hours = minutes / 60
    if hours < 48:
        return t(ctx, f"{hours:.0f} soat oldin", f"{hours:.0f} ч назад")
    return t(ctx, f"{hours / 24:.0f} kun oldin", f"{hours / 24:.0f} дн назад")


def age_minutes(ctx: Ctx, at: datetime | None) -> float | None:
    if at is None:
        return None
    aware = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return max(0.0, (ctx.now - aware).total_seconds() / 60)


def text_card(title: str, subtitle: str | None = None, *, tone: str | None = None, kind: str = "text", rows: list[CardRow] | None = None) -> Card:
    return Card(kind=kind, title=title, subtitle=subtitle, tone=tone, rows=rows or [])  # type: ignore[arg-type]


def clarify(ctx: Ctx, uz: str, ru: str, suggestions: list[str] | None = None) -> Result:
    """The command lacks something (an asset, a number, a text): say what and keep the conversation open."""
    card = Card(kind="text", title=t(ctx, uz, ru), tone="info")
    if suggestions:
        card.items = [CardItem(label=s) for s in suggestions]
    return Result(cards=[card], speak=t(ctx, uz, ru), status="needs_clarification")


def not_found(ctx: Ctx, what_uz: str = "Topilmadi", what_ru: str = "Не найдено") -> Result:
    """The same answer for a missing object and for another section's object (nothing is revealed)."""
    return Result(cards=[Card(kind="error", title=t(ctx, what_uz, what_ru), tone="bad")], speak=t(ctx, what_uz, what_ru), status="error")


def denied(ctx: Ctx) -> Result:
    msg = t(ctx, "Bu amal uchun ruxsatingiz yo'q.", "Для этого действия у вас нет прав.")
    return Result(cards=[Card(kind="error", title=msg, tone="bad")], speak=msg, status="denied")


def error_card(ctx: Ctx, exc: HTTPException) -> Result:
    """A service refused (409 transition, 422 validation, 403 scope): show its message as a card."""
    if exc.status_code == 404:
        return not_found(ctx)
    if exc.status_code == 403:
        return denied(ctx)
    detail = exc.detail if isinstance(exc.detail, str) else t(ctx, "So'rov bajarilmadi.", "Запрос не выполнен.")
    return Result(cards=[Card(kind="error", title=t(ctx, "Bajarilmadi", "Не выполнено"), subtitle=detail, tone="bad")], speak=t(ctx, "Bajarilmadi: ", "Не выполнено: ") + detail, status="error")


def asset_row_card(ctx: Ctx, asset: AssetRef, *, kind: str | None = None, extra: list[CardRow] | None = None, href: str | None = None, title_suffix: str = "") -> Card:
    card_kind = kind or ("asset" if asset.is_locomotive else "wagon")
    return Card(
        kind=card_kind,  # type: ignore[arg-type]
        title=f"{asset.inv_number}{title_suffix}",
        subtitle=" · ".join(x for x in (type_name(ctx, asset.asset_type), asset.model_name, asset.section_name) if x) or None,
        rows=[CardRow(label=t(ctx, "Nomi", "Название"), value=asset.name)] + (extra or []),
        href=href or asset_href(asset),
    )


def asset_href(asset: AssetRef) -> str:
    return f"/dashboard/gps/{asset.id}" if asset.is_locomotive else f"/dashboard/gps/wagons/{asset.id}"


def card_href(asset: AssetRef) -> str:
    return f"/dashboard/directories/assets?q={asset.inv_number}"


def verify_scope(ctx: Ctx, asset: AssetRef) -> bool:
    """A master sees only his own section: another section's asset is "not found" (the parser scopes the lookup too; this is the second lock)."""
    scope = ctx.master_section_id
    return scope is None or asset.section_id == scope


def _from_read(read: Any) -> AssetRef:
    return AssetRef(
        id=read.id, inv_number=read.inv_number, name=read.name, asset_type=str(read.asset_type), section_id=read.section_id,
        gtk_id=int(read.gtk_id) if getattr(read, "gtk_id", None) and str(read.gtk_id).isdigit() else None,
    )


async def asset_from_context(ctx: Ctx) -> AssetRef | None:
    """The asset of the open page or the last answer ("bu lokomotiv")."""
    c = ctx.context
    asset_id = c.asset_id if c else None
    if asset_id is None and c and c.last_entity and c.last_entity.kind == "asset":
        try:
            from uuid import UUID

            asset_id = UUID(c.last_entity.id)
        except ValueError:
            return None
    if asset_id is None:
        return None
    try:
        return _from_read(await assets_service.get_fixed_asset(ctx.db, asset_id, master_section_id=ctx.master_section_id))
    except HTTPException:
        return None


async def need_asset(ctx: Ctx, slots: Slots, *, use_context: bool = True) -> tuple[AssetRef | None, Result | None]:
    """(asset, None) when one asset is known, else (None, the Result that asks / lists the candidates)."""
    if slots.asset is not None:
        if not verify_scope(ctx, slots.asset):
            return None, not_found(ctx, "Texnika topilmadi", "Техника не найдена")
        return slots.asset, None
    if slots.assets:
        items = [
            CardItem(label=a.inv_number, sub=f"{type_name(ctx, a.asset_type)} · {a.name}", entity=a.entity(), href=card_href(a))
            for a in slots.assets
            if verify_scope(ctx, a)
        ]
        title = t(ctx, "Qaysi birini nazarda tutyapsiz?", "Какую именно вы имеете в виду?")
        return None, Result(cards=[Card(kind="list", title=title, tone="info", items=items)], speak=title, status="needs_clarification")
    if use_context:
        found = await asset_from_context(ctx)
        if found is not None:
            return found, None
    return None, clarify(ctx, "Qaysi texnika? Inventar raqamini ayting.", "Какая техника? Назовите инвентарный номер.", ["37919", "35656"])


def suggest(*texts: str) -> list[Suggestion]:
    return [Suggestion(text=x) for x in texts]


def entity_for(asset: AssetRef) -> list[EntityRef]:
    return [asset.entity()]


def tone_for_status(value: str | None) -> str | None:
    return {"ok": "ok", "warn": "warn", "bad": "bad"}.get(value or "")
