"""Read-only per-wagon mileage coverage report (never writes)."""
import csv
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import and_, cast, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkTrainMember
from app.models.mileage import WagonMileageLedger, WagonMileageOpeningBalance
from app.services.wagon_mileage_reasons import describe

ZERO = Decimal("0")
CSV_FIELDS = [
    "asset_id",
    "inv_number",
    "status",
    "reason_code",
    "reason_text",
    "action",
    "opening_status",
    "opening_km",
    "confirmed_km",
    "estimated_km",
    "held_periods",
    "projected_km",
    "fixed_assets_mileage",
]


async def build_report(db: AsyncSession) -> dict[str, Any]:
    wagons = (
        await db.execute(
            select(FixedAsset.id, FixedAsset.inv_number, FixedAsset.mileage).where(
                FixedAsset.asset_type == "wagon"
            )
        )
    ).all()

    linked = {
        row[0]: row[1]
        for row in (
            await db.execute(
                select(AssetSourceLink.asset_id, AssetSourceLink.external_id).where(
                    AssetSourceLink.source == "gtk", AssetSourceLink.status == "active"
                )
            )
        ).all()
    }
    with_membership = set(
        (
            await db.scalars(
                select(AssetSourceLink.asset_id)
                .join(
                    GtkTrainMember,
                    and_(
                        GtkTrainMember.kind == "carriage",
                        cast(GtkTrainMember.object_gtk_id, String)
                        == AssetSourceLink.external_id,
                    ),
                )
                .where(
                    AssetSourceLink.source == "gtk", AssetSourceLink.status == "active"
                )
            )
        ).all()
    )

    openings: dict[Any, tuple[str, Decimal]] = {}
    for asset_id, status, km in (
        await db.execute(
            select(
                WagonMileageOpeningBalance.asset_id,
                WagonMileageOpeningBalance.status,
                WagonMileageOpeningBalance.mileage_km,
            ).where(WagonMileageOpeningBalance.status.in_(("approved", "pending")))
        )
    ).all():
        if asset_id not in openings or status == "approved":
            openings[asset_id] = (status, km)

    ledger: dict[Any, dict[str, Any]] = defaultdict(
        lambda: {
            "CONFIRMED": ZERO,
            "ESTIMATED": ZERO,
            "HELD": 0,
            "estimated_rows": 0,
            "reasons": Counter(),
        }
    )
    for asset_id, classification, distance, eligible, reason in (
        await db.execute(
            select(
                WagonMileageLedger.wagon_asset_id,
                WagonMileageLedger.classification,
                WagonMileageLedger.distance_km,
                WagonMileageLedger.calculation_eligible,
                WagonMileageLedger.calculation_details["reason"].astext,
            ).where(WagonMileageLedger.status == "active")
        )
    ).all():
        bucket = ledger[asset_id]
        if classification == "HELD":
            bucket["HELD"] += 1
            bucket["reasons"][reason or "unknown"] += 1
        elif eligible:
            bucket[classification] += distance
            if classification == "ESTIMATED":
                bucket["estimated_rows"] += 1

    rows: list[dict[str, Any]] = []
    for asset_id, inv_number, mileage in sorted(wagons, key=lambda w: str(w[1])):
        opening = openings.get(asset_id)
        bucket = ledger.get(asset_id)
        code = None
        if asset_id not in linked:
            status, code = "HELD", "gtk_link_missing"
        elif asset_id not in with_membership:
            status, code = "HELD", "no_gtk_membership"
        elif opening is None or opening[0] != "approved":
            status, code = "HELD", "approved_opening_balance_missing"
        elif bucket is None:
            status, code = "HELD", "no_calculated_period_yet"
        elif bucket["HELD"]:
            status, code = "HELD", bucket["reasons"].most_common(1)[0][0]
        elif bucket["estimated_rows"] > 0:
            status = "ESTIMATED"
        else:
            status = "CONFIRMED"
        confirmed = bucket["CONFIRMED"] if bucket else ZERO
        estimated = bucket["ESTIMATED"] if bucket else ZERO
        approved = opening is not None and opening[0] == "approved"
        info = describe(code)
        rows.append(
            {
                "asset_id": str(asset_id),
                "inv_number": inv_number,
                "status": status,
                "reason_code": info["code"],
                "reason_text": info["text"],
                "action": info["action"],
                "opening_status": opening[0] if opening else "none",
                "opening_km": str(opening[1]) if opening else "",
                "confirmed_km": str(confirmed),
                "estimated_km": str(estimated),
                "held_periods": bucket["HELD"] if bucket else 0,
                "projected_km": (
                    str(opening[1] + confirmed + estimated) if approved else ""
                ),
                "fixed_assets_mileage": str(mileage),
            }
        )

    status_counts = Counter(row["status"] for row in rows)
    reason_counts = Counter(
        row["reason_code"] for row in rows if row["status"] == "HELD"
    )
    km_by_status = {"CONFIRMED": ZERO, "ESTIMATED": ZERO}
    for bucket in ledger.values():
        km_by_status["CONFIRMED"] += bucket["CONFIRMED"]
        km_by_status["ESTIMATED"] += bucket["ESTIMATED"]
    return {
        "wagons": len(rows),
        "status_counts": {
            key: status_counts.get(key, 0) for key in ("CONFIRMED", "ESTIMATED", "HELD")
        },
        "km_by_status": {key: str(value) for key, value in km_by_status.items()},
        "held_reasons": dict(reason_counts.most_common()),
        "held_reason_details": {code: describe(code) for code in reason_counts},
        "rows": rows,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
