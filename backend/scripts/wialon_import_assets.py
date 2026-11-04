#!/usr/bin/env python3
"""Import supported Wialon units as new TOIR assets.

Default mode only reports candidates and writes a CSV under /tmp.
Use --apply to create assets, baseline counters, and initial mileage history.
Existing assets are only inspected by exact Wialon ID and are never modified.
"""

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionFactory  # noqa: E402
from app.integrations.wialon_client import WialonClient, WialonUnit  # noqa: E402
from app.models.assets import FixedAsset  # noqa: E402
from app.models.asset_source_links import AssetSourceLink  # noqa: E402
from app.repositories import assets as assets_repo  # noqa: E402
from app.repositories import wialon_counters as counters_repo  # noqa: E402
from app.services.wialon_asset_import import (  # noqa: E402
    classify_asset_type,
    extract_asset_series,
)
from app.services.wialon_quality import Reading, evaluate, suspect_absolute  # noqa: E402
from app.services import asset_links as asset_links_service  # noqa: E402


@dataclass(frozen=True)
class ImportRow:
    unit_id: str
    name: str
    asset_type: str | None
    series: str | None
    inv_number: str
    source_cnm: Decimal | None
    mileage: Decimal
    suspect: bool
    skipped_reason: str | None


def build_import_rows(
    units: list[WialonUnit],
    existing_wialon_ids: set[str],
    existing_inv_numbers: set[str],
) -> list[ImportRow]:
    rows: list[ImportRow] = []
    seen_unit_ids = set(existing_wialon_ids)
    reserved_inv_numbers = set(existing_inv_numbers)

    for unit in units:
        unit_id = str(unit.unit_id)
        name = unit.name
        inv_number = f"WIALON-{unit_id}"
        asset_type = classify_asset_type(name)
        series = extract_asset_series(name)
        suspect = suspect_absolute(unit.mileage, unit.engine_hours)
        mileage = (
            Decimal("0")
            if suspect or unit.mileage is None
            else unit.mileage
        )

        if unit_id in seen_unit_ids:
            skipped_reason = "wialon_id allaqachon fixed_assets jadvalida yoki birlik takrorlangan"
        elif asset_type is None:
            skipped_reason = "nomidan TOIR turi aniqlanmadi"
        elif inv_number in reserved_inv_numbers:
            skipped_reason = f"inv_number band: {inv_number}"
        else:
            skipped_reason = None

        seen_unit_ids.add(unit_id)
        if skipped_reason is None:
            reserved_inv_numbers.add(inv_number)
        rows.append(
            ImportRow(
                unit_id=unit_id,
                name=name,
                asset_type=asset_type,
                series=series,
                inv_number=inv_number,
                source_cnm=unit.mileage,
                mileage=mileage,
                suspect=suspect,
                skipped_reason=skipped_reason,
            )
        )

    return rows


async def main(apply: bool) -> int:
    if settings.wialon_host is None or settings.wialon_token is None:
        print("CONFIG XATOSI: Wialon host/token sozlanmagan.")
        return 1

    now = datetime.now(timezone.utc)
    units = await WialonClient(
        settings.wialon_host,
        settings.wialon_token.get_secret_value(),
    ).fetch_units()

    async with SessionFactory() as db:
        existing_rows = (
            await db.execute(
                select(AssetSourceLink.external_id).where(
                    AssetSourceLink.source == "wialon",
                    AssetSourceLink.status == "active",
                )
            )
        ).all()
        existing_wialon_ids = {
            row[0] for row in existing_rows
        }
        existing_inv_numbers = set(
            (await db.execute(select(FixedAsset.inv_number))).scalars().all()
        )
        rows = build_import_rows(
            units, existing_wialon_ids, existing_inv_numbers
        )
        to_create = [row for row in rows if row.skipped_reason is None]
        skipped = [row for row in rows if row.skipped_reason is not None]
        suspicious = [row for row in rows if row.suspect]

        print(
            f"Rejim: {'APPLY' if apply else 'DRY-RUN'} | "
            f"Wialon birliklari: {len(units)} | "
            f"yaratiladi: {len(to_create)} | o'tkazib yuboriladi: {len(skipped)}"
        )
        print(
            "Majburiy qiymatlar: status=operational; "
            "cnm yo'q yoki suspect bo'lsa mileage=0; "
            "wialon_online=false; created_at/updated_at=DB server default."
        )
        for row in skipped:
            print(
                f"  O'TKAZILDI unit={row.unit_id} nom={row.name} "
                f"sabab={row.skipped_reason}"
            )
        for row in suspicious:
            print(
                f"  QO'LDA TO'G'RILASH KERAK unit={row.unit_id} "
                f"nom={row.name} cnm={row.source_cnm}"
            )

        csv_path = Path("/tmp") / f"wialon_import_assets_{now:%Y%m%d_%H%M%S}.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "unit_id",
                    "name",
                    "asset_type",
                    "series",
                    "inv_number",
                    "cnm",
                    "mileage",
                    "suspect_absolute",
                    "status",
                    "reason",
                ]
            )
            for row in rows:
                reason = row.skipped_reason
                if row.suspect:
                    reason = "; ".join(
                        part
                        for part in (reason, "qo'lda to'g'rilash kerak")
                        if part
                    )
                writer.writerow(
                    [
                        row.unit_id,
                        row.name,
                        row.asset_type,
                        row.series,
                        row.inv_number,
                        row.source_cnm,
                        row.mileage,
                        row.suspect,
                        "skipped" if row.skipped_reason else "create",
                        reason,
                    ]
                )
        print(f"CSV: {csv_path}")

        if not apply:
            print("DRY-RUN: bazaga yozilmadi. Yozish uchun --apply.")
            return 0

        units_by_id: dict[str, WialonUnit] = {}
        for unit in units:
            units_by_id.setdefault(str(unit.unit_id), unit)
        for row in to_create:
            if row.asset_type is None:
                raise RuntimeError("Import candidate has no asset type")
            unit = units_by_id[row.unit_id]
            asset = FixedAsset(
                name=row.name,
                asset_type=row.asset_type,
                series=row.series,
                inv_number=row.inv_number,
                status="operational",
                mileage=row.mileage,
                section_id=None,
                depot=None,
                wialon_online=False,
            )
            db.add(asset)
            await db.flush()
            await asset_links_service.link(
                db,
                asset.id,
                "wialon",
                row.unit_id,
                None,
                external_name=row.name,
                method="import",
            )
            reading = Reading(unit.mileage, unit.engine_hours, unit.last_message_at)
            gate = evaluate(None, reading, now=now)
            await counters_repo.save_decision(
                db, asset.id, None, gate, reading, now=now
            )
            await assets_repo.add_mileage_history(
                db, asset.id, row.mileage, "wialon"
            )

        await db.commit()
        print(f"APPLY: {len(to_create)} ta yangi aktiv yaratildi.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.apply)))
