"""Unit tests (no database) for the "fix everything" batch of 2026-11-16."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.maintenance import _require_planner
from app.schemas.maintenance import MaintenanceSettingsUpdate
from app.schemas.references import DepartmentCreate, DepartmentUpdate
from app.schemas.users import UserRead
from app.services.audit_log import _OPERATIONAL_TABLES, _telemetry_predicate
from app.services.maintenance import _unforecasted_units
from app.services.maintenance_engine import daily_deltas

D = Decimal


# ── B2: the default pace has to be realistic, and `management` cannot change it ──────────────────────────────
@pytest.mark.parametrize("bad", ["0", "1", "4.99", "1000.01", "-5"])
def test_unrealistic_default_pace_is_refused(bad):
    with pytest.raises(ValidationError):
        MaintenanceSettingsUpdate(daily_average_km=D(bad))


@pytest.mark.parametrize("good", ["5", "60", "250.5", "1000"])
def test_realistic_default_pace_is_accepted(good):
    assert MaintenanceSettingsUpdate(daily_average_km=D(good)).daily_average_km == D(good)


@pytest.mark.parametrize("role,allowed", [("admin", True), ("operator", True), ("management", False), ("master", False)])
def test_only_admin_and_operator_plan(role, allowed):
    user = SimpleNamespace(role=role)
    if allowed:
        _require_planner(user)
    else:
        with pytest.raises(Exception) as caught:
            _require_planner(user)
        assert getattr(caught.value, "status_code", None) == 403


# ── B3: a department colour must be a colour ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["red", "#12345", "#1234567", "123456", "#gggggg", "<script>", "javascript:alert(1)"])
def test_department_colour_must_be_hex(bad):
    with pytest.raises(ValidationError):
        DepartmentCreate(name="Участок", color=bad)
    with pytest.raises(ValidationError):
        DepartmentUpdate(color=bad)


def test_department_colour_hex_is_accepted_and_default_is_valid():
    assert DepartmentCreate(name="Участок", color="#0EA5e9").color == "#0EA5e9"
    assert DepartmentCreate(name="Участок").color == "#3b82f6"
    assert DepartmentUpdate(name="Другой").name == "Другой"  # a patch that does not touch the colour is fine


# ── B5: the directory GUID stays on the server ────────────────────────────────────────────────────────────────
def _user_read(guid):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return UserRead(
        id=uuid4(), email="a@example.test", full_name="A", role="operator", section_id=None, is_active=True,
        last_login_at=None, created_at=now, updated_at=now, ad_object_guid=guid,
    )


def test_user_read_hides_the_ad_guid_and_reports_confirmation():
    unconfirmed = _user_read(None).model_dump(mode="json")
    confirmed = _user_read(uuid4()).model_dump(mode="json")
    assert "ad_object_guid" not in unconfirmed and "ad_object_guid" not in confirmed
    assert unconfirmed["ad_confirmed"] is False
    assert confirmed["ad_confirmed"] is True


# ── B11: km that pile up while our collector was down are spread, not counted as one huge day ───────────────
def test_catch_up_after_unobserved_days_is_spread_over_them():
    d0 = date(2026, 11, 10)
    # readings only on day 0 (100) and day 4 (700): days 1-3 had no collector
    readings = [(d0, D(100)), (d0 + timedelta(days=4), D(700))]
    plain = daily_deltas(readings, first_day=d0, last_day=d0 + timedelta(days=4))
    assert plain == [D(0), D(0), D(0), D(600)]  # what used to feed the pace: one 600 km "day"
    down = {d0 + timedelta(days=i) for i in (1, 2, 3)}
    spread = daily_deltas(readings, first_day=d0, last_day=d0 + timedelta(days=4), unobserved_days=down)
    assert spread == [D(150)] * 4
    assert sum(spread) == sum(plain)  # nothing is invented or lost


def test_a_genuinely_idle_stretch_with_a_working_collector_is_still_idle():
    d0 = date(2026, 11, 10)
    readings = [(d0, D(100)), (d0 + timedelta(days=4), D(700))]
    assert daily_deltas(readings, first_day=d0, last_day=d0 + timedelta(days=4), unobserved_days=set()) == [D(0), D(0), D(0), D(600)]


def test_an_unobserved_tail_is_unknown_not_idle():
    d0 = date(2026, 11, 10)
    readings = [(d0, D(100)), (d0 + timedelta(days=1), D(160))]
    tail = {d0 + timedelta(days=2), d0 + timedelta(days=3)}
    # the last two days have no later reading: they are dropped instead of being counted as 0
    assert daily_deltas(readings, first_day=d0, last_day=d0 + timedelta(days=3), unobserved_days=tail) == [D(60)]


# ── B7: the telemetry purge only names feed tables and sync-only asset updates ────────────────────────────────
def test_telemetry_predicate_is_limited_to_system_rows_and_known_feeds():
    predicate = _telemetry_predicate()
    assert predicate.startswith("actor_type = 'system' AND (")
    for table in ("wialon_raw_receipts", "gtk_sync_runs", "mileage_history"):
        assert f"'{table}'" in predicate
    # business tables are never named as whole-table matches
    for table in ("users", "work_orders", "maintenance_plan", "maintenance_intervals", "wagon_mileage_opening_balances"):
        assert f"'{table}'" not in predicate
    assert "audit_logs" not in _OPERATIONAL_TABLES - {"audit_logs"}
    # a fixed-asset row counts only when every changed column is a live-sync column
    assert "NOT EXISTS" in predicate and "'wialon_last_sync'" in predicate and "'name'" not in predicate


# ── B8: units that cannot be placed on the calendar are listed with a reason ──────────────────────────────────
class _Ctx:
    def __init__(self, trusted=()):
        self.trusted_wagons = set(trusted)

    def behavior(self, asset):
        return asset.behavior


def _asset(asset_type="locomotive", mileage=100, behavior="active"):
    return SimpleNamespace(
        id=uuid4(), name="N", inv_number=str(uuid4())[:6], asset_type=asset_type, mileage=mileage,
        behavior=behavior, decommissioned_at=None,
    )


def _interval(asset_type="locomotive"):
    return SimpleNamespace(id=uuid4(), is_active=True, asset_types=[asset_type])


def _ob(asset, *, planned=None, state="forecast", plan=None):
    return SimpleNamespace(asset=asset, plan=plan, markers=SimpleNamespace(state=state), planned_date=planned)


def test_unforecasted_units_explain_every_gap():
    today = date(2026, 11, 16)
    moving, still, no_odo, wagon_no_open, wagon_ok, gone = (
        _asset(), _asset(), _asset(mileage=None), _asset("wagon", 50), _asset("wagon", 50), _asset(behavior="out_of_service"),
    )
    loco_i, wagon_i = _interval(), _interval("wagon")
    by_type = {"locomotive": [loco_i], "wagon": [wagon_i]}
    by_key = {
        (moving.id, loco_i.id): _ob(moving, planned=today + timedelta(days=9)),
        (still.id, loco_i.id): _ob(still),  # exists but cannot be dated: the unit does not move
        (wagon_ok.id, wagon_i.id): _ob(wagon_ok, planned=today + timedelta(days=3)),
    }
    result = _unforecasted_units(
        [moving, still, no_odo, wagon_no_open, wagon_ok, gone], by_type, by_key, _Ctx(trusted=[wagon_ok.id]), today
    )
    reasons = {item.asset_id: item.reason for item in result}
    assert reasons == {still.id: "no_movement", no_odo.id: "no_mileage", wagon_no_open.id: "no_mileage_baseline"}
    assert moving.id not in reasons and wagon_ok.id not in reasons and gone.id not in reasons


def test_an_overdue_obligation_is_not_called_unforecasted():
    today = date(2026, 11, 16)
    a, i = _asset(), _interval()
    result = _unforecasted_units([a], {"locomotive": [i]}, {(a.id, i.id): _ob(a, state="over_limit")}, _Ctx(), today)
    assert result == []
