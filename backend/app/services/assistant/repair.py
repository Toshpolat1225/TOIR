"""Speech-recogniser repair: map the words of a garbled sentence back to catalogue words.

A small local Whisper writes Uzbek as a mix of scripts and near-misses ("харитana otz" for "xaritani och", "naryadlir", "vaqon"). This module compares
every UNKNOWN token with the catalogue vocabulary on a phonetic fold (Cyrillic -> Latin, x/h, q/k, o/u, e/i/y collapsed, double letters merged) with a
small edit-distance budget, and replaces it by the catalogue word. It only runs when the strict parse found no keyword intent, so a correct sentence
is never touched. A tie between two different words is left alone (no guessing).
"""
from __future__ import annotations

import re
from functools import lru_cache

from app.services.assistant import catalog
from app.services.assistant.normalize import _CYR_TO_LAT, keyword_matches, normalize

_NUMBER = re.compile(r"^\d+$")
_VOWEL_FOLD = str.maketrans({"u": "o", "e": "i", "y": "i", "w": "v", "x": "h", "q": "k", "z": "s", "c": "s"})
_MIN_WORD = 4  # shorter vocabulary words / tokens are never repaired (too many collisions)
_SKIP = {"bu", "shu", "uni", "buni", "ona", "tez", "yana", "keyin"}


def fold(word: str) -> str:
    """Phonetic key of a normalised word: Latin letters only, confusable letters merged, doubles collapsed."""
    lat = "".join(_CYR_TO_LAT.get(c, c) for c in word.lower())
    lat = lat.replace("ch", "s").replace("sh", "s").replace("ts", "s").replace("ya", "ia").replace("yu", "io").replace("yo", "io")
    lat = lat.translate(_VOWEL_FOLD)
    out: list[str] = []
    for c in lat:
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def _distance(a: str, b: str, limit: int) -> int:
    """Damerau-Levenshtein (adjacent swap = 1), cut off above `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] | None = None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


@lru_cache(maxsize=1)
def vocabulary() -> tuple[tuple[str, str], ...]:
    """(normalised word, fold) for every single catalogue word of 4+ letters: intent keywords, page names, statuses."""
    words: set[str] = set()
    for intent in catalog.CATALOG:
        for group in (*intent.groups, *intent.boost):
            for w in group:
                for part in normalize(w.rstrip("*")).split():
                    words.add(part)
    for _path, _perm, names in catalog.PAGES.values():
        for name in names:
            for part in normalize(name).split():
                words.add(part)
    for names in catalog.STATUS_WORDS.values():
        for name in names:
            for part in normalize(name).split():
                words.add(part)
    return tuple(sorted((w, fold(w)) for w in words if len(w) >= _MIN_WORD and fold(w) and not _NUMBER.match(w)))


def _known(token: str, words: tuple[tuple[str, str], ...]) -> bool:
    return any(keyword_matches(token, w) for w, _f in words)


def _is_cyrillic(word: str) -> bool:
    return any("а" <= c <= "я" for c in word)


def _twins(token: str, words: tuple[tuple[str, str], ...]) -> str:
    """A known token written in the other script ("вагонлар" = Uzbek "vagonlar"): add the twin word of the other script so both spellings can match."""
    if len(token) < 5 or not _is_cyrillic(token):
        return ""
    key = fold(token)
    extra = [w for w, k in words if k == key and not _is_cyrillic(w) and not keyword_matches(token, w) and not keyword_matches(w, token)]
    return (" " + extra[0]) if extra else ""


def repair_token(token: str) -> str:
    """The catalogue word this token most likely means, or the token itself (known word, number, too short, no close match, a tie)."""
    if len(token) < _MIN_WORD or _NUMBER.match(token) or token in _SKIP:
        return token
    words = vocabulary()
    if _known(token, words):
        return token + _twins(token, words)
    key = fold(token)
    if len(key) < 3:
        return token
    best: tuple[int, int, str] | None = None  # (distance, -length, word)
    best_key = ""
    tie = False
    for word, wkey in words:
        if key[0] != wkey[0]:
            continue  # a recogniser seldom changes the first sound
        limit = 0 if len(wkey) < 6 else (1 if len(wkey) < 10 else 2)  # short words: only a phonetic twin (hello is not help)
        # the token may carry a suffix ("xaritana"): compare with the token cut to the word's length (+-1)
        d = min(_distance(cut, wkey, limit) for cut in {key[: len(wkey)], key[: len(wkey) + 1]})
        if d > limit:
            continue
        cand = (d, -len(word), word)
        if best is None or cand[:2] < best[:2]:
            best, best_key, tie = cand, wkey, False
        elif cand[:2] == best[:2] and cand[2] != best[2]:
            if wkey == best_key:  # the same word written in the other script ("аналитика" / "analitika"): not a real tie, keep the token's own script
                if _is_cyrillic(word) == _is_cyrillic(token) and _is_cyrillic(best[2]) != _is_cyrillic(token):
                    best = cand
            else:
                tie = True
    if best is None or tie:
        return token
    return best[2]


def repair_text(canonical_text: str) -> str:
    """The sentence with every unknown token replaced by its closest catalogue word."""
    return " ".join(repair_token(t) for t in canonical_text.split())
