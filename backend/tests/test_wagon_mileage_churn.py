"""The ledger must not churn: a wobbling diagnostic detail is not a new result."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.wagon_mileage_run import same_outcome

START = datetime(2026, 11, 16, 7, 44, tzinfo=timezone.utc)
END = datetime(2026, 11, 20, 7, 58, tzinfo=timezone.utc)
LOCO = uuid4()


def _row(**kw):
    base = dict(period_from=START, period_to=END, locomotive_asset_id=LOCO, classification="ESTIMATED", distance_km=Decimal("299.32"))
    base.update(kw)
    return SimpleNamespace(**base)


def _proposal(km="299.3200001", classification="ESTIMATED", end=END, loco=LOCO):
    return {"decision": SimpleNamespace(km=Decimal(km), classification=classification), "period_from": START, "period_to": end, "locomotive_asset_id": loco}


def test_the_same_answer_with_different_diagnostics_is_unchanged():
    assert same_outcome(_row(), _proposal()) is True


def test_a_real_change_is_not_hidden():
    assert same_outcome(_row(), _proposal(km="305.10")) is False
    assert same_outcome(_row(), _proposal(classification="CONFIRMED")) is False
    assert same_outcome(_row(), _proposal(loco=uuid4())) is False
    assert same_outcome(_row(), _proposal(end=datetime(2026, 11, 21, tzinfo=timezone.utc))) is False  # an open membership that grew


def test_a_missing_km_counts_as_zero():
    assert same_outcome(_row(distance_km=Decimal("0.00")), {"decision": SimpleNamespace(km=None, classification="ESTIMATED"), "period_from": START, "period_to": END, "locomotive_asset_id": LOCO}) is True
