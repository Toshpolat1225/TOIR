"""Spoken numbers (Uzbek Latin + Russian) -> digits, and digit grouping, so that "o'ttiz yetti to'qqiz yuz o'n to'qqiz",
"тридцать семь девятьсот девятнадцать", "3 7 9 1 9" and "37 919" all become 37919 (inventory numbers are said in pieces).

Algorithm: a run of number words is split into groups (one group = a number below 1000: "o'ttiz yetti" = 37, "to'qqiz yuz o'n to'qqiz" = 919).
With an explicit "ming/тысяча" the run is evaluated arithmetically; without it the groups are CONCATENATED (37|919 -> 37919, 2|3|1|3 -> 2313).
"""
from __future__ import annotations

from app.services.assistant.normalize import normalize

_ONES = {
    "nol": 0, "ноль": 0, "нуль": 0, "bir": 1, "ikki": 2, "uch": 3, "tort": 4, "besh": 5, "olti": 6, "yetti": 7, "sakkiz": 8, "toqqiz": 9,
    "один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
}
_TEENS = {
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
    "восемнадцать": 18, "девятнадцать": 19,
}
_TENS = {
    "on": 10, "yigirma": 20, "ottiz": 30, "qirq": 40, "ellik": 50, "oltmish": 60, "yetmish": 70, "sakson": 80, "toqson": 90,
    "десять": 10, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
}
_HUNDREDS_RU = {"сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900}
_YUZ = {"yuz"}
_THOUSAND = {"ming", "тысяча", "тысячи", "тысяч", "тысячу"}
_FILLERS = {"va", "и"}


def _kind(token: str) -> str | None:
    if token in _ONES:
        return "ones"
    if token in _TEENS:
        return "teen"
    if token in _TENS:
        return "tens"
    if token in _HUNDREDS_RU:
        return "hundreds"
    if token in _YUZ:
        return "yuz"
    if token in _THOUSAND:
        return "thousand"
    return None


class _Group:
    def __init__(self) -> None:
        self.value = 0
        self.has_h = self.has_t = self.has_o = False
        self.last_ones: int | None = None  # a lone ones word that a following "yuz" would multiply
        self.empty = True

    def can_take(self, kind: str) -> bool:
        if kind == "yuz":
            return self.empty or (self.last_ones is not None and not self.has_t and not self.has_h)
        if kind == "hundreds":
            return self.empty
        if kind == "tens":
            return not (self.has_t or self.has_o)
        if kind == "teen":
            return not (self.has_t or self.has_o)
        if kind == "ones":
            return not self.has_o
        return False

    def add(self, kind: str, token: str) -> None:
        self.empty = False
        if kind == "ones":
            self.value += _ONES[token]
            self.has_o = True
            self.last_ones = _ONES[token] if self.value == _ONES[token] else None
        elif kind == "teen":
            self.value += _TEENS[token]
            self.has_t = self.has_o = True
            self.last_ones = None
        elif kind == "tens":
            self.value += _TENS[token]
            self.has_t = True
            self.last_ones = None
        elif kind == "hundreds":
            self.value += _HUNDREDS_RU[token]
            self.has_h = True
            self.last_ones = None
        elif kind == "yuz":
            self.value = (self.last_ones if self.last_ones else 1) * 100
            self.has_h = True
            self.has_t = self.has_o = False
            self.last_ones = None


def _evaluate(run: list[str]) -> str:
    """One run of number words -> digits."""
    if any(_kind(t) == "thousand" for t in run):
        total = current = 0
        group = _Group()
        for t in run:
            k = _kind(t)
            if k == "thousand":
                total += (group.value or 1) * 1000
                group = _Group()
            elif k and group.can_take(k):
                group.add(k, t)
            elif k:
                current += group.value
                group = _Group()
                group.add(k, t)
        return str(total + current + group.value)
    groups: list[_Group] = []
    group = _Group()
    for t in run:
        k = _kind(t)
        if k is None:
            continue
        if not group.can_take(k):
            groups.append(group)
            group = _Group()
        group.add(k, t)
    groups.append(group)
    return "".join(str(g.value) for g in groups if not g.empty)


def words_to_digits(text: str) -> str:
    """Replace every run of number words in an (already normalised) sentence by its digits."""
    toks = text.split()
    out: list[str] = []
    i = 0
    while i < len(toks):
        if _kind(toks[i]) is not None:
            j = i
            run: list[str] = []
            while j < len(toks) and (_kind(toks[j]) is not None or (toks[j] in _FILLERS and j + 1 < len(toks) and _kind(toks[j + 1]) is not None and run)):
                if toks[j] not in _FILLERS:
                    run.append(toks[j])
                j += 1
            out.append(_evaluate(run))
            i = j
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def join_digit_groups(text: str) -> str:
    """"37 919" -> "37919" (a thousands group) and "3 7 9 1 9" -> "37919" (digit by digit). Other neighbouring numbers stay apart."""
    toks = text.split()
    out: list[str] = []
    i = 0
    while i < len(toks):
        if toks[i].isdigit():
            j = i
            while j < len(toks) and toks[j].isdigit():
                j += 1
            run = toks[i:j]
            if len(run) >= 2 and all(len(t) == 1 for t in run):
                out.append("".join(run))
            elif len(run) >= 2 and 1 <= len(run[0]) <= 3 and all(len(t) == 3 for t in run[1:]):
                out.append("".join(run))
            else:
                out.extend(run)
            i = j
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def canonical(text: str) -> str:
    """normalise -> number words to digits -> digit groups joined. The form every later stage reads."""
    return join_digit_groups(words_to_digits(normalize(text)))
