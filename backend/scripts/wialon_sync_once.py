#!/usr/bin/env python3
"""BITTA marta sinxronlash (alohida jarayonda). Ishlayotgan serverni YOQMAYDI.

Servis `wialon_pull_enabled=false` bo'lsa 503 beradi, shuning uchun bu skriptni FLAG YOQILGAN holda,
faqat shu bitta jarayon uchun ishga tushiring. Masalan (Docker):
  docker compose run --rm -e WIALON_SYNC_ENABLED=true backend python scripts/wialon_sync_once.py
(flag nomini config.py dagi `wialon_pull_enabled` maydonidan tekshiring; hujjatlarda WIALON_SYNC_ENABLED).
Davriy sikl (main.py) bu jarayonda ishga tushmaydi — faqat bitta sync chaqiriladi.
"""
import asyncio, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionFactory  # noqa: E402
from app.services.wialon import sync_wialon_assets  # noqa: E402


async def main() -> int:
    async with SessionFactory() as db:
        result = await sync_wialon_assets(db)
        print(f"SYNC TUGADI: topildi={result.found}, yangilandi={result.updated}, topilmadi={result.not_found}")
        for name in result.not_found_units[:30]:
            print("  topilmadi:", name)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
