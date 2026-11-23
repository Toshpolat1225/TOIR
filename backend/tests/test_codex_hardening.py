"""CODEX hardening: API docs are off by default (AUTH-06); sensitive request bodies refuse unknown fields (INJ-04)."""
from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.auth import LoginRequest
from app.schemas.maintenance import (
    MaintenanceBaselineUpsert,
    MaintenanceDisruptionCreate,
    MaintenancePlanBlock,
    MaintenancePlanFromForecast,
    MaintenancePlanUpdate,
    MaintenancePlanWaive,
    MaintenanceSettingsUpdate,
)
from app.schemas.users import AdUserCreate, UserUpdate


def test_api_docs_are_off_unless_explicitly_enabled():
    assert Settings.model_fields["api_docs_enabled"].default is False


@pytest.mark.parametrize(
    "model, payload",
    [
        (UserUpdate, {"full_name": "A", "role": "admin"}),
        (AdUserCreate, {"ad_username": "a.b", "full_name": "A", "role": "operator"}),
        (LoginRequest, {"email": "a.b", "password": "x"}),
        (MaintenanceSettingsUpdate, {"daily_average_km": "50"}),
        (MaintenancePlanWaive, {"reason": "x"}),
        (MaintenancePlanBlock, {"reason_code": "parts"}),
        (MaintenancePlanUpdate, {"status": "scheduled"}),
        (MaintenancePlanFromForecast, {"asset_id": str(uuid4()), "interval_id": str(uuid4()), "scheduled_date": date.today().isoformat()}),
        (MaintenanceBaselineUpsert, {"asset_id": str(uuid4()), "interval_id": str(uuid4()), "done_at": date.today().isoformat(), "km": "1"}),
        (MaintenanceDisruptionCreate, {"kind": "parts", "scope": "all"}),
    ],
)
def test_an_unknown_field_is_refused_but_the_known_ones_still_work(model, payload):
    try:
        model(**payload)
    except ValidationError as exc:  # a legitimately invalid payload is fine for this test only if it is not about the extra field
        assert all(e["type"] != "extra_forbidden" for e in exc.errors())
    with pytest.raises(ValidationError) as refused:
        model(**payload, is_superuser=True)
    assert any(e["type"] == "extra_forbidden" for e in refused.value.errors())
