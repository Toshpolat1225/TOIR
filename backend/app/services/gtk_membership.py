from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable


def snapshot_transition_evidence(
    previous_memberships: Iterable[Any],
    snapshot: dict[str, Any],
    *,
    observed_at: datetime,
) -> dict[str, list[dict[str, Any]]]:
    previous_by_wagon: dict[int, set[int]] = defaultdict(set)
    current_by_wagon: dict[int, set[int]] = defaultdict(set)

    for member in previous_memberships:
        if member.kind == "carriage":
            previous_by_wagon[member.object_gtk_id].add(member.train_gtk_id)
    for train in snapshot["trains"]:
        if train["is_open"]:
            for carriage in train["carriages"]:
                current_by_wagon[carriage["gtk_id"]].add(train["gtk_id"])

    overlap_ids = {
        wagon_id
        for wagon_id in previous_by_wagon.keys() | current_by_wagon.keys()
        if len(previous_by_wagon[wagon_id]) > 1 or len(current_by_wagon[wagon_id]) > 1
    }
    overlaps = [
        {
            "wagon_gtk_id": wagon_id,
            "previous_trains": sorted(previous_by_wagon[wagon_id]),
            "current_trains": sorted(current_by_wagon[wagon_id]),
            "classification": "HELD",
            "reason": "wagon_observed_in_multiple_trains",
        }
        for wagon_id in sorted(overlap_ids)
    ]

    transfers = []
    for wagon_id in sorted(previous_by_wagon.keys() & current_by_wagon.keys()):
        previous_trains = previous_by_wagon[wagon_id]
        current_trains = current_by_wagon[wagon_id]
        if wagon_id in overlap_ids or previous_trains == current_trains:
            continue
        if len(previous_trains) == 1 and len(current_trains) == 1:
            transfers.append(
                {
                    "wagon_gtk_id": wagon_id,
                    "from_train": next(iter(previous_trains)),
                    "to_train": next(iter(current_trains)),
                    "observed_at": observed_at.isoformat(),
                    "effective_at": None,
                    "km": None,
                    "classification": "ESTIMATED",
                }
            )

    return {"wagon_transfers": transfers, "membership_conflicts": overlaps}
