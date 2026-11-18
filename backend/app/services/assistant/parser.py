"""Intent selection: score the catalogue against the canonical sentence, then fill the slots the winner needs.

No machine learning: every decision is a visible rule (keyword groups AND/OR, 5-letter prefixes, slot requirements, priorities), so a wrong
answer is always explainable and fixed by adding a keyword or an example to the catalogue.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.schemas.assistant import AssistantContext
from app.services.assistant import catalog, entities
from app.services.assistant.catalog import INTENTS, Intent
from app.services.assistant.normalize import keyword_matches, normalize, phrase_matches
from app.services.assistant.repair import repair_text
from app.services.assistant.types import Slots

# normalised keywords, built once
_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {}
_BOOST: dict[str, tuple[tuple[str, ...], ...]] = {}


def _norm_word(w: str) -> str:
    n = normalize(w.rstrip("*"))
    return n + "*" if w.endswith("*") and n else n


def _norm_groups(groups) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(dict.fromkeys(_norm_word(w) for w in g if _norm_word(w))) for g in groups)


for _i in catalog.CATALOG:
    _GROUPS[_i.id] = _norm_groups(_i.groups)
    _BOOST[_i.id] = _norm_groups(_i.boost)


@dataclass
class Match:
    intent: Intent
    score: float
    missing: list[str] = field(default_factory=list)  # slot names the sentence did not provide


@dataclass
class Parsed:
    intent: Intent | None
    slots: Slots
    missing: list[str]
    candidates: list[tuple[str, float]]  # (intent id, score) best first, for suggestions
    fallback: str | None = None  # why this intent was chosen without keywords ("asset_only", "page_only")
    repaired: str | None = None  # the sentence after speech-error repair, when that is what matched


def _group_hit(tokens: list[str], group: tuple[str, ...], text: str = "") -> bool:
    text = text or " ".join(tokens)
    for w in group:
        if " " in w:
            if phrase_matches(text, w):
                return True
        elif any(keyword_matches(t, w) for t in tokens):
            return True
    return False


def keyword_score(intent_id: str, tokens: list[str]) -> float | None:
    """None when a required group does not match; else the base score of the keywords."""
    groups = _GROUPS[intent_id]
    text = " ".join(tokens)
    if not all(_group_hit(tokens, g, text) for g in groups):
        return None
    score = 10.0 * len(groups)
    score += 3.0 * sum(1 for g in _BOOST[intent_id] if _group_hit(tokens, g, text))
    return score


def _needs_missing(intent: Intent, slots: Slots) -> list[str]:
    missing: list[str] = []
    for need in intent.needs:
        if need == "asset" and (slots.asset is None or (intent.pronoun_only and slots.asset_from_context and not slots.pronoun)):
            missing.append("asset")
        elif need == "train_no" and not slots.train_no:
            missing.append("train_no")
        elif need == "work_order" and not slots.work_order:
            missing.append("work_order")
        elif need == "page" and not slots.page:
            missing.append("page")
        elif need == "text" and not slots.text:
            missing.append("text")
    return missing


_CREATE_VERBS = ("yarat", "yangi", "создай", "создать", "оформи", "новый", "новую", "tuz")  # not «och/открой»: those mean «open the page»


def rank(tokens: list[str], slots: Slots) -> list[Match]:
    """Pure part: every intent whose keyword groups all match, scored with the slot situation (no database)."""
    matches: list[Match] = []
    for intent in catalog.CATALOG:
        base = keyword_score(intent.id, tokens)
        if base is None:
            continue
        missing = _needs_missing(intent, slots)
        if intent.no_asset and (slots.asset is not None or slots.assets):
            continue  # "GPS holati 37919" is about one unit, not the fleet summary
        if intent.no_train and slots.train_no:
            continue  # "sostavda nechta vagon bor 439" is about that train
        if not intent.groups and missing:
            continue  # a keyword-less intent (nav.open) only exists when its slot was found
        # an intent whose needs are met outranks one that still lacks something; each missing need costs more than any keyword can earn
        bonus = 4.0 * (len(intent.needs) - len(missing)) + (6.0 if not missing else 0.0) - 12.0 * len(missing)
        if slots.assets and "asset" in intent.needs:
            bonus += 2.0  # ambiguous but present: the handler lists the candidates
            missing = [m for m in missing if m != "asset"]
        if intent.id == "wo.create" and any(t.startswith(_CREATE_VERBS) for t in tokens):
            bonus += 30.0  # «yangi naryad yarat» is a create command that still lacks the unit, not a request to open the page
        matches.append(Match(intent, base + intent.priority + bonus, missing))
    matches.sort(key=lambda m: (-m.score, m.intent.id))
    return matches


def _wants(tokens: list[str]) -> tuple[bool, bool, bool]:
    """(any intent matches, an intent needs an asset, an intent may take the context asset) - decides which lookups are worth doing."""
    hits = [i for i in catalog.CATALOG if i.groups and keyword_score(i.id, tokens) is not None]  # a keyword-less intent (nav.open) says nothing about the sentence
    return bool(hits), any(("asset" in i.needs) or i.context_asset for i in hits), any(i.context_asset for i in hits)


async def parse(db: AsyncSession, user: User, canonical_text: str, context: AssistantContext | None) -> Parsed:
    """Strict parse first; when no keyword intent was found, the sentence is repaired (recogniser near-misses -> catalogue words) and parsed once more."""
    parsed = await _parse(db, user, canonical_text, context)
    if parsed.intent is not None and parsed.fallback is None and not parsed.missing and parsed.intent.id != "nav.open":
        return parsed  # nav.open carries no keywords of its own: a repaired sentence may name a more specific command
    repaired = repair_text(canonical_text)
    if repaired != canonical_text:
        second = await _parse(db, user, repaired, context)
        if second.intent is not None and not second.missing and second.intent != parsed.intent and (second.fallback is None or parsed.intent is None):
            second.repaired = repaired
            return second
    return parsed


async def _parse(db: AsyncSession, user: User, canonical_text: str, context: AssistantContext | None) -> Parsed:
    tokens = canonical_text.split()
    any_hit, wants_asset, wants_ctx = _wants(tokens)
    slots = await entities.extract(db, user, canonical_text, context, need_asset=wants_asset or not any_hit, need_context_asset=wants_ctx or not any_hit)
    matches = rank(tokens, slots)
    candidates = [(m.intent.id, m.score) for m in matches[:4]]
    if matches:
        best = matches[0]
        return Parsed(best.intent, slots, best.missing, candidates)
    if (slots.asset is not None and not slots.asset_from_context) or slots.assets:  # the page's unit never turns an unclear sentence into «find the unit»
        return Parsed(INTENTS["find.asset"], slots, [], [("find.asset", 1.0)], fallback="asset_only")
    if slots.page:
        return Parsed(INTENTS["nav.open"], slots, [], [("nav.open", 1.0)], fallback="page_only")
    return Parsed(None, slots, [], [])
