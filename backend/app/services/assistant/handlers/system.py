"""sys.help (what can be said, filtered by the user's permissions) and sys.sync_status (Wialon, GTK, GTK GPS freshness)."""
from __future__ import annotations

from app.core.permissions import user_has_permission
from app.schemas.assistant import Card, CardItem, CardRow
from app.services import gps_overview
from app.services import gtk as gtk_service
from app.services import wialon as wialon_service
from app.services.assistant.catalog import CATALOG, MODULE_TITLES
from app.services.assistant.handlers._common import age_minutes, ago, t, text_card
from app.services.assistant.registry import handler
from app.services.assistant.types import Ctx, Result, Slots


@handler("sys.bye")
async def bye(ctx: Ctx, slots: Slots) -> Result:
    msg = t(ctx, "Marhamat! Kerak bo'lsam, chaqiring.", "Пожалуйста! Обращайтесь, когда нужно.")
    return Result(cards=[text_card(msg, tone="info")], speak=msg)


@handler("sys.help")
async def help_(ctx: Ctx, slots: Slots) -> Result:
    groups: dict[str, list[CardItem]] = {}
    for intent in CATALOG:
        if intent.permission and not await user_has_permission(ctx.db, ctx.user, intent.permission):
            continue
        examples = intent.examples_uz if ctx.locale == "uz" else intent.examples_ru
        if not examples:
            continue
        groups.setdefault(intent.module, []).append(CardItem(label=examples[0], sub=t(ctx, intent.title_uz, intent.title_ru) + (t(ctx, " (tasdiq bilan)", " (с подтверждением)") if intent.write else "")))
    cards = [Card(kind="help", title=MODULE_TITLES.get(module, module), items=items) for module, items in groups.items()]
    msg = t(ctx, "Mana nimalarni ayta olasiz. Yozuvchi amallar har doim tasdiq so'raydi.", "Вот что можно сказать. Действия с записью всегда требуют подтверждения.")
    return Result(cards=cards, speak=msg)


@handler("sys.sync_status")
async def sync_status(ctx: Ctx, slots: Slots) -> Result:
    rows: list[CardRow] = []
    wialon = await wialon_service.get_sync_status(ctx.db)
    w_age = age_minutes(ctx, wialon.last_sync_at)
    rows.append(CardRow(label="Wialon", value=(ago(ctx, w_age) + f" · {wialon.last_sync_status or '—'}") if wialon.last_sync_at else t(ctx, "hali yangilanmagan", "ещё не обновлялся"), tone="ok" if (w_age is not None and w_age < 30) else "warn"))
    if await user_has_permission(ctx.db, ctx.user, "gtk.view"):
        status = await gtk_service.get_status(ctx.db)
        run = status.get("last_run")
        g_age = age_minutes(ctx, run.started_at) if run else None
        rows.append(CardRow(label="GTK", value=(ago(ctx, g_age) + f" · {run.status}") if run else t(ctx, "hali yangilanmagan", "ещё не обновлялся"), tone="ok" if (g_age is not None and g_age < 30) else "warn"))
    feed = await gps_overview._feed(ctx.db)
    gps_age = age_minutes(ctx, feed.gtk_last_run_at)
    rows.append(CardRow(label="GTK GPS", value=(ago(ctx, gps_age) + f" · {feed.gtk_last_status or '—'}") if feed.gtk_last_run_at else t(ctx, "o'chiq yoki hali ishlamagan", "выключен или ещё не работал"),
                        tone="ok" if (gps_age is not None and gps_age < 30 and feed.gtk_last_status in ("success", "partial")) else "warn"))
    card = Card(kind="metric", title=t(ctx, "Sinxron holati", "Статус синхронизации"), rows=rows)
    stale = [r.label for r in rows if r.tone == "warn"]
    speak = t(ctx, "Hammasi yangi." if not stale else f"Eskirgan: {', '.join(stale)}.", "Всё свежее." if not stale else f"Устарели: {', '.join(stale)}.")
    return Result(cards=[card], speak=speak)
