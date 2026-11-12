import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrain, GtkTrainMember
from app.models.mileage import (
    MileageCalculationInput,
    MileageCalculationRun,
    WagonIdlePeriod,
    WagonMileageLedger,
    WagonMileageOpeningBalance,
    WialonOdometerReading,
)
from app.services import maintenance as maintenance_service
from app.services.wagon_mileage import (
    OdometerPoint,
    SegmentDecision,
    decide_wagon_idle,
    sum_wialon_sample_deltas,
)
from app.core.config import settings
from app.services.wagon_mileage_engine import (
    OdometerInterval,
    select_main_locomotive,
)

ALGORITHM_VERSION = "wagon-mileage-p0.3"


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ledger_idempotency_key(
    *,
    wagon_asset_id: str,
    aggregate_id: str,
    period_from: str,
    period_to: str,
    algorithm_version: str,
    input_hash: str,
) -> str:
    return _digest(
        [
            wagon_asset_id,
            aggregate_id,
            period_from,
            period_to,
            algorithm_version,
            input_hash,
        ]
    )


def calculate_wagon_projection(
    asset_type: str,
    opening_balance_km: Decimal,
    confirmed_km: Decimal,
    estimated_km: Decimal,
) -> Decimal:
    if asset_type != "wagon":
        raise ValueError("Mileage projection is only for wagons")
    return opening_balance_km + confirmed_km + estimated_km


def _decision_payload(decision: SegmentDecision) -> dict[str, Any]:
    return {
        "classification": decision.classification,
        "calculation_eligible": decision.calculation_eligible,
        "km": str(decision.km) if decision.km is not None else None,
        "locomotive_asset_id": (
            str(decision.locomotive_asset_id)
            if decision.locomotive_asset_id is not None
            else None
        ),
        "source_reading_ids": list(decision.source_reading_ids),
        "reason": decision.reason,
    }


def _held(reason: str, locomotive_id: UUID | None = None) -> SegmentDecision:
    return SegmentDecision("HELD", False, None, locomotive_id, (), reason)


async def _linked_members(db: AsyncSession, kind: str):
    result = await db.execute(
        select(
            GtkTrainMember,
            GtkTrain.begin_time,
            GtkTrain.end_time,
            FixedAsset.id,
        )
        .join(GtkTrain, GtkTrain.gtk_id == GtkTrainMember.train_gtk_id)
        .join(
            AssetSourceLink,
            and_(
                AssetSourceLink.source == "gtk",
                AssetSourceLink.external_id
                == cast(GtkTrainMember.object_gtk_id, String),
                AssetSourceLink.status == "active",
            ),
        )
        .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
        .where(
            GtkTrainMember.kind == kind,
            FixedAsset.asset_type == ("wagon" if kind == "carriage" else "locomotive"),
        )
        .order_by(
            GtkTrainMember.train_gtk_id,
            GtkTrainMember.object_gtk_id,
            GtkTrainMember.observed_from,
        )
    )
    return list(result.all())


def _bounds(member: GtkTrainMember, end: datetime | None) -> tuple[datetime, datetime] | None:
    start = member.observed_from
    final = member.observed_to or end
    if final is None or final <= start:
        return None
    return start, final


async def _load_inputs(db: AsyncSession):
    wagon_rows = await _linked_members(db, "carriage")
    locomotive_rows = await _linked_members(db, "locomotive")
    locomotive_assets = {row[3] for row in locomotive_rows}
    readings_result = await db.execute(
        select(WialonOdometerReading)
        .where(
            WialonOdometerReading.asset_id.in_(locomotive_assets),
            WialonOdometerReading.observed_at.is_not(None),
        )
        .order_by(
            WialonOdometerReading.asset_id,
            WialonOdometerReading.observed_at,
            WialonOdometerReading.id,
        )
    ) if locomotive_assets else None
    readings = list(readings_result.scalars().all()) if readings_result else []
    by_locomotive: dict[UUID, list[OdometerPoint]] = defaultdict(list)
    reading_rows: dict[int, WialonOdometerReading] = {}
    latest_reading_at: dict[UUID, datetime] = {}
    for row in readings:
        if row.asset_id is None or row.observed_at is None:
            continue
        point = OdometerPoint(
            reading_id=row.id,
            locomotive_asset_id=row.asset_id,
            odometer_km=row.odometer_km,
            reading_at=row.observed_at,
            accepted=row.accepted,
            calculation_eligible=row.calculation_eligible,
            received_at=row.received_at,
        )
        by_locomotive[row.asset_id].append(point)
        reading_rows[row.id] = row
        latest_reading_at[row.asset_id] = row.observed_at

    wagon_assets = {row[3] for row in wagon_rows}
    openings_result = await db.execute(
        select(WagonMileageOpeningBalance).where(
            WagonMileageOpeningBalance.asset_id.in_(wagon_assets),
            WagonMileageOpeningBalance.status == "approved",
        )
    ) if wagon_assets else None
    openings = {
        row.asset_id: row
        for row in openings_result.scalars().all()
    } if openings_result else {}
    return (
        wagon_rows,
        locomotive_rows,
        by_locomotive,
        reading_rows,
        latest_reading_at,
        openings,
    )


def _candidate_decisions(
    *,
    start: datetime,
    end: datetime,
    train_id: int,
    locomotive_rows: list[tuple[Any, ...]],
    by_locomotive: dict[UUID, list[OdometerPoint]],
) -> tuple[SegmentDecision, str | None]:
    candidates: list[OdometerInterval] = []
    decisions: dict[UUID, SegmentDecision] = {}
    for member, _train_start, _train_end, asset_id in locomotive_rows:
        member_end = member.observed_to or end
        if member.observed_from > start or member_end < end:
            return _held("locomotive_handoff_time_unknown"), None
        decision = sum_wialon_sample_deltas(
            by_locomotive.get(asset_id, ()),
            period_from=start,
            period_to=end,
        )
        if decision.classification == "HELD" or decision.km is None:
            continue
        points = by_locomotive.get(asset_id, ())
        if not points:
            continue
        readings_in_window = [
            point for point in points
            if decision.source_reading_ids and point.reading_id in decision.source_reading_ids
        ]
        if not readings_in_window:
            continue
        decisions[asset_id] = decision
        candidates.append(
            OdometerInterval(
                locomotive_asset_id=asset_id,
                start_km=Decimal("0"),
                end_km=decision.km,
                start_at=start,
                end_at=end,
                received_at=max(
                    point.received_at or point.reading_at
                    for point in readings_in_window
                ),
                source_id=str(asset_id),
                is_main=member.is_main,
            )
        )

    selection = select_main_locomotive(candidates)
    if selection.selected is None:
        if not candidates:
            return _held("no_eligible_locomotive_odometer"), None
        return _held(selection.reason), selection.reason
    decision = decisions[selection.selected.locomotive_asset_id]
    return decision, selection.reason


async def _proposals(inputs):
    (
        wagon_rows,
        locomotive_rows,
        by_locomotive,
        reading_rows,
        latest_reading_at,
        openings,
    ) = inputs
    locomotives_by_train: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in locomotive_rows:
        locomotives_by_train[row[0].train_gtk_id].append(row)

    proposals = []
    pending_assets: set[UUID] = set()
    for member, train_start, train_end, wagon_asset_id in wagon_rows:
        train_id = member.train_gtk_id
        train_locomotives = locomotives_by_train.get(train_id, [])
        train_latest = max(
            (
                latest_reading_at[row[3]]
                for row in train_locomotives
                if row[3] in latest_reading_at
            ),
            default=None,
        )
        bounds = _bounds(member, train_end or train_latest)
        if bounds is None:
            pending_assets.add(wagon_asset_id)
            continue
        start, end = bounds
        if not train_locomotives:
            decision = _held("no_linked_locomotive")
            selection_reason = None
        else:
            decision, selection_reason = _candidate_decisions(
                start=start,
                end=end,
                train_id=train_id,
                locomotive_rows=train_locomotives,
                by_locomotive=by_locomotive,
            )
        opening = openings.get(wagon_asset_id)
        if opening is None:
            pending_assets.add(wagon_asset_id)
            decision = _held("approved_opening_balance_missing")
        elif start < opening.effective_at:
            decision = _held("period_precedes_approved_opening_balance")

        boundaries_exact = (
            member.gtk_begin_time is not None
            and member.gtk_begin_time == start
            and train_end is not None
            and member.observed_to == train_end
            and end == train_end
        )
        if (
            decision.classification == "CONFIRMED"
            and decision.km is not None
            and decision.km > 0
            and not boundaries_exact
        ):
            decision = SegmentDecision(
                "ESTIMATED",
                True,
                decision.km,
                decision.locomotive_asset_id,
                decision.source_reading_ids,
                "gtk_snapshot_membership_boundary_estimated",
            )

        details = _decision_payload(decision) | {
            "selection_reason": selection_reason,
            "gtk_membership_id": member.id,
            "gtk_boundary_exact": boundaries_exact,
            "opening_balance_id": str(opening.id) if opening else None,
        }
        source_payload = {
            "wagon_asset_id": str(wagon_asset_id),
            "train_gtk_id": train_id,
            "period_from": start.isoformat(),
            "period_to": end.isoformat(),
            "algorithm_version": ALGORITHM_VERSION,
            "gtk_membership_id": member.id,
            "opening_balance_id": str(opening.id) if opening else None,
            "readings": [
                {
                    "id": reading_id,
                    "km": str(reading_rows[reading_id].odometer_km),
                    "observed_at": reading_rows[reading_id].observed_at.isoformat(),
                    "eligible": reading_rows[reading_id].calculation_eligible,
                }
                for reading_id in decision.source_reading_ids
                if reading_id in reading_rows
            ],
            "decision": details,
        }
        input_hash = _digest(source_payload)
        idempotency_key = ledger_idempotency_key(
            wagon_asset_id=str(wagon_asset_id),
            aggregate_id=str(decision.locomotive_asset_id or train_id),
            period_from=start.isoformat(),
            period_to=end.isoformat(),
            algorithm_version=ALGORITHM_VERSION,
            input_hash=input_hash,
        )
        proposals.append(
            {
                "wagon_asset_id": wagon_asset_id,
                "locomotive_asset_id": decision.locomotive_asset_id,
                "train_gtk_id": train_id,
                "period_from": start,
                "period_to": end,
                "decision": decision,
                "details": details,
                "input_hash": input_hash,
                "idempotency_key": idempotency_key,
                "opening_balance_id": opening.id if opening else None,
            }
        )
    return proposals, pending_assets, reading_rows


def _report(proposals, pending_assets: set[UUID]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    kms: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    conflicts = 0
    for proposal in proposals:
        decision = proposal["decision"]
        counts[decision.classification] += 1
        value = decision.km or Decimal("0")
        kms[decision.classification] += value
        if decision.classification == "HELD":
            reasons[decision.reason] += 1
            conflicts += int("conflict" in decision.reason)
    return {
        "status_counts": {key: counts[key] for key in ("CONFIRMED", "ESTIMATED", "HELD")},
        "status_km": {
            key: str(Decimal(kms[key]).quantize(Decimal("0.01")))
            for key in ("CONFIRMED", "ESTIMATED", "HELD")
        },
        "held_reasons": dict(sorted(reasons.items())),
        "conflicts": conflicts,
        "unapproved_opening_balances": len(pending_assets),
        "proposed_segments": len(proposals),
    }


async def run_wagon_mileage(
    db: AsyncSession, *, dry_run: bool = False
) -> dict[str, Any]:
    inputs = await _load_inputs(db)
    proposals, pending_assets, reading_rows = await _proposals(inputs)
    report = _report(proposals, pending_assets)
    report["dry_run"] = dry_run
    if dry_run:
        await db.rollback()
        return report

    run = MileageCalculationRun(
        algorithm_version=ALGORITHM_VERSION,
        status="running",
        input_watermark={
            "proposal_count": len(proposals),
            "reading_ids": sorted(reading_rows),
        },
    )
    db.add(run)
    await db.commit()
    by_train: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for proposal in proposals:
        by_train[proposal["train_gtk_id"]].append(proposal)
    changed_assets: set[UUID] = set()
    seen_inputs: set[tuple[str, Any]] = set()
    idle_periods = 0
    for train_id, train_proposals in sorted(by_train.items()):
        async with db.begin():
            lock_key = f"wagon-mileage-train:{train_id}"
            await db.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0)))
            )
            for proposal in train_proposals:
                decision = proposal["decision"]
                existing_result = await db.execute(
                    select(WagonMileageLedger)
                    .where(
                        WagonMileageLedger.wagon_asset_id == proposal["wagon_asset_id"],
                        WagonMileageLedger.train_gtk_id == train_id,
                        WagonMileageLedger.period_from == proposal["period_from"],
                        WagonMileageLedger.period_to == proposal["period_to"],
                        WagonMileageLedger.status == "active",
                    )
                    .with_for_update()
                )
                existing = list(existing_result.scalars().all())
                if any(
                    row.idempotency_key == proposal["idempotency_key"]
                    for row in existing
                ):
                    continue
                previous = existing[0] if existing else None
                for row in existing:
                    row.status = "superseded"
                classification = decision.classification
                ledger = WagonMileageLedger(
                    run_id=run.id,
                    wagon_asset_id=proposal["wagon_asset_id"],
                    locomotive_asset_id=proposal["locomotive_asset_id"],
                    train_gtk_id=train_id,
                    period_from=proposal["period_from"],
                    period_to=proposal["period_to"],
                    distance_km=decision.km or Decimal("0"),
                    estimated=classification == "ESTIMATED",
                    classification=classification,
                    calculation_eligible=classification in {"CONFIRMED", "ESTIMATED"},
                    status="active",
                    idempotency_key=proposal["idempotency_key"],
                    algorithm_version=ALGORITHM_VERSION,
                    input_hash=proposal["input_hash"],
                    supersedes_id=previous.id if previous else None,
                    calculation_details=proposal["details"],
                )
                db.add(ledger)
                await db.flush()
                db.add(
                    MileageCalculationInput(
                        run_id=run.id,
                        gtk_membership_id=proposal["details"]["gtk_membership_id"],
                    )
                )
                seen_inputs.add(
                    ("gtk_membership_id", proposal["details"]["gtk_membership_id"])
                )
                if proposal["opening_balance_id"] is not None:
                    opening_key = (
                        "opening_balance_id",
                        proposal["opening_balance_id"],
                    )
                    if opening_key not in seen_inputs:
                        db.add(
                            MileageCalculationInput(
                                run_id=run.id,
                                opening_balance_id=proposal["opening_balance_id"],
                            )
                        )
                        seen_inputs.add(opening_key)
                for reading_id in decision.source_reading_ids:
                    reading_key = ("wialon_reading_id", reading_id)
                    if reading_key not in seen_inputs:
                        db.add(
                            MileageCalculationInput(
                                run_id=run.id,
                                wialon_reading_id=reading_id,
                            )
                        )
                        seen_inputs.add(reading_key)
                duration_seconds = int(
                    (
                        proposal["period_to"] - proposal["period_from"]
                    ).total_seconds()
                )
                if (
                    decision.km == 0
                    and duration_seconds >= settings.wagon_mileage_idle_min_minutes * 60
                ):
                    idle_status, idle_reason = decide_wagon_idle(
                        gtk_wagon_stationary=None,
                        wialon_locomotive_stopped=None,
                        odometer_delta_km=decision.km,
                        duration_seconds=duration_seconds,
                    )
                    idle_key = _digest(
                        [
                            proposal["wagon_asset_id"],
                            train_id,
                            proposal["period_from"],
                            proposal["period_to"],
                            ALGORITHM_VERSION,
                        ]
                    )
                    idle_exists = await db.scalar(
                        select(WagonIdlePeriod.id).where(
                            WagonIdlePeriod.idempotency_key == idle_key
                        )
                    )
                    if idle_exists is None:
                        db.add(
                            WagonIdlePeriod(
                                wagon_asset_id=proposal["wagon_asset_id"],
                                aggregate_gtk_id=train_id,
                                period_from=proposal["period_from"],
                                period_to=proposal["period_to"],
                                status=(
                                    "confirmed"
                                    if idle_status == "CONFIRMED"
                                    else "unknown_activity"
                                ),
                                distance_km=Decimal("0"),
                                idempotency_key=idle_key,
                                evidence={
                                    "reason": idle_reason,
                                    "gtk_membership_id": proposal["details"][
                                        "gtk_membership_id"
                                    ],
                                },
                            )
                        )
                        idle_periods += 1
                changed_assets.add(proposal["wagon_asset_id"])

    for asset_id in sorted(changed_assets, key=str):
        async with db.begin():
            lock_key = f"wagon-mileage-asset:{asset_id}"
            await db.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0)))
            )
            asset = await db.scalar(
                select(FixedAsset).where(FixedAsset.id == asset_id).with_for_update()
            )
            if asset is None:
                raise RuntimeError(f"Wagon projection asset {asset_id} no longer exists")
            if asset.asset_type != "wagon":
                raise RuntimeError("Wagon mileage projection rejected a non-wagon asset")
            opening = await db.scalar(
                select(WagonMileageOpeningBalance).where(
                    WagonMileageOpeningBalance.asset_id == asset.id,
                    WagonMileageOpeningBalance.status == "approved",
                )
            )
            if opening is None:
                continue
            total = await db.scalar(
                select(func.coalesce(func.sum(WagonMileageLedger.distance_km), 0)).where(
                    WagonMileageLedger.wagon_asset_id == asset.id,
                    WagonMileageLedger.status == "active",
                    WagonMileageLedger.calculation_eligible.is_(True),
                    WagonMileageLedger.classification.in_(("CONFIRMED", "ESTIMATED")),
                    WagonMileageLedger.period_from >= opening.effective_at,
                )
            )
            projection = calculate_wagon_projection(
                asset.asset_type,
                opening.mileage_km,
                Decimal("0"),
                Decimal(str(total or 0)),
            )
            if projection != asset.mileage:
                asset.mileage = projection
                asset.updated_at = datetime.now(timezone.utc)
                await maintenance_service.reconcile_asset_plans(
                    db, asset, projection
                )

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.summary = report
    await db.commit()
    report["run_id"] = str(run.id)
    report["changed_assets"] = len(changed_assets)
    report["idle_periods_added"] = idle_periods
    return report
