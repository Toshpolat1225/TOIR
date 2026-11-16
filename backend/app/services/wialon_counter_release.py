"""Operator release of Wialon counters blocked by ``same_time_different_odometer``.

Before the benign-advance rule, a second odometer value with the SAME message time
froze the whole counter. A counter is released only when the stored data prove it
healthy. The flagged history is replayed through the same quality gate the live
pipeline uses, so no reading becomes eligible that the gate would not accept:

* inside a same-time group the later value must not be lower and must not grow faster
  than the maximum speed; the first reading represents the group;
* representatives older than the counter state only have to be non-decreasing;
* newer ones are replayed through ``evaluate``; a counter that DECREASED stays blocked
  (manual review). A step that is too large is only held (the live gate accepts it
  once enough time has passed, because the counter state is left untouched).

Dry-run by default; ``apply`` writes and audits (one audit row per released unit).
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.audit_log import AuditLog
from app.models.identity import User
from app.models.mileage import WialonOdometerReading
from app.models.wialon_counters import WialonCounterState
from app.services.wialon_quality import (
    COUNTER_ADVANCED_REASON,
    JUMP_SLACK_KM,
    MAX_SPEED_KMH,
    ROUNDING_KM,
    CounterState,
    Reading,
    Verdict,
    evaluate,
)

BLOCK_REASON = "same_time_different_odometer"
FLAGGED_REASONS = (
    BLOCK_REASON,
    "counter_state_blocked_by_unresolved_conflict",
    COUNTER_ADVANCED_REASON,
)
LOCOMOTIVE_TYPES = ("locomotive", "diesel")
_ACCEPTED_VERDICTS = {Verdict.BASELINE, Verdict.ACCEPTED, Verdict.UNCHANGED}


def _hours(start: datetime, end: datetime) -> Decimal:
    return Decimal(str((end - start).total_seconds())) / Decimal("3600")


def plan_release(
    rows: list[Any], *, last_cnm: Decimal | None, last_cnm_at: datetime | None
) -> dict[str, Any]:
    """Pure decision. ``rows`` are all readings since the first flagged one.

    Returns ``decisions``: one entry per same-time group with the representative,
    the group, whether the representative becomes eligible and the hold reason.
    """
    groups: dict[datetime, list[Any]] = defaultdict(list)
    for row in rows:
        if row.reading_at is None:
            continue
        if row.rejection_reason in FLAGGED_REASONS or row.calculation_eligible:
            groups[row.reading_at].append(row)

    state = (
        CounterState(last_cnm=last_cnm, last_cnm_at=last_cnm_at)
        if last_cnm is not None and last_cnm_at is not None
        else CounterState()
    )
    decisions: list[dict[str, Any]] = []
    previous_old: Decimal | None = None
    for reading_at in sorted(groups):
        group = sorted(groups[reading_at], key=lambda r: (r.received_at, r.id))
        for earlier, later in zip(group, group[1:]):
            if later.odometer_km < earlier.odometer_km:
                return {"releasable": False, "problem": "same_time_value_decreased",
                        "at": reading_at.isoformat()}
        gap = _hours(group[0].received_at, group[-1].received_at)
        growth = group[-1].odometer_km - group[0].odometer_km
        if growth > MAX_SPEED_KMH * gap + JUMP_SLACK_KM:
            return {"releasable": False, "problem": "same_time_growth_too_fast",
                    "at": reading_at.isoformat()}
        representative = group[0]

        if last_cnm_at is not None and reading_at <= last_cnm_at:
            # History older than the counter state: only internal consistency counts.
            if previous_old is not None and representative.odometer_km < previous_old - ROUNDING_KM:
                return {"releasable": False, "problem": "counter_decreased",
                        "at": reading_at.isoformat()}
            previous_old = representative.odometer_km
            decisions.append({"representative": representative, "group": group,
                              "eligible": True, "reason": None})
            continue

        result = evaluate(
            state,
            Reading(representative.odometer_km, None, reading_at),
            now=representative.received_at,
        )
        verdict = result.mileage.verdict
        if verdict in _ACCEPTED_VERDICTS:
            state = result.state
            decisions.append({"representative": representative, "group": group,
                              "eligible": True, "reason": None})
        elif result.mileage.reason and "kamaydi" in result.mileage.reason:
            return {"releasable": False, "problem": "counter_decreased",
                    "at": reading_at.isoformat()}
        else:
            decisions.append({"representative": representative, "group": group,
                              "eligible": False,
                              "reason": result.mileage.reason or verdict.value})
    return {"releasable": True, "decisions": decisions}


async def release_blocked_counters(
    db: AsyncSession,
    *,
    actor: User | None,
    apply: bool,
    inv_numbers: list[str] | None = None,
) -> dict[str, Any]:
    actor_id = actor.id if actor is not None else None
    actor_name = actor.full_name if actor is not None else "CLI"
    query = (
        select(WialonCounterState.asset_id, FixedAsset.inv_number, FixedAsset.wialon_id)
        .join(FixedAsset, FixedAsset.id == WialonCounterState.asset_id)
        .where(
            WialonCounterState.last_reason == BLOCK_REASON,
            FixedAsset.asset_type.in_(LOCOMOTIVE_TYPES),
        )
        .order_by(FixedAsset.inv_number)
    )
    if inv_numbers:
        query = query.where(FixedAsset.inv_number.in_(inv_numbers))
    blocked = (await db.execute(query)).all()
    await db.rollback()

    items: list[dict[str, Any]] = []
    for asset_id, inv_number, wialon_id in blocked:
        item: dict[str, Any] = {"inv_number": inv_number, "status": "manual"}
        if wialon_id:
            await db.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(f"wialon-unit:{wialon_id}", 0)))
            )
        state = (
            await db.execute(
                select(WialonCounterState)
                .where(WialonCounterState.asset_id == asset_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if state is None or state.last_reason != BLOCK_REASON:
            item["status"] = "already_released"
            items.append(item)
            await db.rollback()
            continue
        first_flagged = (
            await db.execute(
                select(func.min(WialonOdometerReading.reading_at)).where(
                    WialonOdometerReading.asset_id == asset_id,
                    WialonOdometerReading.rejection_reason.in_(FLAGGED_REASONS),
                )
            )
        ).scalar_one()
        rows = []
        if first_flagged is not None:
            rows = list(
                (
                    await db.execute(
                        select(WialonOdometerReading)
                        .where(
                            WialonOdometerReading.asset_id == asset_id,
                            WialonOdometerReading.reading_at >= first_flagged,
                        )
                        .order_by(WialonOdometerReading.reading_at, WialonOdometerReading.id)
                        .with_for_update()
                    )
                ).scalars()
            )
        plan = plan_release(rows, last_cnm=state.last_cnm, last_cnm_at=state.last_cnm_at)
        if not plan["releasable"]:
            item.update(problem=plan["problem"], at=plan["at"])
            items.append(item)
            await db.rollback()
            continue

        restore_ids: list[int] = []
        held_ids: list[int] = []
        gate_held: dict[str, list[int]] = defaultdict(list)
        for decision in plan["decisions"]:
            representative = decision["representative"]
            for row in decision["group"]:
                if row.rejection_reason not in FLAGGED_REASONS:
                    continue  # an already-eligible reading stays as it is
                if row is not representative:
                    held_ids.append(row.id)
                elif decision["eligible"]:
                    restore_ids.append(row.id)
                else:
                    gate_held[decision["reason"][:500]].append(row.id)
        item.update(
            status="released" if apply else "would_release",
            readings_restored=len(restore_ids),
            readings_held_benign=len(held_ids),
            readings_held_by_gate=sum(len(ids) for ids in gate_held.values()),
        )
        if apply:
            # Core UPDATEs: thousands of ORM changes would flood the audit log;
            # one explicit audit row below describes the whole release.
            if restore_ids:
                await db.execute(
                    update(WialonOdometerReading)
                    .where(WialonOdometerReading.id.in_(restore_ids))
                    .values(calculation_eligible=True, classification="CONFIRMED",
                            rejection_reason=None)
                )
            if held_ids:
                await db.execute(
                    update(WialonOdometerReading)
                    .where(WialonOdometerReading.id.in_(held_ids))
                    .values(calculation_eligible=False, classification="HELD",
                            rejection_reason=COUNTER_ADVANCED_REASON)
                )
            for reason, ids in gate_held.items():
                await db.execute(
                    update(WialonOdometerReading)
                    .where(WialonOdometerReading.id.in_(ids))
                    .values(calculation_eligible=False, classification="HELD",
                            rejection_reason=reason)
                )
            await db.execute(
                update(WialonCounterState)
                .where(WialonCounterState.asset_id == asset_id)
                .values(last_reason=None, last_status="unchanged",
                        updated_at=datetime.now(timezone.utc))
            )
            db.add(
                AuditLog(
                    action="other",
                    actor_type="user" if actor_id else "system",
                    actor_user_id=actor_id,
                    actor_name=actor_name,
                    module="wialon",
                    route="/cli/wialon-counter-release",
                    object_type="fixed_asset",
                    object_id=str(asset_id),
                    object_label=inv_number,
                    details={
                        "event": "counter_release",
                        "readings_restored": len(restore_ids),
                        "readings_held_benign": len(held_ids),
                        "readings_held_by_gate": item["readings_held_by_gate"],
                    },
                )
            )
            await db.commit()
        else:
            await db.rollback()
        items.append(item)

    summary: dict[str, int] = defaultdict(int)
    for item in items:
        summary[item["status"]] += 1
    return {"applied": apply, "summary": dict(summary), "items": items}
