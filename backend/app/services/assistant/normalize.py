"""Text normalisation for the command centre: one canonical form for typed text and for speech-recogniser output.

Lower case; every kind of apostrophe/modifier letter removed from Uzbek Latin words (o'tgan -> otgan, ko'rsat -> korsat) so that
"o‘tgan", "o'tgan" and "otgan" are one word; Uzbek-only Cyrillic letters folded to Latin (ў ғ қ ҳ), "ё" to "е"; punctuation to spaces.
Russian stays Cyrillic. The catalogue keywords are normalised with the same function, so both sides always agree.
"""
from __future__ import annotations

import re

_APOSTROPHES = "'`´ʻʼ’‘′ʹ"
_CYR_UZ = str.maketrans({"ў": "o", "ғ": "g", "қ": "q", "ҳ": "h", "ё": "е", "Ў": "o", "Ғ": "g", "Қ": "q", "Ҳ": "h", "Ё": "е"})
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ь": "",
    "ы": "i", "э": "e", "ю": "yu", "я": "ya",
}
_UZ_ONLY = set("ўғқҳЎҒҚҲ")
_PUNCT = re.compile(r"[^0-9a-zа-я\s]+", re.IGNORECASE)
_SPACES = re.compile(r"\s+")
_DASH_BETWEEN_DIGITS = re.compile(r"(?<=\d)[-–—.,](?=\d{3}\b)")  # 37-919 / 37.919 / 37,919 -> 37919 (a thousands separator)


def normalize(text: str) -> str:
    raw = (text or "").strip().lower()
    if any(c in _UZ_ONLY for c in raw):  # a Cyrillic-written UZBEK sentence (it has ў ғ қ ҳ): transliterate the whole of it to Latin
        raw = "".join(_CYR_TO_LAT.get(c, c) for c in raw.translate(_CYR_UZ))
    t = raw.translate(_CYR_UZ)
    for ch in _APOSTROPHES:
        t = t.replace(ch, "")
    t = _DASH_BETWEEN_DIGITS.sub("", t)
    t = t.replace("-", " ").replace("_", " ")
    t = _PUNCT.sub(" ", t)
    return _SPACES.sub(" ", t).strip()


def tokens(text: str) -> list[str]:
    return normalize(text).split()


def is_cyrillic_dominant(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    cyr = sum(1 for c in letters if "а" <= c.lower() <= "я" or c.lower() == "ё")
    return cyr / len(letters) > 0.5


def detect_locale(text: str) -> str:
    """ru for Cyrillic-dominant text (Uzbek-only Cyrillic letters count as Uzbek), else uz."""
    if any(c in text for c in "ўғқҳЎҒҚҲ"):
        return "uz"
    return "ru" if is_cyrillic_dominant(text) else "uz"


def keyword_matches(token: str, keyword: str) -> bool:
    """A keyword of 5+ letters matches as a prefix of the token (Uzbek/Russian suffixes); a shorter one must equal the token; "stem*" is a prefix of any length."""
    if keyword.endswith("*"):
        return token.startswith(keyword[:-1])
    if len(keyword) >= 5:
        return token.startswith(keyword)
    return token == keyword


def phrase_matches(text: str, phrase: str) -> bool:
    """A multi-word keyword ("не работ", "что умеешь") matches at word starts inside the sentence."""
    return f" {phrase.rstrip('*')}" in f" {text}"
