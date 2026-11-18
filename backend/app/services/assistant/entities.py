"""Entity resolution: from the canonical sentence to assets, trains, sections, periods, pages, statuses, comment text.

Assets are looked up ONLY among what the user may see (a master: own section). The numbers are matched against the inventory number, the
serial/registration number and the GTK garage number; several hits are returned as `assets` (ambiguous) for the handler to list.
"""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset, fixed_asset_name_expression
from app.models.gtk import GtkLocomotive, GtkTrain
from app.models.identity import User
from app.models.organization import Section
from app.schemas.assistant import AssistantContext
from app.services.assistant import catalog
from app.services.assistant.normalize import keyword_matches, normalize
from app.services.assistant.types import AssetRef, LOCOMOTIVE_TYPES, Period, Slots

_NUMBER = re.compile(r"^\d{2,12}$")
_LOCO_HINT = ("lokomotiv", "локомотив", "teplovoz", "тепловоз", "elektrovoz", "электровоз", "tortuv", "тягов")
_WAGON_HINT = ("vagon", "вагон", "sisterna", "цистерн", "platforma", "платформ", "samosval", "самосвал")
_TRAIN_WORDS = ("sostav", "состав", "poezd", "поезд")
_WO_WORDS = ("naryad", "наряд")
_COMMENT_WORDS = ("izoh", "comment", "комментар", "примечан", "qayd", "eslatma", "заметк")
_COMMENT_FILLERS = {"qosh", "qoshing", "yoz", "yozib", "qoy", "добавь", "добавить", "напиши", "запиши", "к", "ga", "uchun", "va", "что", "bu", "shu"}

PRONOUNS = ("bu", "shu", "uni", "unga", "ushbu", "buni", "bunga", "этот", "эту", "его", "ему", "этого", "эта", "это")
_PERIODS: dict[str, tuple[str, ...]] = {
    "today": ("bugun", "bugungi", "hozir", "сегодня", "сегодняшн", "today"),
    "yesterday": ("kecha", "kechagi", "вчера", "вчерашн", "yesterday"),
    "week": ("hafta", "haftalik", "haftada", "неделя", "неделю", "недельн", "неделе", "week"),
    "month": ("oy", "oylik", "oyda", "месяц", "месяце", "месячн", "month"),
}


def _has(tokens: list[str], words: tuple[str, ...]) -> bool:
    return any(keyword_matches(t, normalize(w)) for t in tokens for w in words)


def detect_period(tokens: list[str]) -> Period:
    for period in ("yesterday", "week", "month", "today"):
        for t in tokens:
            if any(keyword_matches(t, p) for p in _PERIODS[period]):
                return period  # type: ignore[return-value]
    return "today"


def detect_status(tokens: list[str]) -> str | None:
    for status, words in catalog.STATUS_WORDS.items():
        if any(keyword_matches(t, normalize(w)) for t in tokens for w in words):
            return status
    return None


def detect_page(text: str) -> str | None:
    """The longest spoken page name found in the sentence (so "vagonlar" beats a shorter "gps")."""
    padded = f" {text} "
    best: tuple[int, str] | None = None
    for key, (_path, _perm, names) in catalog.PAGES.items():
        for name in names:
            n = normalize(name)
            if f" {n} " in padded or (len(n) >= 5 and any(t.startswith(n) for t in text.split())):  # "xaritani" / "vesovoyni" carry a suffix
                if best is None or len(n) > best[0]:
                    best = (len(n), key)
    return best[1] if best else None


def numbers_in(tokens: list[str]) -> list[str]:
    return [t for t in tokens if _NUMBER.match(t)]


def after_keyword_number(tokens: list[str], words: tuple[str, ...], reach: int = 2) -> str | None:
    """The first number right after (or one token before) one of the words: "sostav 439" / "439 sostav". `reach` 1: only the NEXT token (a work order is "naryad 1024"; "37919 naryadlari" names a unit)."""
    for i, t in enumerate(tokens):
        if any(keyword_matches(t, normalize(w)) for w in words):
            for j in ((i + 1,) if reach == 1 else (i + 1, i + 2, i - 1)):
                if 0 <= j < len(tokens) and _NUMBER.match(tokens[j]):
                    return tokens[j]
    return None


def comment_text(tokens: list[str], numbers: list[str]) -> str | None:
    """The free text of a comment: everything after the comment word and the order number, without filler words."""
    for i, t in enumerate(tokens):
        if any(keyword_matches(t, normalize(w)) for w in _COMMENT_WORDS):
            rest = [x for x in tokens[i + 1 :] if x not in _COMMENT_FILLERS and x not in numbers]
            if len(rest) >= 1:
                return " ".join(rest)[:300]
            before = [x for x in tokens[:i] if x not in _COMMENT_FILLERS and x not in numbers and not any(keyword_matches(x, normalize(w)) for w in _WO_WORDS)]
            return " ".join(before)[:300] or None
    return None


def _asset_stmt(user: User):
    stmt = (
        select(
            FixedAsset.id, FixedAsset.inv_number, fixed_asset_name_expression().label("name"), FixedAsset.asset_type, FixedAsset.section_id,
            Section.name.label("section_name"), FixedAsset.serial_number,
        )
        .outerjoin(Section, FixedAsset.section_id == Section.id)
        .where(FixedAsset.decommissioned_at.is_(None))
    )
    if user.role == "master":
        stmt = stmt.where(FixedAsset.section_id == user.section_id)
    return stmt


async def _gtk_ids(db: AsyncSession, ids: list[UUID]) -> dict[UUID, int]:
    if not ids:
        return {}
    rows = await db.execute(
        select(AssetSourceLink.asset_id, AssetSourceLink.external_id).where(
            AssetSourceLink.asset_id.in_(ids), AssetSourceLink.source == "gtk", AssetSourceLink.status == "active"
        )
    )
    return {a: int(e) for a, e in rows.all() if str(e).isdigit()}


def _ref(row, gtk: dict[UUID, int], model: str | None = None) -> AssetRef:
    return AssetRef(
        id=row.id, inv_number=row.inv_number, name=row.name, asset_type=row.asset_type, section_id=row.section_id, section_name=row.section_name,
        model_name=model, gtk_id=gtk.get(row.id),
    )


async def asset_by_id(db: AsyncSession, user: User, asset_id: UUID) -> AssetRef | None:
    row = (await db.execute(_asset_stmt(user).where(FixedAsset.id == asset_id))).first()
    if row is None:
        return None
    return _ref(row, await _gtk_ids(db, [row.id]))


async def resolve_assets(db: AsyncSession, user: User, numbers: list[str], tokens: list[str]) -> list[AssetRef]:
    """Assets matching the numbers of the sentence; a kind word (lokomotiv / vagon) narrows an ambiguous result."""
    found: dict[UUID, tuple[int, object]] = {}
    for n in numbers:
        if len(n) < 3:
            continue
        stmt = _asset_stmt(user)
        exact = (await db.execute(stmt.where(or_(FixedAsset.inv_number == n, FixedAsset.serial_number == n)))).all()
        rows = list(exact)
        if not rows and len(n) >= 4:
            rows = list((await db.execute(stmt.where(or_(FixedAsset.inv_number.like(f"%{n}%"), FixedAsset.serial_number.like(f"%{n}%"))).limit(8))).all())
        if not rows:  # the GTK garage number of a locomotive ("2313")
            garage = (
                await db.execute(
                    select(AssetSourceLink.asset_id)
                    .join(GtkLocomotive, cast(GtkLocomotive.gtk_id, String) == AssetSourceLink.external_id)
                    .where(AssetSourceLink.source == "gtk", AssetSourceLink.status == "active", GtkLocomotive.garage_number == n)
                )
            ).scalars().all()
            if garage:
                rows = list((await db.execute(stmt.where(FixedAsset.id.in_(garage)))).all())
        for r in rows:
            found.setdefault(r.id, (0 if r.inv_number == n or r.serial_number == n else 1, r))
    if not found:
        return []
    ordered = sorted(found.values(), key=lambda x: (x[0], x[1].inv_number))
    rows = [r for _, r in ordered]
    if len(rows) > 1:
        wants_loco, wants_wagon = _has(tokens, _LOCO_HINT), _has(tokens, _WAGON_HINT)
        if wants_loco and not wants_wagon:
            narrowed = [r for r in rows if r.asset_type in LOCOMOTIVE_TYPES]
            rows = narrowed or rows
        elif wants_wagon and not wants_loco:
            narrowed = [r for r in rows if r.asset_type not in LOCOMOTIVE_TYPES]
            rows = narrowed or rows
        best = [r for r in rows if any(r.inv_number == n or r.serial_number == n for n in numbers)]
        if len(best) == 1:
            rows = best
    gtk = await _gtk_ids(db, [r.id for r in rows])
    return [_ref(r, gtk) for r in rows[:6]]


async def resolve_section(db: AsyncSession, user: User, text: str) -> tuple[UUID | None, str | None]:
    if user.role == "master":
        return user.section_id, None
    rows = (await db.execute(select(Section.id, Section.name))).all()
    padded = f" {text} "
    best: tuple[int, UUID, str] | None = None
    for sid, name in rows:
        n = normalize(name or "")
        if len(n) >= 4 and f" {n} " in padded:
            if best is None or len(n) > best[0]:
                best = (len(n), sid, name)
    return (best[1], best[2]) if best else (None, None)


async def resolve_train(db: AsyncSession, train_no: str) -> int | None:
    rows = (await db.execute(select(GtkTrain.gtk_id, GtkTrain.is_open).where(func.trim(GtkTrain.number) == train_no).order_by(GtkTrain.is_open.desc(), GtkTrain.gtk_id.desc()).limit(1))).first()
    return rows[0] if rows else None


async def extract(db: AsyncSession, user: User, canonical_text: str, context: AssistantContext | None, need_asset: bool, need_context_asset: bool) -> Slots:
    """Fill `Slots` from the canonical sentence (+ page context for "bu lokomotiv")."""
    tokens = canonical_text.split()
    slots = Slots(raw_numbers=numbers_in(tokens))
    slots.period = detect_period(tokens)
    slots.status = detect_status(tokens)
    slots.page = detect_page(canonical_text)
    slots.train_no = after_keyword_number(tokens, _TRAIN_WORDS)
    wo_no = after_keyword_number(tokens, _WO_WORDS, reach=1)
    slots.work_order = wo_no
    slots.text = comment_text(tokens, slots.raw_numbers)
    ids = [n for n in slots.raw_numbers if n not in {slots.train_no, wo_no}] or ([] if (slots.train_no or wo_no) else slots.raw_numbers)
    if slots.train_no:
        slots.train_gtk_id = await resolve_train(db, slots.train_no)
    slots.section_id, slots.section_name = await resolve_section(db, user, canonical_text)
    if need_asset and ids:
        assets = await resolve_assets(db, user, ids, tokens)
        if len(assets) == 1:
            slots.asset = assets[0]
        elif len(assets) > 1:
            slots.assets = assets
    if slots.asset is None and not slots.assets and need_context_asset and context is not None:
        slots.pronoun = _has(tokens, PRONOUNS)
        target = context.asset_id or (UUID(context.last_entity.id) if context.last_entity and context.last_entity.kind == "asset" else None)
        if target is not None and (slots.pronoun or not ids):
            slots.asset = await asset_by_id(db, user, target)
            slots.asset_from_context = slots.asset is not None
    return slots
