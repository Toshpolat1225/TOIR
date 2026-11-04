"""Pure mileage attribution rules for GTK train snapshots."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Literal
from uuid import UUID

from app.services.wialon_quality import JUMP_SLACK_KM, MAX_SPEED_KMH

_ZERO = Decimal("0")
_CENT = Decimal("0.01")


@dataclass(frozen=True)
class TrainMembership:
    train_gtk_id: int
    kind: Literal["locomotive", "carriage"]
    object_gtk_id: int
    is_main: bool = False


@dataclass(frozen=True)
class LocomotiveMileage:
    asset_id: UUID
    mileage: Decimal


@dataclass(frozen=True)
class WagonAsset:
    asset_id: UUID
    is_active: bool


@dataclass(frozen=True)
class MileageCheckpoint:
    asset_id: UUID
    mileage: Decimal
    at: datetime


@dataclass(frozen=True)
class WagonMileageAttribution:
    wagon_asset_id: UUID
    loco_asset_id: UUID
    train_gtk_id: int
    period_from: datetime
    period_to: datetime
    km: Decimal


@dataclass(frozen=True)
class AttributionResult:
    entries: tuple[WagonMileageAttribution, ...]
    checkpoints: dict[int, MileageCheckpoint]
    unattributed_km: Decimal
    loco_unlinked: int
    loco_rejected: int

    @property
    def attributed_km(self) -> Decimal:
        return sum((entry.km for entry in self.entries), _ZERO).quantize(_CENT)

    @property
    def wagons_updated(self) -> int:
        return len({entry.wagon_asset_id for entry in self.entries})


def _hours(start: datetime, end: datetime) -> Decimal:
    return Decimal(str((end - start).total_seconds())) / Decimal("3600")


def compute_attribution(
    previous_memberships: Iterable[TrainMembership],
    current_memberships: Iterable[TrainMembership],
    locomotive_assets: dict[int, LocomotiveMileage],
    wagon_assets: dict[int, WagonAsset],
    checkpoints: dict[int, MileageCheckpoint],
    *,
    observed_at: datetime,
) -> AttributionResult:
    previous = tuple(previous_memberships)
    current = tuple(current_memberships)
    previous_keys = {
        (member.train_gtk_id, member.kind, member.object_gtk_id)
        for member in previous
    }

    previous_carriage_trains: dict[int, set[int]] = defaultdict(set)
    current_carriage_trains: dict[int, set[int]] = defaultdict(set)
    current_trains: dict[int, list[TrainMembership]] = defaultdict(list)
    for member in previous:
        if member.kind == "carriage":
            previous_carriage_trains[member.object_gtk_id].add(member.train_gtk_id)
    for member in current:
        current_trains[member.train_gtk_id].append(member)
        if member.kind == "carriage":
            current_carriage_trains[member.object_gtk_id].add(member.train_gtk_id)

    duplicate_carriages = {
        carriage_id
        for carriage_id in previous_carriage_trains.keys()
        | current_carriage_trains.keys()
        if len(previous_carriage_trains[carriage_id]) > 1
        or len(current_carriage_trains[carriage_id]) > 1
    }
    main_trains: dict[int, set[int]] = defaultdict(set)
    for train_id, members in current_trains.items():
        for member in members:
            if member.kind == "locomotive" and member.is_main:
                main_trains[member.object_gtk_id].add(train_id)

    updated_checkpoints: dict[int, MileageCheckpoint] = {}
    for gtk_id, reading in locomotive_assets.items():
        old = checkpoints.get(gtk_id)
        if old is None or old.asset_id != reading.asset_id:
            updated_checkpoints[gtk_id] = MileageCheckpoint(
                reading.asset_id, reading.mileage, observed_at
            )
        elif gtk_id not in main_trains:
            updated_checkpoints[gtk_id] = MileageCheckpoint(
                reading.asset_id, reading.mileage, observed_at
            )

    entries: list[WagonMileageAttribution] = []
    unattributed = _ZERO
    loco_unlinked = 0
    loco_rejected = 0
    rejected_locomotives: set[int] = set()

    for train_id in sorted(current_trains):
        members = current_trains[train_id]
        main_ids = {
            member.object_gtk_id
            for member in members
            if member.kind == "locomotive" and member.is_main
        }
        if not main_ids:
            continue
        if len(main_ids) != 1:
            loco_rejected += len(main_ids)
            rejected_locomotives.update(main_ids)
            continue

        loco_gtk_id = next(iter(main_ids))
        if len(main_trains[loco_gtk_id]) != 1:
            if loco_gtk_id not in rejected_locomotives:
                loco_rejected += 1
                rejected_locomotives.add(loco_gtk_id)
            continue

        reading = locomotive_assets.get(loco_gtk_id)
        if reading is None:
            loco_unlinked += 1
            continue
        checkpoint = checkpoints.get(loco_gtk_id)
        if checkpoint is None or checkpoint.asset_id != reading.asset_id:
            updated_checkpoints[loco_gtk_id] = MileageCheckpoint(
                reading.asset_id, reading.mileage, observed_at
            )
            continue

        delta = reading.mileage - checkpoint.mileage
        if delta <= _ZERO:
            updated_checkpoints[loco_gtk_id] = MileageCheckpoint(
                reading.asset_id, reading.mileage, observed_at
            )
            continue

        elapsed = _hours(checkpoint.at, observed_at)
        maximum = MAX_SPEED_KMH * max(elapsed, _ZERO) + JUMP_SLACK_KM
        if delta > maximum:
            if loco_gtk_id not in rejected_locomotives:
                loco_rejected += 1
                rejected_locomotives.add(loco_gtk_id)
            continue

        eligible_wagons = {
            member.object_gtk_id
            for member in members
            if member.kind == "carriage"
            and (
                train_id,
                "carriage",
                member.object_gtk_id,
            )
            in previous_keys
            and member.object_gtk_id not in duplicate_carriages
            and member.object_gtk_id in wagon_assets
            and wagon_assets[member.object_gtk_id].is_active
        }
        if not eligible_wagons:
            unattributed += delta
        else:
            for wagon_gtk_id in sorted(eligible_wagons):
                entries.append(
                    WagonMileageAttribution(
                        wagon_asset_id=wagon_assets[wagon_gtk_id].asset_id,
                        loco_asset_id=reading.asset_id,
                        train_gtk_id=train_id,
                        period_from=checkpoint.at,
                        period_to=observed_at,
                        km=delta.quantize(_CENT),
                    )
                )
        updated_checkpoints[loco_gtk_id] = MileageCheckpoint(
            reading.asset_id, reading.mileage, observed_at
        )

    return AttributionResult(
        entries=tuple(entries),
        checkpoints=updated_checkpoints,
        unattributed_km=unattributed.quantize(_CENT),
        loco_unlinked=loco_unlinked,
        loco_rejected=loco_rejected,
    )
