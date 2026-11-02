"""Wialon hisoblagichlari uchun sifat darvozasi (quality gate). Sof mantiq: DB va tarmoq yo'q.

Qoidalar (2026-10 Wialon tahlilidan):
- TOIR mileage'i Wialon absolyut `cnm` bilan emas, uning O'SISHI (delta) bilan yuritiladi.
  Sabab: HILUX 366 `cnm` ida +1 007 019 507 km siljish bor, lekin o'sishi to'g'ri.
- API `cnm` ni butun km ga qirqadi (Telegram yaxlitlaydi): 1 km gacha kamayish xato emas.
- Hisoblagichlar qadam-qadam yangilanadi (1-2 daqiqada 3-5 km, moto-soat 52 minutgacha oldinga).
  Shuning uchun chegaralar zaxira bilan: cnm <= 150 km/soat * dt + 10 km; cneh <= dt + 1 soat.
- cneh=0 "0 soat" emas, "ma'lumot yo'q" (kontakt datchigi ishlamaydigan birliklar).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

MAX_SPEED_KMH = Decimal("150")
JUMP_SLACK_KM = Decimal("10")
ROUNDING_KM = Decimal("1")
HOURS_SLACK = Decimal("1")
HOURS_ROUNDING = Decimal("0.01")
SUSPECT_ABSOLUTE_KM = Decimal("1000000")
SUSPECT_AVG_SPEED_KMH = Decimal("100")
STALE_AFTER = timedelta(hours=24)
_ZERO = Decimal("0")


class Verdict(str, Enum):
    BASELINE = "baseline"    # birinchi o'qish: faqat baseline saqlanadi, TOIR qiymati o'zgarmaydi
    ACCEPTED = "accepted"    # delta TOIR'ga qo'shiladi
    UNCHANGED = "unchanged"  # o'zgarish yo'q
    REJECTED = "rejected"    # shubhali; yozilmaydi, audit'ga tushadi
    STALE = "stale"          # xabar juda eski; e'tiborga olinmaydi
    NO_DATA = "no_data"      # hisoblagich yo'q yoki hisoblanmayapti


@dataclass(frozen=True)
class CounterState:
    baseline_cnm: Decimal | None = None
    last_cnm: Decimal | None = None
    last_cnm_at: datetime | None = None
    baseline_cneh: Decimal | None = None
    last_cneh: Decimal | None = None
    last_cneh_at: datetime | None = None


@dataclass(frozen=True)
class Reading:
    cnm: Decimal | None
    cneh: Decimal | None
    at: datetime | None  # oxirgi xabar vaqti (UTC, timezone-aware)


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    delta: Decimal | None = None
    reason: str | None = None


@dataclass(frozen=True)
class GateResult:
    mileage: Decision
    hours: Decision
    state: CounterState          # saqlanadigan yangi holat
    suspect_absolute: bool       # absolyut qiymat ishonchsiz (faqat ma'lumot uchun)


def _hours(a: datetime, b: datetime) -> Decimal:
    return Decimal(str((b - a).total_seconds())) / Decimal("3600")


def suspect_absolute(cnm: Decimal | None, cneh: Decimal | None) -> bool:
    if cnm is None:
        return False
    if cnm > SUSPECT_ABSOLUTE_KM:
        return True
    return cneh is not None and cneh > 1 and cnm / cneh > SUSPECT_AVG_SPEED_KMH


def _mileage(state: CounterState, r: Reading) -> tuple[Decision, dict]:
    if r.cnm is None or r.at is None:
        return Decision(Verdict.NO_DATA, reason="cnm yoki xabar vaqti yo'q"), {}
    if state.last_cnm is None or state.last_cnm_at is None:
        return Decision(Verdict.BASELINE, _ZERO), {
            "baseline_cnm": r.cnm, "last_cnm": r.cnm, "last_cnm_at": r.at}
    if r.at <= state.last_cnm_at:
        return Decision(Verdict.UNCHANGED, _ZERO, "yangi xabar yo'q"), {}
    dc = r.cnm - state.last_cnm
    if dc < -ROUNDING_KM:
        return Decision(Verdict.REJECTED, reason=f"cnm kamaydi: {dc:+}"), {}
    if dc <= 0:   # 0 yoki -1..0: yaxlitlash/qirqish; orqaga yurmaymiz
        return Decision(Verdict.UNCHANGED, _ZERO), {"last_cnm_at": r.at}
    limit = MAX_SPEED_KMH * _hours(state.last_cnm_at, r.at) + JUMP_SLACK_KM
    if dc > limit:
        return Decision(Verdict.REJECTED, reason=f"cnm sakradi: +{dc} km, ruxsat {limit:.1f} km"), {}
    return Decision(Verdict.ACCEPTED, dc), {"last_cnm": r.cnm, "last_cnm_at": r.at}


def _hours_decision(state: CounterState, r: Reading) -> tuple[Decision, dict]:
    if r.cneh is None or r.at is None:
        return Decision(Verdict.NO_DATA, reason="cneh yo'q"), {}
    if r.cneh <= 0 and not (state.last_cneh and state.last_cneh > 0):
        return Decision(Verdict.NO_DATA, reason="cneh=0: moto-soat hisoblanmayapti"), {}
    if state.last_cneh is None or state.last_cneh_at is None:
        return Decision(Verdict.BASELINE, _ZERO), {
            "baseline_cneh": r.cneh, "last_cneh": r.cneh, "last_cneh_at": r.at}
    if r.at <= state.last_cneh_at:
        return Decision(Verdict.UNCHANGED, _ZERO, "yangi xabar yo'q"), {}
    dh = r.cneh - state.last_cneh
    if dh < -HOURS_ROUNDING:
        return Decision(Verdict.REJECTED, reason=f"cneh kamaydi: {dh:+}"), {}
    if dh <= HOURS_ROUNDING:
        return Decision(Verdict.UNCHANGED, _ZERO), {"last_cneh_at": r.at}
    limit = _hours(state.last_cneh_at, r.at) + HOURS_SLACK
    if dh > limit:
        return Decision(Verdict.REJECTED, reason=f"cneh real vaqtdan katta: +{dh} soat, ruxsat {limit:.2f}"), {}
    return Decision(Verdict.ACCEPTED, dh), {"last_cneh": r.cneh, "last_cneh_at": r.at}


def evaluate(state: CounterState | None, reading: Reading, *, now: datetime) -> GateResult:
    state = state or CounterState()
    flag = suspect_absolute(reading.cnm, reading.cneh)
    if reading.at is not None and now - reading.at > STALE_AFTER:
        stale = Decision(Verdict.STALE, reason="oxirgi xabar 24 soatdan eski")
        return GateResult(stale, stale, state, flag)
    m, m_upd = _mileage(state, reading)
    h, h_upd = _hours_decision(state, reading)
    new_state = CounterState(**{**state.__dict__, **m_upd, **h_upd})
    return GateResult(m, h, new_state, flag)
