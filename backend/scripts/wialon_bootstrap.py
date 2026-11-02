#!/usr/bin/env python3
"""Wialon <-> TOIR bootstrap. STANDART REJIM = DRY-RUN (DB'ga yozmaydi).

  python scripts/wialon_bootstrap.py                     # faqat hisobot (+ CSV)
  python scripts/wialon_bootstrap.py --apply             # mapped aktivlar uchun baseline holat yozadi
  python scripts/wialon_bootstrap.py --apply --map-exact-names
        # + nomi aynan mos va YAGONA bo'lgan aktivlarga wialon_id yozadi (ambiguous/unmapped'ga tegmaydi)

TOIR mileage'iga HECH QACHON tegmaydi. Backend papkasida ishga tushiring (app paketi import qilinadi).
"""
import argparse, asyncio, csv, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionFactory  # noqa: E402
from app.integrations.wialon_client import WialonClient  # noqa: E402
from app.models.assets import FixedAsset  # noqa: E402
from app.models.wialon_counters import WialonCounterState  # noqa: E402
from app.repositories import wialon_counters as repo  # noqa: E402
from app.services.wialon_bootstrap_plan import plan_bootstrap, summarize  # noqa: E402
from app.services.wialon_quality import Reading, evaluate  # noqa: E402


async def main(apply: bool, map_exact: bool) -> int:
    if settings.wialon_host is None or settings.wialon_token is None:
        print("CONFIG XATOSI: Wialon host/token sozlanmagan."); return 1
    now = datetime.now(timezone.utc)
    units = await WialonClient(settings.wialon_host, settings.wialon_token.get_secret_value()).fetch_units()
    async with SessionFactory() as db:
        assets = (await db.execute(select(FixedAsset))).scalars().all()
        state_ids = set((await db.execute(select(WialonCounterState.asset_id))).scalars().all())
        rows = plan_bootstrap(units, assets, state_ids)
        print(f"Rejim: {'APPLY (yozadi)' if apply else 'DRY-RUN (yozmaydi)'} | Wialon birliklari: {len(units)} | TOIR aktivlari: {len(assets)}")
        for k, v in sorted(summarize(rows).items()):
            print(f"  {k:<24} {v}")
        print("\nE'TIBOR TALAB QILADIGANLAR (ambiguous / unmapped / katta farq / shubhali):")
        for r in rows:
            if r.status in ("ambiguous", "unmapped", "asset_without_unit") or r.suspect_absolute or (r.diff is not None and abs(r.diff) > 1000):
                print(f"  [{r.status}] unit={r.unit_id} {r.unit_name} | asset={r.asset_name} | TOIR={r.toir_mileage} cnm={r.cnm} "
                      f"farq={r.diff} | shubhali={r.suspect_absolute}")
        csv_path = Path(__file__).resolve().parent / f"wialon_bootstrap_{now:%Y%m%d_%H%M%S}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["status", "unit_id", "unit_name", "asset_id", "asset_name", "toir_mileage", "cnm", "diff", "cneh", "suspect", "has_state"])
            for r in rows:
                w.writerow([r.status, r.unit_id, r.unit_name, r.asset_id, r.asset_name, r.toir_mileage, r.cnm, r.diff, r.cneh, r.suspect_absolute, r.has_state])
        print(f"\nCSV: {csv_path}")
        if not apply:
            print("DRY-RUN: DB'ga hech narsa yozilmadi. Yozish uchun --apply."); return 0

        by_unit = {str(u.unit_id): u for u in units}
        by_asset = {a.id: a for a in assets}
        mapped = baselined = 0
        for r in rows:
            if r.status == "name_unique" and map_exact:
                by_asset[r.asset_id].wialon_id = r.unit_id          # unique constraint buzilsa commit xato beradi
                await db.flush()
            elif r.status != "mapped":
                continue
            if r.has_state:
                continue
            u = by_unit[r.unit_id]
            reading = Reading(u.mileage, u.engine_hours, u.last_message_at)
            gate = evaluate(None, reading, now=now)
            await repo.save_decision(db, r.asset_id, None, gate, reading, now=now)
            baselined += 1
        await db.commit()
        print(f"APPLY: baseline yozildi: {baselined} ta. TOIR mileage o'zgartirilmadi.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--map-exact-names", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.apply, a.map_exact_names)))
