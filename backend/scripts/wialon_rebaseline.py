#!/usr/bin/env python3
"""Bitta birlik uchun yangi baseline o'rnatish (Wialon admini hisoblagichni tuzatgandan KEYIN).
STANDART = DRY-RUN. TOIR mileage'iga TEGMAYDI, faqat wialon_counter_state ni yangilaydi.

  python scripts/wialon_rebaseline.py --unit-id 366            # ko'rsatadi
  python scripts/wialon_rebaseline.py --unit-id 366 --apply    # yozadi
"""
import argparse, asyncio, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionFactory  # noqa: E402
from app.integrations.wialon_client import WialonClient  # noqa: E402
from app.repositories import wialon_counters as repo  # noqa: E402


async def main(unit_id: str, apply: bool) -> int:
    units = await WialonClient(settings.wialon_host, settings.wialon_token.get_secret_value()).fetch_units()
    unit = next((u for u in units if str(u.unit_id) == unit_id), None)
    if unit is None:
        print(f"Wialon'da birlik {unit_id} topilmadi."); return 1
    async with SessionFactory() as db:
        asset = await repo.get_asset_by_wialon_id(db, unit_id)
        if asset is None:
            print(f"TOIR'da wialon_id={unit_id} bo'lgan aktiv yo'q."); return 1
        row = await repo.get_state_row(db, asset.id)
        print(f"Aktiv: {asset.name} | TOIR mileage: {asset.mileage}")
        print(f"Wialon hozir: cnm={unit.mileage} cneh={unit.engine_hours} (xabar: {unit.last_message_at})")
        print(f"Saqlangan baseline/last: cnm={row.last_cnm if row else None} cneh={row.last_cneh if row else None}")
        if not apply:
            print("DRY-RUN: hech narsa yozilmadi. Yozish uchun --apply."); return 0
        await repo.rebaseline(db, asset.id, cnm=unit.mileage, cneh=unit.engine_hours,
                              at=unit.last_message_at or datetime.now(timezone.utc))
        await db.commit()
        print("Yangi baseline yozildi. TOIR mileage o'zgarmadi.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--unit-id", required=True); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(); sys.exit(asyncio.run(main(a.unit_id, a.apply)))
