"""Pure mileage-based maintenance planning calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

HIGH_URGENCY_MAX_PERCENT = Decimal("3")
MEDIUM_URGENCY_MAX_PERCENT = Decimal("7")


@dataclass(frozen=True)
class MaintenanceTarget:
    trigger_mileage: Decimal
    remaining_km: Decimal
    scheduled_date: date
    remaining_percent: Decimal


def next_mileage_threshold(
    mileage: Decimal, interval_km: Decimal | None
) -> Decimal | None:
    if interval_km is None or interval_km <= 0:
        return None
    interval_count = (mileage / interval_km).to_integral_value(
        rounding=ROUND_CEILING
    )
    return interval_count * interval_km


def calculate_maintenance_target(
    *,
    asset_type: str,
    interval_asset_types: list[str],
    mileage: Decimal,
    interval_km: Decimal | None,
    warn_percent: Decimal,
    daily_km_estimate: int,
    today: date,
) -> MaintenanceTarget | None:
    if asset_type not in interval_asset_types or interval_km is None:
        return None
    if interval_km <= 0 or daily_km_estimate <= 0:
        return None

    trigger = next_mileage_threshold(mileage, interval_km)
    if trigger is None:
        return None
    remaining = trigger - mileage
    if remaining > interval_km * warn_percent / Decimal("100"):
        return None

    remaining_days = int(
        (remaining / Decimal(daily_km_estimate)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    return MaintenanceTarget(
        trigger_mileage=trigger,
        remaining_km=remaining,
        scheduled_date=today + timedelta(days=remaining_days),
        remaining_percent=remaining / interval_km * Decimal("100"),
    )


def maintenance_urgency(
    remaining_percent: Decimal, warn_percent: Decimal
) -> str | None:
    if remaining_percent <= HIGH_URGENCY_MAX_PERCENT:
        return "high"
    if remaining_percent <= MEDIUM_URGENCY_MAX_PERCENT:
        return "medium"
    if remaining_percent <= warn_percent:
        return "low"
    return None
