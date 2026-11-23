"""DATA-05: «today» is the Tashkent day (the container runs in UTC)."""
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.core.timeutil import today_local

APP = Path(__file__).resolve().parents[1] / "app"


def test_between_midnight_and_five_tashkent_time_is_already_the_next_day():
    assert today_local(datetime(2026, 11, 23, 20, 30, tzinfo=timezone.utc)) == date(2026, 11, 24)  # 01:30 in Tashkent
    assert today_local(datetime(2026, 11, 23, 18, 59, tzinfo=timezone.utc)) == date(2026, 11, 23)  # 23:59 in Tashkent


def test_month_and_year_boundaries():
    assert today_local(datetime(2026, 12, 31, 19, 0, tzinfo=timezone.utc)) == date(2027, 1, 1)
    assert today_local(datetime(2026, 2, 28, 19, 30, tzinfo=timezone.utc)) == date(2026, 3, 1)


def test_a_naive_datetime_is_refused():
    with pytest.raises(ValueError):
        today_local(datetime(2026, 11, 23, 20, 30))


def test_no_module_uses_the_container_clock_for_today():
    offenders = [
        f"{path.relative_to(APP)}:{n}"
        for path in APP.rglob("*.py")
        if path.name != "timeutil.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"\bdate\.today\(\)|datetime\.now\(\)|datetime\.today\(\)|datetime\.utcnow\(\)", line)
    ]
    assert offenders == []
