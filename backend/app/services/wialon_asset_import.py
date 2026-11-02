"""Pure helpers for classifying Wialon unit names during asset import."""

from __future__ import annotations

import re

_LOCOMOTIVE_PREFIX = re.compile(
    r"^(?:(?:м|m)(?:п|p)(?:э|e)|(?:п|p)(?:э|e))-",
    re.IGNORECASE,
)
_DIESEL_PREFIX = re.compile(r"^[тt][эe][мm]", re.IGNORECASE)
_TWO_TE_PREFIX = re.compile(r"^2[тt][эe]\d+", re.IGNORECASE)
_LOCOMOTIVE_SERIES = re.compile(
    r"^(?:(?:м|m)(?:п|p)(?:э|e)|(?:п|p)(?:э|e))"
    r"\s*-\s*\d+[a-zа-яё]?",
    re.IGNORECASE,
)
_DIESEL_SERIES = re.compile(
    r"^[тt][эe][мm]\s*\d+[a-zа-яё]*(?:\s+[a-zа-яё]+)?",
    re.IGNORECASE,
)


def classify_asset_type(name: str | None) -> str | None:
    """Return a TOIR asset type for supported Cyrillic or Latin prefixes."""
    normalized = (name or "").strip().casefold()
    if _LOCOMOTIVE_PREFIX.match(normalized):
        return "locomotive"
    if _DIESEL_PREFIX.match(normalized) or _TWO_TE_PREFIX.match(normalized):
        return "diesel"
    return None


def extract_asset_series(name: str | None) -> str | None:
    """Extract the model designation, excluding a trailing unit number."""
    value = (name or "").strip()
    two_te_match = _TWO_TE_PREFIX.match(value)
    if two_te_match is not None:
        return two_te_match.group(0).translate(
            str.maketrans({"t": "Т", "T": "Т", "e": "Э", "E": "Э", "т": "Т", "э": "Э"})
        )
    match = _LOCOMOTIVE_SERIES.match(value) or _DIESEL_SERIES.match(value)
    if match is None:
        return None
    return " ".join(match.group(0).split())
