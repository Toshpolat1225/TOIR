"""Wagon segments: where a wagon was (behind which locomotive) and how far it went, with four distance candidates.

A wagon has no GPS of its own. For every GTK membership interval of a carriage (split at local midnights, so closed days never change) the
locomotive that pulled it is found (the main one; a switch of locomotive splits the interval) and four candidates are computed from that
locomotive's tracks: A the Wialon odometer, B the Wialon track, C the GTK track, D the fused track. `gps_analytics.select_candidate`
picks one (never a sum or an average) and says how sure it is. Nothing here writes into the wagon mileage ledger: it is read by the GPS
page and by the dry-run comparison `wagon-gps-diff`; wiring it into the ledger is a separate, approved step.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrainMember
from app.models.gtk_gps import GpsWagonSegment
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.services import gps_analytics as ga
from app.services import gps_assessment as assessment
from app.services import gtk_gps

logger = logging.getLogger(__name__)

MIN_SEGMENT_S = 60  # shorter slices are noise at the interval edges


@dataclass(frozen=True)
class Slice:
    t0: datetime
    t1: datetime
    loco_gtk_id: int


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def pick_loco(members: list, at: datetime):
    """The locomotive of a train at an instant: the main one, then the lowest order."""
    live = [m for m in members if _aware(m.observed_from) <= at and (m.observed_to is None or _aware(m.observed_to) > at)]
    return min(live, key=lambda m: (not m.is_main, m.ord, m.object_gtk_id)) if live else None


def loco_slices(locos: list, t0: datetime, t1: datetime, now: datetime) -> list[Slice]:
    """Cut [t0, t1] at every instant a locomotive joins/leaves and keep the best locomotive per piece (consecutive equal pieces merged)."""
    cuts = {t0, t1}
    for m in locos:
        for t in (_aware(m.observed_from), _aware(m.observed_to) if m.observed_to is not None else now):
            if t0 < t < t1:
                cuts.add(t)
    edges = sorted(cuts)
    out: list[Slice] = []
    for a, b in zip(edges, edges[1:]):
        mid = a + (b - a) / 2
        best = pick_loco(locos, mid)
        if best is None or (b - a).total_seconds() < MIN_SEGMENT_S:
            continue
        if out and out[-1].loco_gtk_id == best.object_gtk_id and out[-1].t1 == a:
            out[-1] = Slice(out[-1].t0, b, best.object_gtk_id)
        else:
            out.append(Slice(a, b, best.object_gtk_id))
    return out


def split_by_local_day(t0: datetime, t1: datetime, offset_hours: int) -> list[tuple[datetime, datetime]]:
    """[t0, t1] cut at local midnights."""
    out: list[tuple[datetime, datetime]] = []
    cur = t0
    while cur < t1:
        local = cur + timedelta(hours=offset_hours)
        nxt = (datetime(local.year, local.month, local.day, tzinfo=timezone.utc) + timedelta(days=1)) - timedelta(hours=offset_hours)
        end = min(t1, nxt)
        out.append((cur, end))
        cur = end
    return out


async def _odometer(db: AsyncSession, asset_id: UUID, lo: datetime, hi: datetime) -> list[tuple[datetime, float]]:
    rows = await db.execute(
        text(
            "SELECT reading_at, odometer_km::float8 FROM wialon_odometer_readings "
            "WHERE asset_id = :a AND accepted AND odometer_km IS NOT NULL AND reading_at >= :lo AND reading_at <= :hi ORDER BY reading_at"
        ),
        {"a": asset_id, "lo": lo, "hi": hi},
    )
    return [(at, km) for at, km in rows.all()]


# Reasons of a HELD odometer decision that GPS tracks cannot cure (the problem is not the missing odometer)
UNRECOVERABLE_HELD = {"approved_opening_balance_missing", "no_linked_locomotive", "locomotive_handoff_time_unknown"}


async def make_track_fallback(db: AsyncSession):
    """An async callable `(locomotive_asset_id, start, end) -> dict | None` for the wagon mileage run.

    It serves the periods the odometer cannot (HELD): the km is the selected candidate of the locomotive's tracks (never a sum or an
    average of sources), reported with the basis and the confidence so the ledger row says exactly where the number came from.
    """
    cache: dict[tuple[UUID, datetime, datetime], dict | None] = {}

    async def fallback(loco_asset_id: UUID, start: datetime, end: datetime) -> dict | None:
        key = (loco_asset_id, start, end)
        if key in cache:
            return cache[key]
        lo, hi = start - timedelta(hours=1), end + timedelta(hours=1)
        w = (await assessment._load_points(db, [loco_asset_id], "wialon", lo, hi)).get(loco_asset_id, [])
        g = (await assessment._load_points(db, [loco_asset_id], "gtk_gps", lo, hi)).get(loco_asset_id, [])
        odo = await _odometer(db, loco_asset_id, lo - timedelta(hours=4), hi + timedelta(hours=4))
        cands = ga.candidates(w, g, odo, start, end)
        sel = ga.select_candidate(cands)
        result = None
        if sel.selected_km is not None and sel.basis != "held":
            result = {
                "km": Decimal(str(round(sel.selected_km, 2))), "basis": sel.basis, "confidence": sel.confidence, "flags": sel.flags,
                "candidates": {"odometer": cands.a_odometer, "wialon": cands.b_wialon, "gtk": cands.c_gtk, "fused": cands.d_fused, "coverage": cands.coverage_d},
            }
        cache[key] = result
        return result

    return fallback


async def compute_segments(db: AsyncSession, now: datetime | None = None, *, back_days: int = 3, progress=None) -> int:
    """(Re)compute the wagon segments touching the last `back_days` days; returns the number of rows written."""
    now = now or datetime.now(timezone.utc)
    offset = settings.gtk_utc_offset_hours
    # aligned to a local midnight: a piece that starts at `since` must keep the same key from cycle to cycle
    since = assessment.local_day_bounds(assessment.local_today(now - timedelta(days=back_days), offset), offset)[0]
    members = (
        await db.execute(select(GtkTrainMember).where((GtkTrainMember.observed_to.is_(None)) | (GtkTrainMember.observed_to >= since)))
    ).scalars().all()
    if not members:
        return 0
    loco_asset_of = {gid: asset for gid, asset in (await gtk_gps.linked_targets(db)).items()}
    carriage_ids = {m.object_gtk_id for m in members if m.kind == "carriage"}
    wagon_asset_of: dict[int, UUID] = {}
    if carriage_ids:
        rows = await db.execute(
            select(AssetSourceLink.external_id, AssetSourceLink.asset_id)
            .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
            .where(AssetSourceLink.source == "gtk", AssetSourceLink.status == "active", FixedAsset.asset_type.not_in(LOCOMOTIVE_TYPES))
        )
        wagon_asset_of = {int(e): a for e, a in rows.all() if str(e).isdigit() and int(e) in carriage_ids}
    by_train: dict[int, dict[str, list]] = defaultdict(lambda: {"loco": [], "carriage": []})
    for m in members:
        by_train[m.train_gtk_id]["loco" if m.kind == "locomotive" else "carriage"].append(m)

    # 1. all (carriage, piece) jobs with their locomotive
    jobs: list[dict] = []
    for train, groups in by_train.items():
        for c in groups["carriage"]:
            c0, c1 = max(_aware(c.observed_from), since), (_aware(c.observed_to) if c.observed_to is not None else now)
            if c1 <= c0:
                continue
            for s in loco_slices(groups["loco"], c0, c1, now):
                for d0, d1 in split_by_local_day(s.t0, s.t1, offset):
                    if (d1 - d0).total_seconds() >= MIN_SEGMENT_S:
                        jobs.append({"carriage": c.object_gtk_id, "train": train, "loco_gtk": s.loco_gtk_id, "t0": d0, "t1": d1, "open": c.observed_to is None and d1 >= now - timedelta(seconds=1)})
    # 2. candidates once per (locomotive, piece), the points loaded once per locomotive
    pieces: dict[tuple[int, datetime, datetime], ga.Candidates | None] = {}
    need: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    for j in jobs:
        key = (j["loco_gtk"], j["t0"], j["t1"])
        if key not in pieces:
            pieces[key] = None
            need[j["loco_gtk"]].append((j["t0"], j["t1"]))
    for loco_gtk, spans in need.items():
        asset = loco_asset_of.get(loco_gtk)
        if asset is None:
            continue
        lo, hi = min(a for a, _ in spans) - timedelta(hours=1), max(b for _, b in spans) + timedelta(hours=1)
        w = (await assessment._load_points(db, [asset], "wialon", lo, hi)).get(asset, [])
        g = (await assessment._load_points(db, [asset], "gtk_gps", lo, hi)).get(asset, [])
        odo = await _odometer(db, asset, lo - timedelta(hours=4), hi + timedelta(hours=4))
        for a, b in spans:
            pieces[(loco_gtk, a, b)] = ga.candidates(w, g, odo, a, b)
        if progress:
            progress(f"loco {loco_gtk}: {len(spans)} pieces")
    # 3. rows
    rows_out: list[dict] = []
    for j in jobs:
        cands = pieces.get((j["loco_gtk"], j["t0"], j["t1"]))
        loco_asset = loco_asset_of.get(j["loco_gtk"])
        if cands is None:
            sel = ga.Selection(None, "held", "none", ["no_loco" if loco_asset is None else "no_data"])
            km = (None, None, None, None)
            cov = None
        else:
            sel = ga.select_candidate(cands)
            km = (cands.a_odometer, cands.b_wialon, cands.c_gtk, cands.d_fused)
            cov = cands.coverage_d
        rows_out.append(
            {
                "wagon_asset_id": wagon_asset_of.get(j["carriage"]), "carriage_gtk_id": j["carriage"], "train_gtk_id": j["train"],
                "loco_asset_id": loco_asset, "loco_gtk_id": j["loco_gtk"], "period_from": j["t0"], "period_to": j["t1"], "is_open": j["open"],
                "km_odometer": _d(km[0]), "km_wialon": _d(km[1]), "km_gtk": _d(km[2]), "km_fused": _d(km[3]), "selected_km": _d(sel.selected_km),
                "basis": sel.basis, "confidence": sel.confidence, "coverage": _d(cov, 3), "flags": sel.flags or None,
                "algorithm_version": ga.ALGORITHM_VERSION, "computed_at": now,
            }
        )
    for i in range(0, len(rows_out), 500):
        stmt = insert(GpsWagonSegment).values(rows_out[i : i + 500])
        update = {c: getattr(stmt.excluded, c) for c in rows_out[0] if c not in ("carriage_gtk_id", "train_gtk_id", "period_from")}
        await db.execute(stmt.on_conflict_do_update(constraint="uq_gps_wagon_segments_key", set_=update))
    await db.commit()
    return len(rows_out)


def _d(value: float | None, places: int = 3) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, places)))


async def diff_against_ledger(db: AsyncSession, days: int, now: datetime | None = None) -> dict:
    """Dry run: how the selected km differs from the existing wagon mileage ledger **over the periods the ledger actually covers**.

    The ledger started on its first run (not at the start of the GTK history), so a plain sum over `days` would compare unequal windows.
    Each segment's km is prorated by its time overlap with every active ledger row of the same wagon.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    led = await db.execute(
        text(
            "SELECT l.wagon_asset_id, sum(l.distance_km)::float8 AS km, count(*) AS n FROM wagon_mileage_ledger l "
            "WHERE l.status = 'active' AND l.period_from >= :s AND l.distance_km IS NOT NULL AND NOT EXISTS (SELECT 1 FROM wagon_mileage_ledger l2 WHERE l2.supersedes_id = l.id) GROUP BY 1"
        ),
        {"s": since},
    )
    ledger = {r.wagon_asset_id: (r.km, r.n) for r in led}
    seg = await db.execute(
        text(
            "SELECT l.wagon_asset_id, sum(s.selected_km * (extract(epoch FROM (least(s.period_to, l.period_to) - greatest(s.period_from, l.period_from))) "
            "/ nullif(extract(epoch FROM (s.period_to - s.period_from)), 0)))::float8 AS km, bool_or(s.confidence = 'low') AS low, "
            "string_agg(DISTINCT s.basis, ',') AS bases "
            "FROM wagon_mileage_ledger l JOIN gps_wagon_segments s ON s.wagon_asset_id = l.wagon_asset_id AND s.period_from < l.period_to AND s.period_to > l.period_from "
            "WHERE l.status = 'active' AND l.period_from >= :s AND l.distance_km IS NOT NULL AND s.selected_km IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM wagon_mileage_ledger l2 WHERE l2.supersedes_id = l.id) GROUP BY 1"
        ),
        {"s": since},
    )
    selected = {r.wagon_asset_id: (r.km, r.low, r.bases) for r in seg}
    both = [(a, selected[a][0], ledger[a][0]) for a in selected if a in ledger and ledger[a][0] > 5.0 and selected[a][0] is not None]
    ratios = sorted(sel / led_km for _, sel, led_km in both)
    q = lambda p: round(ratios[int(len(ratios) * p)], 3) if ratios else None  # noqa: E731
    return {
        "days": days, "ledger_wagons": len(ledger), "wagons_with_overlap": len(selected), "compared": len(both),
        "ratio_selected_over_ledger": {"p10": q(0.1), "p50": q(0.5), "p90": q(0.9)},
        "selected_km_total": round(sum(sel for _, sel, _ in both), 1), "ledger_km_total": round(sum(led_km for _, _, led_km in both), 1),
        "within_10pct": sum(1 for _, sel, led_km in both if abs(sel - led_km) / led_km <= 0.10),
        "differ_over_25pct": sum(1 for _, sel, led_km in both if abs(sel - led_km) / led_km > 0.25),
        "largest": sorted(({"wagon": str(a), "selected_km": round(sel, 1), "ledger_km": round(led_km, 1)} for a, sel, led_km in both), key=lambda r: -abs(r["selected_km"] - r["ledger_km"]))[:8],
    }
