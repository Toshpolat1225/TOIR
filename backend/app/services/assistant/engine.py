"""The command centre pipeline: text -> canonical sentence -> intent + slots -> permission -> handler -> answer (+ confirmation for writes).

Nothing here talks to a model. Writes never execute in one step: the handler returns a `PendingAction`, the engine stores it for a minute and the
user confirms it (`confirm_command`); the executor re-checks permission and scope.
"""
from __future__ import annotations

import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import user_has_permission
from app.models.assistant import AssistantPending, AssistantQuery
from app.models.identity import User
from app.schemas.assistant import (
    Card, CardRow, CommandIn, CommandOut, ConfirmIn, DialogState, ConfirmOut, HelpGroup, HelpOut, Suggestion,
)
from app.services.assistant import catalog
from app.services.assistant import handlers as _handlers  # noqa: F401  (importing registers every handler and action)
from app.services.assistant.normalize import detect_locale
from app.services.assistant.numbers import canonical as canonical_for_parser
from app.services.assistant.parser import Parsed, parse
from app.services.assistant.registry import ACTIONS, HANDLERS
from app.services.assistant.types import Ctx, Result

logger = logging.getLogger(__name__)

CONFIRM_TTL = timedelta(seconds=60)
RATE_LIMITS = {"command": (60, 60.0), "transcribe": (15, 60.0), "confirm": (20, 60.0)}
_WINDOWS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def check_rate(user_id: object, kind: str) -> None:
    """A per-user sliding window (in process: enough for one backend container); 429 when exceeded."""
    limit, per = RATE_LIMITS[kind]
    window = _WINDOWS[(str(user_id), kind)]
    now = time.monotonic()
    while window and now - window[0] > per:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many assistant requests, slow down")
    window.append(now)


def _t(locale: str, uz: str, ru: str) -> str:
    return uz if locale == "uz" else ru


def _text_card(title: str, tone: str | None = None, rows: list[CardRow] | None = None, kind: str = "text") -> Card:
    return Card(kind=kind, title=title, tone=tone, rows=rows or [])  # type: ignore[arg-type]


_FOLLOW_UPS: dict[str, tuple[tuple[str, str], ...]] = {
    "gps.where": (("{a} GPS holati", "статус GPS {a}"), ("{a} bugun necha km yurdi", "сколько проехал {a} сегодня"), ("{a} ni xaritada ko'rsat", "покажи {a} на карте")),
    "gps.status": (("{a} qayerda", "где {a}"), ("{a} uchun Wialon va GTK nega farq qildi", "почему у {a} разные пробеги")),
    "gps.km": (("{a} qayerda", "где {a}"), ("{a} kecha necha km yurdi", "сколько проехал {a} вчера")),
    "gps.why_diff": (("o'lik GTK trekerlar", "мёртвые трекеры GTK"),),
    "find.asset": (("{a} qayerda", "где {a}"), ("{a} probegi", "пробег {a}"), ("{a} keyingi ТО qachon", "когда следующее ТО у {a}")),
    "asset.info": (("{a} qayerda", "где {a}"), ("{a} naryadlari", "наряды по {a}")),
    "to.overdue": (("bu oy ТО jadvali", "график ТО на месяц"),),
    "wo.count": (("ochiq naryadlar", "открытые наряды"),),
    "train.info": (("sostav {n} lokomotivi", "локомотив состава {n}"),),
}


def _suggestions(parsed: Parsed, locale: str) -> list[Suggestion]:
    out: list[Suggestion] = []
    if parsed.intent is None:
        examples = []
        for intent_id, _score in parsed.candidates[:3]:
            i = catalog.INTENTS[intent_id]
            examples.extend((i.examples_uz if locale == "uz" else i.examples_ru)[:1])
        defaults = ("37919 qayerda", "ochiq naryadlar", "muddati o'tgan ТО", "yordam") if locale == "uz" else ("где 37919", "открытые наряды", "просроченные ТО", "помощь")
        for text in [*examples, *defaults][:4]:
            out.append(Suggestion(text=text))
        return out
    asset = parsed.slots.asset.inv_number if parsed.slots.asset else None
    for uz, ru in _FOLLOW_UPS.get(parsed.intent.id, ()):
        text = (uz if locale == "uz" else ru).replace("{a}", asset or "").replace("{n}", parsed.slots.train_no or "")
        if ("{a}" in uz and not asset) or ("{n}" in uz and not parsed.slots.train_no):
            continue
        out.append(Suggestion(text=text.strip()))
    return out[:3]


def _clarify(parsed: Parsed, locale: str) -> Result:
    intent = parsed.intent
    assert intent is not None
    asks = {
        "asset": _t(locale, "Qaysi texnika? Inventar raqamini ayting (masalan 37919).", "Какая техника? Назовите инвентарный номер (например 37919)."),
        "train_no": _t(locale, "Qaysi sostav? Sostav raqamini ayting.", "Какой состав? Назовите номер состава."),
        "work_order": _t(locale, "Qaysi naryad? Naryad raqamini ayting.", "Какой наряд? Назовите номер наряда."),
        "page": _t(locale, "Qaysi sahifani ochay?", "Какую страницу открыть?"),
        "text": _t(locale, "Izoh matnini ayting.", "Назовите текст комментария."),
    }
    first = parsed.missing[0] if parsed.missing else "asset"
    examples = (intent.examples_uz if locale == "uz" else intent.examples_ru)[:2]
    card = Card(kind="text", title=asks.get(first, asks["asset"]), tone="info", rows=[CardRow(label=_t(locale, "Masalan", "Например"), value=e) for e in examples])
    return Result(cards=[card], speak=asks.get(first), status="needs_clarification")


async def _allowed(db: AsyncSession, user: User, parsed: Parsed) -> bool:
    intent = parsed.intent
    if intent is None:
        return True
    perm = intent.permission
    if intent.id == "nav.open" and parsed.slots.page:
        perm = catalog.PAGES[parsed.slots.page][1]
    return perm is None or await user_has_permission(db, user, perm)


async def _log(db: AsyncSession, user: User, row: AssistantQuery) -> int | None:
    try:
        db.add(row)
        await db.commit()
        return row.id
    except Exception as exc:  # the log must never break an answer
        logger.error("Assistant log failed (%s)", type(exc).__name__)
        await db.rollback()
        return None


def _out(result: Result, *, parsed: Parsed | None, canon: str, locale: str, st: str, ms: int, confirm: ConfirmOut | None = None, qid: int | None = None) -> CommandOut:
    dialog = DialogState(intent=parsed.intent.id, base=canon[:400]) if parsed and parsed.intent and st == "needs_clarification" else None
    return CommandOut(
        ok=st in ("ok", "needs_confirm"), status=st, intent=parsed.intent.id if parsed and parsed.intent else None, heard=canon, speak=result.speak,  # type: ignore[arg-type]
        speak_lang="uz" if locale == "uz" else "ru", cards=result.cards, navigate=result.navigate, confirm=confirm,
        suggestions=_suggestions(parsed, locale) if parsed else [], entities=result.entities, ms=ms, query_id=qid, dialog=dialog,
    )


async def run_command(db: AsyncSession, user: User, body: CommandIn) -> CommandOut:
    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    locale: Literal["uz", "ru"] = body.locale if body.locale != "auto" else detect_locale(body.text)  # type: ignore[assignment]
    canon = canonical_for_parser(body.text)
    parsed = await parse(db, user, canon, body.context)
    dialog = body.context.dialog if body.context else None
    if dialog is not None and dialog.intent in catalog.INTENTS and (parsed.intent is None or parsed.fallback is not None):
        # the answer to our question ("37919", "ehtiyot qism kutilmoqda"): it is not a command of its own, so it completes the unfinished one
        combined = f"{dialog.base} {canon}"[:400]
        joined = await parse(db, user, combined, body.context)
        if joined.intent is not None and joined.intent.id == dialog.intent:
            parsed, canon = joined, combined
    ctx = Ctx(db=db, user=user, locale=locale, context=body.context, now=now)
    st = "ok"
    result = Result()
    confirm: ConfirmOut | None = None
    if parsed.intent is None:
        st = "unmatched"
        result = Result(
            cards=[Card(kind="error", title=_t(locale, "Tushunmadim. Quyidagilardan birini ayting yoki yozing:", "Не понял. Скажите или напишите, например:"), tone="warn")],
            speak=_t(locale, "Tushunmadim", "Не понял"),
        )
    elif not await _allowed(db, user, parsed):
        st = "denied"
        result = Result(
            cards=[Card(kind="error", title=_t(locale, "Bu amal uchun ruxsatingiz yo'q.", "Для этого действия нет прав."), tone="bad")],
            speak=_t(locale, "Ruxsat yo'q", "Нет прав"), status="denied",
        )
    elif parsed.missing and not (parsed.slots.assets and parsed.missing == ["asset"]):
        result = _clarify(parsed, locale)
        st = "needs_clarification"
    else:
        fn = HANDLERS.get(parsed.intent.id)
        if fn is None:
            st = "error"
            result = Result(cards=[Card(kind="error", title=_t(locale, "Bu buyruq hali ishga tushirilmagan.", "Эта команда ещё не реализована."), tone="warn")])
        else:
            try:
                result = await fn(ctx, parsed.slots)
                st = result.status
                if result.pending is not None:
                    token = secrets.token_urlsafe(24)
                    expires = now + CONFIRM_TTL
                    db.add(AssistantPending(
                        token=token, user_id=user.id, kind=result.pending.kind, payload=result.pending.payload, summary=result.pending.summary,
                        locale=locale, risk=result.pending.risk, expires_at=expires,
                    ))
                    await db.commit()
                    confirm = ConfirmOut(token=token, expires_at=expires, summary=result.pending.summary, risk=result.pending.risk)
                    result.cards.append(Card(kind="confirm", title=result.pending.summary, tone="warn" if result.pending.risk == "medium" else "info"))
                    result.speak = result.speak or result.pending.summary
                    st = "needs_confirm"
            except HTTPException as exc:
                await db.rollback()
                st = "error" if exc.status_code >= 500 else "denied" if exc.status_code in (401, 403) else "ok"
                result = Result(cards=[Card(kind="error", title=str(exc.detail), tone="bad" if st != "ok" else "warn")], status="error" if st == "error" else "ok")
            except Exception as exc:  # a handler bug must not leak details
                logger.error("Assistant handler %s failed (%s)", parsed.intent.id, type(exc).__name__)
                await db.rollback()
                st = "error"
                result = Result(cards=[Card(kind="error", title=_t(locale, "Xatolik yuz berdi. Qayta urinib ko'ring.", "Произошла ошибка. Повторите попытку."), tone="bad")])
    ms = int((time.perf_counter() - started) * 1000)
    qid = await _log(db, user, AssistantQuery(
        user_id=user.id, text=canon[:400], locale=locale, source=body.source, intent=parsed.intent.id if parsed.intent else None,
        best_intent=(parsed.candidates[0][0] if parsed.candidates else None), status=st, ms=ms, stt_confidence=body.stt_confidence,
        entities=[e.model_dump() for e in result.entities] or None,
    ))
    return _out(result, parsed=parsed, canon=canon, locale=locale, st=st, ms=ms, confirm=confirm, qid=qid)


async def confirm_command(db: AsyncSession, user: User, body: ConfirmIn) -> CommandOut:
    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    row = (await db.execute(select(AssistantPending).where(AssistantPending.token == body.token, AssistantPending.user_id == user.id))).scalar_one_or_none()
    locale = row.locale if row is not None else "uz"
    if row is None:
        result = Result(cards=[Card(kind="error", title="Confirmation not found", tone="bad")], status="error")
        return _out(result, parsed=None, canon="", locale=locale, st="error", ms=0)
    if row.used_at is not None or row.outcome is not None:
        result = Result(cards=[Card(kind="error", title=_t(locale, "Bu tasdiq allaqachon ishlatilgan.", "Это подтверждение уже использовано."), tone="warn")], status="error")
        return _out(result, parsed=None, canon="", locale=locale, st="error", ms=0)
    if row.expires_at < now:
        await db.execute(update(AssistantPending).where(AssistantPending.token == row.token).values(used_at=now, outcome="expired"))
        await db.commit()
        result = Result(cards=[Card(kind="error", title=_t(locale, "Tasdiq muddati tugadi. Buyruqni qaytaring.", "Время подтверждения истекло. Повторите команду."), tone="warn")], status="error")
        return _out(result, parsed=None, canon="", locale=locale, st="error", ms=0)
    if not body.approve:
        await db.execute(update(AssistantPending).where(AssistantPending.token == row.token).values(used_at=now, outcome="cancelled"))
        await db.commit()
        result = Result(cards=[Card(kind="text", title=_t(locale, "Bekor qilindi.", "Отменено."), tone="muted")], speak=_t(locale, "Bekor qilindi", "Отменено"))
        return _out(result, parsed=None, canon="", locale=locale, st="ok", ms=int((time.perf_counter() - started) * 1000))
    # claim it atomically: two taps / two tabs execute the action once
    claimed = (
        await db.execute(
            update(AssistantPending)
            .where(AssistantPending.token == row.token, AssistantPending.used_at.is_(None))
            .values(used_at=now, outcome="confirmed").returning(AssistantPending.token)
        )
    ).first()
    await db.commit()
    if claimed is None:
        result = Result(cards=[Card(kind="error", title=_t(locale, "Bu tasdiq allaqachon ishlatilgan.", "Это подтверждение уже использовано."), tone="warn")], status="error")
        return _out(result, parsed=None, canon="", locale=locale, st="error", ms=0)
    executor = ACTIONS.get(row.kind)
    ctx = Ctx(db=db, user=user, locale=locale if locale in ("uz", "ru") else "uz", context=body.context, now=now)  # type: ignore[arg-type]
    st = "ok"
    try:
        if executor is None:
            raise HTTPException(status_code=501, detail="Action not available")
        result = await executor(ctx, row.payload)
        st = result.status
    except HTTPException as exc:
        await db.rollback()
        await db.execute(update(AssistantPending).where(AssistantPending.token == row.token).values(outcome="failed"))
        await db.commit()
        result = Result(cards=[Card(kind="error", title=str(exc.detail), tone="bad")], status="error")
        st = "error"
    except Exception as exc:
        logger.error("Assistant action %s failed (%s)", row.kind, type(exc).__name__)
        await db.rollback()
        await db.execute(update(AssistantPending).where(AssistantPending.token == row.token).values(outcome="failed"))
        await db.commit()
        result = Result(cards=[Card(kind="error", title=_t(locale, "Amal bajarilmadi.", "Действие не выполнено."), tone="bad")], status="error")
        st = "error"
    ms = int((time.perf_counter() - started) * 1000)
    qid = await _log(db, user, AssistantQuery(user_id=user.id, text=row.summary[:400], locale=locale, source="text", intent=row.kind, status="confirmed" if st == "ok" else "error", ms=ms))
    return _out(result, parsed=None, canon=row.summary, locale=locale, st=st if st in ("ok", "error") else "ok", ms=ms, qid=qid)


async def help_for(db: AsyncSession, user: User) -> HelpOut:
    perms: dict[str | None, bool] = {}
    groups: dict[str, list[str]] = {}
    for intent in catalog.CATALOG:
        if intent.permission not in perms:
            perms[intent.permission] = intent.permission is None or await user_has_permission(db, user, intent.permission)
        if not perms[intent.permission]:
            continue
        groups.setdefault(intent.module, []).extend([*intent.examples_uz[:1], *intent.examples_ru[:1]])
    return HelpOut(groups=[HelpGroup(module=m, title=catalog.MODULE_TITLES.get(m, m), examples=ex) for m, ex in groups.items() if ex])
