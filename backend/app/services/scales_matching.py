"""Pure matching logic for the weighing-scale feed (no database, no clock): every rule here is unit-tested.

Facts it encodes (measured on the real data, see docs/VESOVOY_ANALYSIS.md):
- the scale's «Номер состава» is the main locomotive's garage number (GTK `gtk_trains.number`, `gtk_locomotives.garage_number`);
- a 15-unit train is 2 traction-aggregate units (tare ~126 t) plus the dump cars; the dump cars are the GTK carriages;
- the scale tare is a default (49 t), the scale's train «Вес» also counts the traction units, so the real cargo is the sum of the
  dump cars' net, or, when the wagon rows are missing, «Вес» minus a median offset learned from complete trains.
"""
from __future__ import annotations

import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

_SPACES = re.compile(r"\s+")
MIN_OFFSET_SAMPLES = 20


def normalize_loco_number(raw: str | None) -> str | None:
    """The operator types the number by hand: trim, drop inner spaces, upper-case. Empty means unknown."""
    if raw is None:
        return None
    value = _SPACES.sub("", str(raw)).upper()
    return value or None


def loco_keys(number: str) -> list[str]:
    """Exact first, then without leading zeros ('074' also finds '74'); the order is the match priority."""
    keys = [number]
    stripped = number.lstrip("0")
    if stripped and stripped != number:
        keys.append(stripped)
    return keys


@dataclass(frozen=True)
class Unit:
    gross: Decimal | None
    tare: Decimal | None
    net: Decimal | None
    capacity: Decimal | None = None
    position: int | None = None
    ref: object | None = None  # the caller's handle (weighing id) to write the unit kind back


def unit_kind(unit: Unit, tare_min: float) -> str:
    return "traction" if unit.tare is not None and float(unit.tare) >= tare_min else "dump"


@dataclass(frozen=True)
class TrainSummary:
    dump_count: int
    traction_count: int
    net_total_t: Decimal | None
    net_source: str | None  # 'weighings' | 'estimated' | None
    flags: tuple[str, ...]
    kinds: tuple[str, ...] = ()  # 'traction' | 'dump', aligned with the input units


def summarize_train(
    units: Sequence[Unit],
    *,
    tare_min: float,
    tare_default: Decimal | None,
    declared_wagons: int | None,
    reported_weight_t: Decimal | None,
    offset_t: Decimal | None,
    traction_hint: int | None = None,
) -> TrainSummary:
    """`traction_hint` = how many units are traction units, known from GTK (weighed units minus GTK carriages); the heaviest tares win.

    Without GTK the tare threshold decides. The hint matters because some dump cars carry a real weighed tare of 100-112 t, which a
    threshold alone would take for a traction unit (and drop ~100 t of cargo from the train).
    """
    if traction_hint is None:
        kinds = [unit_kind(u, tare_min) for u in units]
    else:
        rank = sorted(
            range(len(units)),
            key=lambda i: (-(float(units[i].tare) if units[i].tare is not None else -1.0), units[i].position if units[i].position is not None else 10**6, i),
        )
        heavy = set(rank[:traction_hint])
        kinds = ["traction" if i in heavy else "dump" for i in range(len(units))]
    dumps = [u for u, k in zip(units, kinds) if k == "dump"]
    traction = len(units) - len(dumps)
    flags: list[str] = []
    declared = declared_wagons or 0
    if not units and declared > 0:
        flags.append("no_wagon_rows")
    elif declared and len(units) < declared:
        flags.append("partial_wagon_rows")
    nets = [u.net for u in dumps if u.net is not None]
    net_total: Decimal | None = None
    source: str | None = None
    if dumps and len(nets) == len(dumps) and not (declared and len(units) < declared):
        net_total = sum(nets, Decimal(0)).quantize(Decimal("0.01"))
        source = "weighings"
    elif reported_weight_t is not None and offset_t is not None and declared > 0:
        estimate = (reported_weight_t - offset_t).quantize(Decimal("0.01"))
        if estimate > 0:
            net_total, source = estimate, "estimated"
            flags.append("estimated_net")
    if dumps and tare_default is not None and all(u.tare is not None and u.tare == tare_default for u in dumps):
        flags.append("default_tare")
    if any(u.net is not None and u.net < 0 for u in dumps):
        flags.append("negative_net")
    if any(u.net is not None and u.capacity and u.net > u.capacity for u in dumps):
        flags.append("overload")
    if traction_hint is not None:
        flags.append("traction_inferred")
    return TrainSummary(len(dumps), traction, net_total, source, tuple(flags), tuple(kinds))


def estimate_offset(samples: Iterable[Decimal]) -> Decimal | None:
    """Median of («Вес» − real net) over complete trains; needs enough samples to mean anything."""
    values = [float(v) for v in samples]
    if len(values) < MIN_OFFSET_SAMPLES:
        return None
    return Decimal(str(round(statistics.median(values), 2)))


@dataclass(frozen=True)
class Member:
    train_gtk_id: int
    kind: str  # 'locomotive' | 'carriage'
    object_gtk_id: int
    is_main: bool
    ord: int
    observed_from: datetime
    observed_to: datetime | None


def _overlap_seconds(start: datetime, end: datetime, m_from: datetime, m_to: datetime | None) -> float:
    upper = end if m_to is None else min(end, m_to)
    lower = max(start, m_from)
    return max(0.0, (upper - lower).total_seconds())


def _touches(start: datetime, end: datetime, member: Member) -> bool:
    return member.observed_from <= end and (member.observed_to is None or member.observed_to >= start)


def window(started_at: datetime | None, finished_at: datetime | None, tol: timedelta) -> tuple[datetime, datetime] | None:
    if started_at is None:
        return None
    end = finished_at if finished_at is not None and finished_at >= started_at else started_at
    return started_at - tol, end + tol


def find_gtk_train(loco_gtk_ids: set[int], members: Iterable[Member], win: tuple[datetime, datetime] | None) -> int | None:
    """The GTK train whose main locomotive is one of `loco_gtk_ids` for the longest part of the weighing window."""
    if win is None or not loco_gtk_ids:
        return None
    best: tuple[float, int] | None = None
    for m in members:
        if m.kind != "locomotive" or not m.is_main or m.object_gtk_id not in loco_gtk_ids or not _touches(win[0], win[1], m):
            continue
        score = (_overlap_seconds(win[0], win[1], m.observed_from, m.observed_to), m.train_gtk_id)
        if best is None or score > best:
            best = score
    return best[1] if best else None


def carriages_in_train(train_gtk_id: int, members: Iterable[Member], win: tuple[datetime, datetime] | None) -> list[Member]:
    if win is None:
        return []
    found: dict[int, Member] = {}
    for m in members:
        if m.train_gtk_id != train_gtk_id or m.kind != "carriage" or not _touches(win[0], win[1], m):
            continue
        known = found.get(m.object_gtk_id)
        if known is None or m.ord < known.ord:
            found[m.object_gtk_id] = m
    return sorted(found.values(), key=lambda m: (m.ord, m.object_gtk_id))


def assign_units_to_carriages(
    dump_units: Sequence[Unit], carriages: Sequence[Member], *, order: str = "asc"
) -> list[tuple[Member, Unit]]:
    """Pair each dump car's weighing with its GTK carriage by sequence: scale position order <-> GTK `ord` order.

    GTK counts the cars from the locomotive (ord 1 = next to it) and the scale lists the units from the head of the train, so with
    the traction units removed both sequences run the same way (`asc`, confirmed by the owner). Only an exact count is paired: a
    different count means a car was added/removed or a row is missing, and guessing would put tonnes on the wrong wagon.
    """
    if not dump_units or len(dump_units) != len(carriages):
        return []
    units = sorted(dump_units, key=lambda u: (u.position if u.position is not None else 10**6, str(u.ref)))
    cars = sorted(carriages, key=lambda c: (c.ord, c.object_gtk_id), reverse=order == "desc")
    return list(zip(cars, units))


def suggest_locos(members: Iterable[Member], win: tuple[datetime, datetime] | None, limit: int = 3) -> list[tuple[int, int, float]]:
    """For a train whose number does not resolve: GTK main locomotives working during the window, best overlap first.

    Returns (loco_gtk_id, gtk_train_id, overlap_seconds). Only a suggestion: the operator confirms it as an alias.
    """
    if win is None:
        return []
    scored: dict[int, tuple[float, int]] = {}
    for m in members:
        if m.kind != "locomotive" or not m.is_main or not _touches(win[0], win[1], m):
            continue
        seconds = _overlap_seconds(win[0], win[1], m.observed_from, m.observed_to)
        if seconds <= 0:
            continue
        old = scored.get(m.object_gtk_id)
        if old is None or seconds > old[0]:
            scored[m.object_gtk_id] = (seconds, m.train_gtk_id)
    ranked = sorted(scored.items(), key=lambda kv: kv[1][0], reverse=True)
    return [(loco, train, seconds) for loco, (seconds, train) in ranked[:limit]]


@dataclass(frozen=True)
class LocoResolution:
    asset_id: UUID | None
    gtk_ids: frozenset[int]
    method: str | None  # 'alias' | 'gtk_garage' | None


def resolve_loco(
    number: str | None,
    *,
    aliases: Mapping[str, UUID],
    garage_index: Mapping[str, Sequence[int]],
    asset_by_loco_gtk: Mapping[int, UUID],
    loco_gtk_by_asset: Mapping[UUID, int],
) -> LocoResolution:
    """Alias (operator correction) wins over the GTK garage number; the loco asset is the GTK link of the matched locomotive."""
    if number is None:
        return LocoResolution(None, frozenset(), None)
    for key in loco_keys(number):
        if key in aliases:
            asset = aliases[key]
            gtk = loco_gtk_by_asset.get(asset)
            return LocoResolution(asset, frozenset({gtk}) if gtk is not None else frozenset(), "alias")
    for key in loco_keys(number):
        ids = garage_index.get(key)
        if ids:
            assets = [asset_by_loco_gtk[i] for i in ids if i in asset_by_loco_gtk]
            return LocoResolution(assets[0] if len(assets) == 1 else None, frozenset(ids), "gtk_garage")
    return LocoResolution(None, frozenset(), None)


@dataclass
class MatchResult:
    status: str  # 'ok' | 'no_loco' | 'no_gtk_train' | 'excluded'
    method: str | None
    loco_asset_id: UUID | None
    loco_gtk_id: int | None
    gtk_train_id: int | None
    carriages: list[Member] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def match_train(
    *,
    number: str | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    dump_count: int,
    excluded: bool,
    forced_gtk_train: int | None,
    tolerance: timedelta,
    members: Sequence[Member],
    aliases: Mapping[str, UUID],
    garage_index: Mapping[str, Sequence[int]],
    asset_by_loco_gtk: Mapping[int, UUID],
    loco_gtk_by_asset: Mapping[UUID, int],
) -> MatchResult:
    if excluded:
        return MatchResult("excluded", None, None, None, None)
    win = window(started_at, finished_at, tolerance)
    loco = resolve_loco(
        number, aliases=aliases, garage_index=garage_index, asset_by_loco_gtk=asset_by_loco_gtk, loco_gtk_by_asset=loco_gtk_by_asset
    )
    gtk_train: int | None = None
    method = loco.method
    if forced_gtk_train is not None:
        gtk_train, method = forced_gtk_train, "forced"
    elif loco.gtk_ids:
        gtk_train = find_gtk_train(set(loco.gtk_ids), members, win)
    loco_gtk = None
    if gtk_train is not None:
        main = [m.object_gtk_id for m in members if m.train_gtk_id == gtk_train and m.kind == "locomotive" and m.is_main]
        loco_gtk = next((i for i in main if i in loco.gtk_ids), main[0] if main else None)
    elif len(loco.gtk_ids) == 1:
        loco_gtk = next(iter(loco.gtk_ids))
    loco_asset = loco.asset_id or (asset_by_loco_gtk.get(loco_gtk) if loco_gtk is not None else None)
    if gtk_train is None:
        status = "no_gtk_train" if (loco.gtk_ids or loco.asset_id) else "no_loco"
        return MatchResult(status, method, loco_asset, loco_gtk, None)
    carriages = carriages_in_train(gtk_train, members, win)
    flags = ["count_mismatch"] if dump_count and len(carriages) != dump_count else []
    return MatchResult("ok", method, loco_asset, loco_gtk, gtk_train, carriages, flags)
