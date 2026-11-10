from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.gtk_membership import snapshot_transition_evidence


def _snapshot(train_carriages):
    return {
        "trains": [
            {
                "gtk_id": train_id,
                "is_open": True,
                "carriages": [{"gtk_id": wagon_id} for wagon_id in wagon_ids],
            }
            for train_id, wagon_ids in train_carriages
        ]
    }


def test_snapshot_transfer_is_estimated_without_fabricated_distance_or_time():
    evidence = snapshot_transition_evidence(
        [SimpleNamespace(kind="carriage", object_gtk_id=7, train_gtk_id=10)],
        _snapshot([(20, [7])]),
        observed_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )

    transfer = evidence["wagon_transfers"][0]
    assert transfer["classification"] == "ESTIMATED"
    assert transfer["effective_at"] is None
    assert transfer["km"] is None
    assert transfer["from_train"] == 10
    assert transfer["to_train"] == 20


def test_cross_train_snapshot_overlap_is_held():
    evidence = snapshot_transition_evidence(
        [],
        _snapshot([(10, [7]), (20, [7])]),
        observed_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )

    assert evidence["wagon_transfers"] == []
    assert evidence["membership_conflicts"] == [
        {
            "wagon_gtk_id": 7,
            "previous_trains": [],
            "current_trains": [10, 20],
            "classification": "HELD",
            "reason": "wagon_observed_in_multiple_trains",
        }
    ]
