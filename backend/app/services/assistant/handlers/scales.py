"""scales.today, scales.wagon: weighing results from the scales insight services (the section is closed to a master by the role rules)."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException

from app.schemas.assistant import Card, CardItem, CardRow
from app.services import scales_insights
from app.services.assistant.handlers._common import asset_row_card, entity_for, error_card, need_asset, not_found, t, text_card, tonnes
from app.services.assistant.registry import handler
from app.services.assistant.types import Ctx, Result, Slots

PERIOD_DAYS = {"today": 1, "yesterday": 2, "week": 7, "month": 30}
PERIOD_NAME = {"today": ("bugun", "сегодня"), "yesterday": ("kecha", "вчера"), "week": ("so'nggi 7 kun", "за 7 дней"), "month": ("so'nggi 30 kun", "за 30 дней")}


@handler("scales.today")
async def today(ctx: Ctx, slots: Slots) -> Result:
    period = slots.period if slots.period in PERIOD_DAYS else "today"
    try:
        overview = await scales_insights.overview(ctx.db, PERIOD_DAYS[period])
    except HTTPException as exc:
        return error_card(ctx, exc)
    name_uz, name_ru = PERIOD_NAME[period]
    if period == "yesterday":
        day = overview.date_to - timedelta(days=1)
        points = [d for d in overview.daily if d.day == day]
        trains, total = sum(d.trains for d in points), sum((d.tonnes for d in points), Decimal("0"))
        rows = [CardRow(label=t(ctx, "Sostavlar", "Составов"), value=str(trains), tone="ok"), CardRow(label=t(ctx, "Yuk", "Груз"), value=tonnes(total))]
    else:
        k = overview.kpi
        rows = [
            CardRow(label=t(ctx, "Sostavlar", "Составов"), value=str(k.trains), tone="ok"),
            CardRow(label=t(ctx, "Yuk", "Груз"), value=tonnes(k.tonnes), tone="ok"),
            CardRow(label=t(ctx, "Vagon reyslari", "Рейсов вагонов"), value=str(k.wagon_trips)),
            CardRow(label=t(ctx, "O'rtacha sostav", "Средний состав"), value=tonnes(k.avg_train_t)),
            CardRow(label=t(ctx, "Faol lokomotivlar", "Активных локомотивов"), value=str(k.active_locos)),
        ]
        trains, total = k.trains, k.tonnes
    if not trains:
        msg = t(ctx, f"{name_uz.capitalize()} tortilgan sostav yo'q.", f"Взвешенных составов {name_ru} нет.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg)
    card = Card(kind="metric", title=t(ctx, f"Vesovoy: {name_uz}", f"Весовая: {name_ru}"), rows=rows, href="/dashboard/scales")
    speak = t(ctx, f"{name_uz.capitalize()} {trains} ta sostav tortildi, jami {float(total):.0f} tonna.", f"{name_ru.capitalize()} взвешено составов: {trains}, всего {float(total):.0f} тонн.")
    return Result(cards=[card], speak=speak)


@handler("scales.wagon")
async def wagon(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    try:
        card_data = await scales_insights.wagon_card(ctx.db, asset_id=asset.id, carriage_gtk_id=None, days=30)
    except HTTPException as exc:
        if exc.status_code == 422:
            return Result(cards=[text_card(t(ctx, "Bu lokomotiv: vagon raqamini ayting.", "Это локомотив: назовите номер вагона."), tone="info")], status="needs_clarification")
        return error_card(ctx, exc)
    p, a = card_data.period, card_data.all_time
    rows = [
        CardRow(label=t(ctx, "30 kunda reyslar", "Рейсов за 30 дней"), value=str(p.trips)),
        CardRow(label=t(ctx, "30 kunda yuk", "Груз за 30 дней"), value=tonnes(p.tonnes), tone="ok"),
        CardRow(label=t(ctx, "Jami reyslar", "Всего рейсов"), value=str(a.trips)),
        CardRow(label=t(ctx, "Jami yuk", "Всего груза"), value=tonnes(a.tonnes)),
    ]
    cards = [asset_row_card(ctx, asset, kind="wagon", extra=rows, href=f"/dashboard/scales/wagon/{asset.id}")]
    if card_data.recent:
        cards.append(Card(
            kind="list", title=t(ctx, "So'nggi reyslar", "Последние рейсы"),
            items=[CardItem(label=f"{r.started_at:%d.%m %H:%M}", sub=f"{t(ctx, 'lokomotiv', 'локомотив')} {r.loco_number or '—'}", value=tonnes(r.tonnes)) for r in card_data.recent[:5]],
        ))
    speak = t(ctx, f"{asset.inv_number} vagoni 30 kunda {p.trips} reys, {float(p.tonnes):.0f} tonna tashidi.", f"Вагон {asset.inv_number} за 30 дней: рейсов {p.trips}, груза {float(p.tonnes):.0f} т.")
    return Result(cards=cards, speak=speak, entities=entity_for(asset))
