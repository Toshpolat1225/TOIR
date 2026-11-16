"""The audit log must not copy integration telemetry (it was 96 % of 950k rows) and the export must be bounded."""
from app.main import app
from app.routers import audit_logs
from app.services.audit_log import _OPERATIONAL_TABLES, _SYNC_ONLY_COLUMNS
from sqlalchemy.exc import DBAPIError

from app.models import Base  # noqa: F401  (registers every table)


def test_every_excluded_table_really_exists():
    # the old list said "wialon_counter_states": a table that does not exist, so the real one was never excluded
    from app.models.base import Base as ModelBase

    real = set(ModelBase.metadata.tables)
    missing = sorted(_OPERATIONAL_TABLES - real)
    assert not missing, f"excluded tables that do not exist: {missing}"


def test_the_big_telemetry_feeds_are_excluded():
    for table in ("wialon_raw_receipts", "wialon_odometer_readings", "mileage_history", "mileage_calculation_inputs",
                  "wialon_counter_state", "gtk_raw_snapshots"):
        assert table in _OPERATIONAL_TABLES


def test_business_tables_are_still_audited():
    for table in ("fixed_assets", "work_orders", "maintenance_plan", "users", "wagon_mileage_opening_balances",
                  "maintenance_decision", "maintenance_intervals"):
        assert table not in _OPERATIONAL_TABLES


def test_only_pure_sync_columns_are_ignored_for_assets():
    assert "mileage" not in _SYNC_ONLY_COLUMNS["fixed_assets"]  # a mileage change is handled separately, by actor
    assert {"wialon_last_sync", "wialon_online", "wialon_speed"} <= _SYNC_ONLY_COLUMNS["fixed_assets"]
    assert "inv_number" not in _SYNC_ONLY_COLUMNS["fixed_assets"] and "status" not in _SYNC_ONLY_COLUMNS["fixed_assets"]


def test_the_export_is_bounded():
    assert 0 < audit_logs.EXPORT_MAX_ROWS <= 200_000
    assert 0 < audit_logs.EXPORT_DEFAULT_DAYS <= 90


class _Driver(Exception):
    def __init__(self, sqlstate):
        super().__init__("driver")
        self.sqlstate = sqlstate


def test_database_data_errors_become_a_422_and_other_errors_stay_500():
    from app.main import database_error_response

    assert DBAPIError in app.exception_handlers
    request = type("R", (), {"method": "GET", "url": type("U", (), {"path": "/x"})()})()
    # SQLSTATE class 22 (invalid text representation, NUL character, numeric out of range...)
    assert database_error_response(request, DBAPIError("stmt", {}, _Driver("22021"))).status_code == 422
    # the state may only be visible on the wrapped cause
    wrapped = Exception("adapter")
    wrapped.__cause__ = _Driver("22P02")
    assert database_error_response(request, DBAPIError("stmt", {}, wrapped)).status_code == 422
    # a unique violation, a deadlock... are not the caller's formatting mistake
    assert database_error_response(request, DBAPIError("stmt", {}, _Driver("23505"))).status_code == 500
