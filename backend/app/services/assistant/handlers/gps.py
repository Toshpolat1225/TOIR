"""GPS and wagon intents: where, status, km over a period, why Wialon and GTK differ, dead trackers, summary, map, wagon -> locomotive, train."""
from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrain
from app.schemas.assistant import Card, CardItem, CardRow
from app.services import gps_analytics as ga
from app.services import gps_overview, gps_wagons
from app.services import gtk as gtk_service
from app.services.assistant.handlers._common import (
    age_minutes, ago, asset_row_card, clarify, entity_for, error_card, km, km_value, need_asset, not_found, t, text_card, type_name,
)
from app.services.assistant.registry import handler
from app.services.assistant.types import AssetRef, Ctx, Result, Slots

VERDICT_UZ = {
    "confirmed": "tasdiqlangan", "diverged": "ikki tracker orasida farq", "gtk_stale": "GTK jim", "wialon_stale": "Wialon jim",
    "both_stale_agree": "ikkalasi jim, joyi bir xil", "both_stale_apart": "ikkalasi jim, joylari har xil", "wialon_only": "faqat Wialon",
    "gtk_only": "faqat GTK", "no_position": "koordinata yo'q",
}
VERDICT_RU = {
    "confirmed": "подтверждено", "diverged": "расхождение трекеров", "gtk_stale": "GTK молчит", "wialon_stale": "Wialon молчит",
    "both_stale_agree": "оба молчат, место совпало", "both_stale_apart": "оба молчат, места разные", "wialon_only": "только Wialon",
    "gtk_only": "только GTK", "no_position": "нет координат",
}
VERDICT_TONE = {"confirmed": "ok", "both_stale_agree": "muted", "wialon_only": "info", "gtk_only": "info", "no_position": "warn"}
PERIOD_DAYS = {"today": 1, "yesterday": 2, "week": 7, "month": 30}
PERIOD_NAME = {"today": ("bugun", "сегодня"), "yesterday": ("kecha", "вчера"), "week": ("so'nggi 7 kun", "за 7 дней"), "month": ("so'nggi 30 kun", "за 30 дней")}


def verdict_text(ctx: Ctx, verdict: str) -> str:
    return (VERDICT_UZ if ctx.locale == "uz" else VERDICT_RU).get(verdict, verdict)


def _fix_line(ctx: Ctx, fix) -> str:
    if fix is None:
        return t(ctx, "ma'lumot yo'q", "нет данных")
    speed = f", {fix.speed:.0f} km/h" if fix.speed else ""
    return f"{fix.lat:.5f}, {fix.lon:.5f} · {ago(ctx, fix.age_min)}{speed}"


async def _loco_detail(ctx: Ctx, asset: AssetRef, days: int = 7):
    try:
        return await gps_overview.get_asset_detail(ctx.db, ctx.user, asset.id, days=days, track_days=1, now=ctx.now)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise


async def _wagon_detail(ctx: Ctx, asset: AssetRef, days: int = 31):
    try:
        return await gps_wagons.wagon_detail(ctx.db, ctx.user, str(asset.id), days=days, now=ctx.now)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise


def _best_fix(row):
    return row.gtk if (row.position.best == "gtk" and row.gtk) else (row.wialon or row.gtk)


# ---- gps.where ---------------------------------------------------------------------------------------------
@handler("gps.where")
async def where(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    if asset.is_locomotive:
        detail = await _loco_detail(ctx, asset, days=1)
        if detail is None:
            return not_found(ctx, "Lokomotiv GPS ma'lumoti topilmadi", "GPS-данные локомотива не найдены")
        row = detail.row
        fix = _best_fix(row)
        if fix is None:
            msg = t(ctx, f"{asset.inv_number}: koordinata yo'q.", f"{asset.inv_number}: координат нет.")
            return Result(cards=[text_card(msg, tone="warn")], speak=msg, entities=entity_for(asset))
        source = "GTK" if (row.position.best == "gtk" and row.gtk) else "Wialon"
        verdict = verdict_text(ctx, row.position.verdict)
        card = asset_row_card(
            ctx, asset, extra=[
                CardRow(label=t(ctx, "Joylashuv", "Положение"), value=f"{fix.lat:.5f}, {fix.lon:.5f}"),
                CardRow(label=t(ctx, "Manba", "Источник"), value=f"{source} · {ago(ctx, fix.age_min)}", tone="ok" if fix.fresh else "warn"),
                CardRow(label=t(ctx, "Tezlik", "Скорость"), value=f"{fix.speed:.0f} km/h" if fix.speed else t(ctx, "turibdi", "стоит")),
                CardRow(label=t(ctx, "Trekerlar", "Трекеры"), value=verdict, tone=VERDICT_TONE.get(row.position.verdict, "warn")),
            ],
        )
        speak = t(
            ctx, f"{asset.inv_number} {ago(ctx, fix.age_min)} {source} bo'yicha {fix.lat:.4f}, {fix.lon:.4f} nuqtada, {verdict}.",
            f"{asset.inv_number}: {source}, {ago(ctx, fix.age_min)}, точка {fix.lat:.4f}, {fix.lon:.4f}, {verdict}.",
        )
        return Result(cards=[card], speak=speak, entities=entity_for(asset))
    detail = await _wagon_detail(ctx, asset, days=2)
    if detail is None:
        return not_found(ctx, "Vagon topilmadi yoki GTK bilan bog'lanmagan", "Вагон не найден или не связан с GTK")
    row = detail.row
    if not row.in_train or row.position is None:
        msg = t(ctx, f"{asset.inv_number} hozir hech qaysi sostavda emas: o'z GPS'i yo'q, joyi noma'lum.", f"{asset.inv_number} сейчас не в составе: собственного GPS нет, положение неизвестно.")
        return Result(cards=[text_card(msg, tone="warn")], speak=msg, entities=entity_for(asset))
    fix = row.position
    card = asset_row_card(
        ctx, asset, kind="wagon", extra=[
            CardRow(label=t(ctx, "Sostav", "Состав"), value=f"№ {row.train_number or row.train_gtk_id}"),
            CardRow(label=t(ctx, "Lokomotiv", "Локомотив"), value=row.loco_inv_number or "—"),
            CardRow(label=t(ctx, "Joylashuv (lokomotivdan)", "Положение (по локомотиву)"), value=f"{fix.lat:.5f}, {fix.lon:.5f} · {ago(ctx, fix.age_min)}"),
            CardRow(label=t(ctx, "Ishonch", "Достоверность"), value=row.confidence, tone={"high": "ok", "medium": "info", "low": "warn"}.get(row.confidence)),
        ],
    )
    speak = t(
        ctx, f"{asset.inv_number} vagoni {row.train_number or ''}-sostavda, lokomotiv {row.loco_inv_number or 'noma`lum'} bilan; joyi lokomotivdan olingan.",
        f"Вагон {asset.inv_number} в составе {row.train_number or ''}, локомотив {row.loco_inv_number or 'неизвестен'}; положение по локомотиву.",
    )
    return Result(cards=[card], speak=speak, entities=entity_for(asset))


# ---- gps.status --------------------------------------------------------------------------------------------
@handler("gps.status")
async def status_(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    if not asset.is_locomotive:
        return await where(ctx, slots)
    detail = await _loco_detail(ctx, asset)
    if detail is None:
        return not_found(ctx, "Lokomotiv GPS ma'lumoti topilmadi", "GPS-данные локомотива не найдены")
    row = detail.row
    rows = [
        CardRow(label="Wialon", value=_fix_line(ctx, row.wialon), tone="ok" if (row.wialon and row.wialon.fresh) else "warn"),
        CardRow(label="GTK", value=_fix_line(ctx, row.gtk), tone="ok" if (row.gtk and row.gtk.fresh) else "warn"),
        CardRow(label=t(ctx, "Taqqoslash", "Сверка"), value=verdict_text(ctx, row.position.verdict) + (f" · {row.position.diff_m:.0f} m" if row.position.diff_m is not None else ""),
                tone=VERDICT_TONE.get(row.position.verdict, "warn")),
    ]
    if row.health:
        rows.append(CardRow(label=t(ctx, "GTK treker sog'ligi", "Состояние GTK-трекера"), value=ga.HEALTH_TEXT.get(row.health.health_class, row.health.health_class),
                            tone="ok" if row.health.health_class == "ok" else "warn"))
    card = asset_row_card(ctx, asset, extra=rows)
    if row.explanation:
        card.subtitle = (card.subtitle or "") + " · " + row.explanation
    speak = t(ctx, f"{asset.inv_number}: {verdict_text(ctx, row.position.verdict)}.", f"{asset.inv_number}: {verdict_text(ctx, row.position.verdict)}.")
    return Result(cards=[card], speak=speak, entities=entity_for(asset))


# ---- gps.km ------------------------------------------------------------------------------------------------
def _wagon_period_km(detail, period: str, offset_hours: int, now) -> float:
    today = (now + timedelta(hours=offset_hours)).date()
    days = {"today": {today}, "yesterday": {today - timedelta(days=1)}, "week": {today - timedelta(days=i) for i in range(7)}, "month": {today - timedelta(days=i) for i in range(30)}}[period]
    total = 0.0
    for s in detail.segments:
        local_day = (s.period_from + timedelta(hours=offset_hours)).date()
        if local_day in days and s.selected_km is not None:
            total += float(s.selected_km)
    return total


@handler("gps.km")
async def km_(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    period = slots.period if slots.period in PERIOD_DAYS else "today"
    name_uz, name_ru = PERIOD_NAME[period]
    if asset.is_locomotive:
        detail = await _loco_detail(ctx, asset, days=PERIOD_DAYS[period])
        if detail is None:
            return not_found(ctx, "Lokomotiv GPS ma'lumoti topilmadi", "GPS-данные локомотива не найдены")
        days = detail.row.days[1:2] if period == "yesterday" else detail.row.days[: PERIOD_DAYS[period]]
        wialon = sum(d.wialon_m or 0 for d in days)
        gtk = sum(d.gtk_m or 0 for d in days)
        fused = sum(d.fused_m or d.unified_m or 0 for d in days)
        confs = [d.confidence for d in days if d.confidence is not None]
        rows = [
            CardRow(label=t(ctx, "Yagona km", "Единый пробег"), value=km(fused), tone="ok"),
            CardRow(label="Wialon", value=km(wialon)),
            CardRow(label="GTK", value=km(gtk)),
        ]
        if confs:
            rows.append(CardRow(label=t(ctx, "Ishonch", "Уверенность"), value=f"{sum(confs) / len(confs):.0%}"))
        worst = next((d for d in days if d.cause not in ("ok", "idle", "no_data", "not_collected", "day_open")), None)
        if worst is not None and worst.explanation:
            rows.append(CardRow(label=t(ctx, "Farq sababi", "Причина расхождения"), value=worst.explanation, tone="warn"))
        card = asset_row_card(ctx, asset, kind="metric", extra=rows, title_suffix=f" · {t(ctx, name_uz, name_ru)}")
        speak = t(ctx, f"{asset.inv_number} {name_uz} taxminan {fused / 1000:.1f} kilometr yurdi (Wialon {wialon / 1000:.1f}, GTK {gtk / 1000:.1f}).",
                  f"{asset.inv_number} {name_ru} проехал около {fused / 1000:.1f} километров (Wialon {wialon / 1000:.1f}, GTK {gtk / 1000:.1f}).")
        return Result(cards=[card], speak=speak, entities=entity_for(asset))
    detail = await _wagon_detail(ctx, asset, days=PERIOD_DAYS[period] + 1)
    if detail is None:
        return not_found(ctx, "Vagon topilmadi yoki GTK bilan bog'lanmagan", "Вагон не найден или не связан с GTK")
    value = _wagon_period_km(detail, period, settings.gtk_utc_offset_hours, ctx.now)
    card = asset_row_card(
        ctx, asset, kind="metric", title_suffix=f" · {t(ctx, name_uz, name_ru)}",
        extra=[CardRow(label=t(ctx, "Sostav bo'yicha km", "Пробег по составу"), value=km_value(value), tone="ok"),
               CardRow(label=t(ctx, "Eslatma", "Примечание"), value=t(ctx, "Vagonning o'z GPS'i yo'q: lokomotiv yo'lidan hisoblangan.", "У вагона нет своего GPS: считается по пути локомотива."))],
    )
    speak = t(ctx, f"{asset.inv_number} vagoni {name_uz} sostav bilan taxminan {value:.1f} kilometr yurdi.", f"Вагон {asset.inv_number} {name_ru} проехал в составе около {value:.1f} км.")
    return Result(cards=[card], speak=speak, entities=entity_for(asset))


# ---- gps.why_diff ------------------------------------------------------------------------------------------
@handler("gps.why_diff")
async def why_diff(ctx: Ctx, slots: Slots) -> Result:
    asset = slots.asset
    if asset is None and not slots.assets:
        from app.services.assistant.handlers._common import asset_from_context

        asset = await asset_from_context(ctx)
    if asset is None:
        page = await gps_overview.get_overview(ctx.db, ctx.user, gps_overview.Filters(days=7), limit=1, now=ctx.now)
        causes = {k: v for k, v in page.summary.cause_counts.items() if k not in ("ok", "idle", "no_data", "day_open", "not_collected")}
        total = sum(causes.values()) or 1
        top = sorted(causes.items(), key=lambda kv: -kv[1])[:5]
        card = Card(
            kind="list", title=t(ctx, "Wialon va GTK farqining sabablari (7 kun)", "Причины расхождений Wialon и GTK (7 дней)"), tone="info",
            items=[CardItem(label=ga.explain_day(cause) or cause, value=f"{n} ({n / total:.0%})") for cause, n in top],
        )
        speak = t(ctx, "Farqning asosiy sababi GTK ma'lumotining yo'qolishi.", "Главная причина расхождений: потеря данных GTK.") if top else t(ctx, "Farq yo'q.", "Расхождений нет.")
        return Result(cards=[card], speak=speak)
    if not verify_scope_ok(ctx, asset):
        return not_found(ctx, "Texnika topilmadi", "Техника не найдена")
    if not asset.is_locomotive:
        return clarify(ctx, "Bu faqat lokomotivlar uchun: vagonning o'z GPS'i yo'q.", "Это только для локомотивов: у вагона нет своего GPS.")
    detail = await _loco_detail(ctx, asset)
    if detail is None:
        return not_found(ctx, "Lokomotiv GPS ma'lumoti topilmadi", "GPS-данные локомотива не найдены")
    bad = [d for d in detail.row.days if d.cause not in ("ok", "idle", "no_data", "day_open", "not_collected")]
    if not bad:
        msg = t(ctx, f"{asset.inv_number}: oxirgi 7 kunda sezilarli farq yo'q.", f"{asset.inv_number}: за 7 дней заметных расхождений нет.")
        return Result(cards=[text_card(msg, tone="ok")], speak=msg, entities=entity_for(asset))
    card = Card(
        kind="table", title=f"{asset.inv_number} · " + t(ctx, "farq sabablari", "причины расхождений"),
        columns=[t(ctx, "Kun", "День"), "Wialon", "GTK", t(ctx, "Sabab", "Причина")],
        table=[[d.day.isoformat(), km(d.wialon_m), km(d.gtk_m), d.explanation or d.cause] for d in bad[:7]], href=f"/dashboard/gps/{asset.id}",
    )
    speak = bad[0].explanation or ga.explain_day(bad[0].cause)
    return Result(cards=[card], speak=speak, entities=entity_for(asset))


def verify_scope_ok(ctx: Ctx, asset: AssetRef) -> bool:
    return ctx.master_section_id is None or asset.section_id == ctx.master_section_id


# ---- gps.dead_trackers / gps.summary -----------------------------------------------------------------------
@handler("gps.dead_trackers")
async def dead_trackers(ctx: Ctx, slots: Slots) -> Result:
    page = await gps_overview.get_health(ctx.db, ctx.user, health=["dead", "frozen"], days=30, limit=15, now=ctx.now)
    if not page.items:
        msg = t(ctx, "O'lik yoki qotib qolgan GTK trekerlar yo'q.", "Мёртвых или «замёрзших» трекеров GTK нет.")
        return Result(cards=[text_card(msg, tone="ok")], speak=msg)
    items = [
        CardItem(
            label=h.inv_number, sub=f"{ga.HEALTH_TEXT.get(h.health.health_class, h.health.health_class)} · " + t(ctx, f"yo'qolgan {h.health.km_lost_m / 1000:.0f} km", f"потеряно {h.health.km_lost_m / 1000:.0f} км"),
            tone="bad" if h.health.health_class == "dead" else "warn", href=f"/dashboard/gps/{h.asset_id}",
        )
        for h in page.items
    ]
    card = Card(kind="list", title=t(ctx, f"Muammoli GTK trekerlar: {page.total} ta", f"Проблемные трекеры GTK: {page.total}"), tone="bad", items=items, href="/dashboard/gps?health=dead")
    speak = t(ctx, f"{page.total} ta lokomotivda GTK treker ishlamayapti yoki qotib qolgan.", f"У {page.total} локомотивов трекер GTK не работает или завис.")
    return Result(cards=[card], speak=speak)


@handler("gps.summary")
async def summary(ctx: Ctx, slots: Slots) -> Result:
    page = await gps_overview.get_overview(ctx.db, ctx.user, gps_overview.Filters(days=7), limit=1, now=ctx.now)
    s = page.summary
    v = s.position_verdicts
    rows = [
        CardRow(label=t(ctx, "Lokomotivlar", "Локомотивов"), value=str(s.assets)),
        CardRow(label=t(ctx, "Tasdiqlangan joy", "Подтверждено"), value=str(v.get("confirmed", 0)), tone="ok"),
        CardRow(label=t(ctx, "Farq (ikkalasi yangi)", "Расхождение"), value=str(v.get("diverged", 0)), tone="warn" if v.get("diverged") else None),
        CardRow(label=t(ctx, "GTK jim", "GTK молчит"), value=str(v.get("gtk_stale", 0)), tone="warn" if v.get("gtk_stale") else None),
        CardRow(label=t(ctx, "Wialon jim", "Wialon молчит"), value=str(v.get("wialon_stale", 0)), tone="warn" if v.get("wialon_stale") else None),
        CardRow(label=t(ctx, "O'lik GTK trekerlar", "Мёртвые трекеры GTK"), value=str(s.health_counts.get("dead", 0)), tone="bad" if s.health_counts.get("dead") else None),
        CardRow(label=t(ctx, "7 kunlik yagona km", "Единый пробег за 7 дней"), value=km(s.week_fused_m)),
    ]
    card = Card(kind="metric", title=t(ctx, "GPS xulosasi", "Сводка GPS"), rows=rows, href="/dashboard/gps")
    speak = t(ctx, f"{s.assets} lokomotivdan {v.get('confirmed', 0)} tasi tasdiqlangan, {v.get('diverged', 0)} tasida farq, {s.health_counts.get('dead', 0)} ta GTK treker o'lik.",
              f"Из {s.assets} локомотивов подтверждено {v.get('confirmed', 0)}, расхождений {v.get('diverged', 0)}, мёртвых трекеров GTK {s.health_counts.get('dead', 0)}.")
    return Result(cards=[card], speak=speak)


# ---- map.show / wagon.loco / train.info --------------------------------------------------------------------
@handler("map.show")
async def map_show(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    href = f"/dashboard/gps/{asset.id}" if asset.is_locomotive else f"/dashboard/map/history/{asset.id}"
    msg = t(ctx, f"{asset.inv_number} xaritada ochilmoqda.", f"Открываю {asset.inv_number} на карте.")
    return Result(cards=[asset_row_card(ctx, asset, href=href)], speak=msg, navigate=href, entities=entity_for(asset))


@handler("wagon.loco")
async def wagon_loco(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    if asset.is_locomotive:
        return clarify(ctx, "Bu lokomotiv. Vagon raqamini ayting.", "Это локомотив. Назовите номер вагона.")
    detail = await _wagon_detail(ctx, asset, days=7)
    if detail is None:
        return not_found(ctx, "Vagon topilmadi yoki GTK bilan bog'lanmagan", "Вагон не найден или не связан с GTK")
    row = detail.row
    if not row.in_train:
        msg = t(ctx, f"{asset.inv_number} hozir sostavda emas.", f"Вагон {asset.inv_number} сейчас не в составе.")
        return Result(cards=[text_card(msg, tone="warn")], speak=msg, entities=entity_for(asset))
    loco = row.loco_inv_number or t(ctx, "noma'lum (boshqa uchastka yoki bog'lanmagan)", "неизвестен (другой участок или не связан)")
    rows = [
        CardRow(label=t(ctx, "Lokomotiv", "Локомотив"), value=loco, tone="ok" if row.loco_inv_number else "warn"),
        CardRow(label=t(ctx, "Sostav", "Состав"), value=f"№ {row.train_number or row.train_gtk_id}"),
        CardRow(label=t(ctx, "Boshlangan", "С"), value=row.since.strftime("%d.%m %H:%M") if row.since else "—"),
    ]
    items = [CardItem(label=f"{s.loco_inv_number or '—'} · № {s.train_number or s.train_gtk_id}", sub=f"{s.period_from:%d.%m %H:%M} → {s.period_to:%d.%m %H:%M}", value=km_value(s.selected_km),
                      href=f"/dashboard/gps/{s.loco_asset_id}" if s.loco_asset_id else None) for s in detail.segments[:5]]
    cards = [asset_row_card(ctx, asset, kind="wagon", extra=rows)]
    if items:
        cards.append(Card(kind="list", title=t(ctx, "So'nggi bo'laklar", "Последние отрезки"), items=items, href=f"/dashboard/gps/wagons/{asset.id}"))
    speak = t(ctx, f"{asset.inv_number} vagonini hozir {loco} lokomotivi tortyapti, sostav {row.train_number or row.train_gtk_id}.", f"Вагон {asset.inv_number} сейчас тянет локомотив {loco}, состав {row.train_number or row.train_gtk_id}.")
    return Result(cards=cards, speak=speak, entities=entity_for(asset))


async def _resolve_train(ctx: Ctx, slots: Slots) -> GtkTrain | None:
    if slots.train_gtk_id is not None:
        return (await ctx.db.execute(select(GtkTrain).where(GtkTrain.gtk_id == slots.train_gtk_id))).scalar_one_or_none()
    if not slots.train_no:
        return None
    rows = (await ctx.db.execute(select(GtkTrain).where(GtkTrain.number == slots.train_no).order_by(GtkTrain.is_open.desc(), GtkTrain.begin_time.desc()).limit(1))).scalars().all()
    return rows[0] if rows else None


@handler("train.info")
async def train_info(ctx: Ctx, slots: Slots) -> Result:
    if not slots.train_no and slots.train_gtk_id is None:
        return clarify(ctx, "Qaysi sostav? Raqamini ayting.", "Какой состав? Назовите номер.", ["sostav 439"])
    train = await _resolve_train(ctx, slots)
    if train is None:
        return not_found(ctx, "Sostav topilmadi", "Состав не найден")
    detail = await gtk_service.get_train_detail(ctx.db, train.gtk_id, current_only=True)
    if detail is None:
        return not_found(ctx, "Sostav topilmadi", "Состав не найден")
    carriages, locos = detail["carriages"], detail["locomotives"]
    visible: list[str] = []
    hidden = 0
    for loco in locos:
        link = (await ctx.db.execute(select(AssetSourceLink.asset_id).where(AssetSourceLink.source == "gtk", AssetSourceLink.status == "active", AssetSourceLink.external_id == str(loco["gtk_id"])))).scalar_one_or_none()
        section = None
        inv = None
        if link is not None:
            fa = (await ctx.db.execute(select(FixedAsset.inv_number, FixedAsset.section_id).where(FixedAsset.id == link))).one_or_none()
            if fa is not None:
                inv, section = fa
        if ctx.master_section_id is not None and section != ctx.master_section_id:
            hidden += 1  # another section's locomotive is not named to a master
            continue
        visible.append(inv or loco.get("garage_number") or loco.get("name") or "—")
    if ctx.master_section_id is not None and hidden and not visible and not carriages:
        return not_found(ctx, "Sostav topilmadi", "Состав не найден")
    rows = [
        CardRow(label=t(ctx, "Vagonlar", "Вагонов"), value=str(len(carriages)), tone="ok"),
        CardRow(label=t(ctx, "Lokomotiv", "Локомотив"), value=", ".join(visible) if visible else "—"),
        CardRow(label=t(ctx, "Holat", "Статус"), value=t(ctx, "ochiq", "открыт") if train.is_open else t(ctx, "yopilgan", "закрыт")),
    ]
    if train.begin_time:
        rows.append(CardRow(label=t(ctx, "Boshlangan", "С"), value=train.begin_time.strftime("%d.%m %H:%M")))
    card = Card(kind="train", title=f"{t(ctx, 'Sostav', 'Состав')} № {train.number or train.gtk_id}", subtitle=train.title, rows=rows, href="/dashboard/map")
    speak = t(ctx, f"Sostav {train.number}: {len(carriages)} ta vagon, lokomotiv {', '.join(visible) or 'ko`rsatilmagan'}.", f"Состав {train.number}: вагонов {len(carriages)}, локомотив {', '.join(visible) or 'не указан'}.")
    from app.schemas.assistant import EntityRef

    return Result(cards=[card], speak=speak, entities=[EntityRef(kind="train", id=str(train.gtk_id), label=str(train.number or train.gtk_id))])
