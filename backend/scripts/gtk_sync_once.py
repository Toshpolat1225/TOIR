#!/usr/bin/env python3
"""Run one GTK synchronization in the current backend environment."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionFactory  # noqa: E402
from app.services.gtk import sync_gtk  # noqa: E402


async def main() -> int:
    async with SessionFactory() as db:
        run = await sync_gtk(db)
    if run is None:
        print("GTK sync stopped after repeated login failures; restart backend to retry.")
        return 2
    print(f"GTK sync status={run.status} counts={run.counts or {}}")
    if run.error:
        print(f"GTK sync error: {run.error}")
    return 0 if run.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
