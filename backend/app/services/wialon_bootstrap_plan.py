"""Bootstrap rejasi (sof mantiq): Wialon birliklari <-> TOIR aktivlari moslashuvi va farqlar hisoboti."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from app.services.wialon_quality import suspect_absolute


def norm_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


@dataclass(frozen=True)
class PlanRow:
    status: str            # mapped | name_unique | ambiguous | unmapped | asset_without_unit
    unit_id: str | None
    unit_name: str | None
    asset_id: Any
    asset_name: str | None
    toir_mileage: Decimal | None
    cnm: Decimal | None
    diff: Decimal | None   # cnm - toir_mileage (faqat ma'lumot uchun)
    cneh: Decimal | None
    suspect_absolute: bool
    has_state: bool


def plan_bootstrap(units: Iterable[Any], assets: Iterable[Any], state_asset_ids: set) -> list[PlanRow]:
    """units: unit_id, name, mileage, engine_hours. assets: id, name, wialon_id, mileage."""
    assets = list(assets)
    units = list(units)
    by_wid = {str(a.wialon_id): a for a in assets if a.wialon_id}
    by_name: dict[str, list] = {}
    for a in assets:
        by_name.setdefault(norm_name(a.name), []).append(a)
    unit_names = Counter(norm_name(u.name) for u in units)
    rows: list[PlanRow] = []
    seen_assets = set()
    for u in units:
        a, status = by_wid.get(str(u.unit_id)), "mapped"
        if a is None:
            cands = [c for c in by_name.get(norm_name(u.name), []) if not c.wialon_id]
            if len(cands) == 1 and unit_names[norm_name(u.name)] == 1:
                a, status = cands[0], "name_unique"
            elif len(by_name.get(norm_name(u.name), [])) > 1 or unit_names[norm_name(u.name)] > 1:
                status = "ambiguous"
            else:
                status = "unmapped"
        if a is not None:
            seen_assets.add(a.id)
        diff = (u.mileage - a.mileage) if (a is not None and u.mileage is not None and a.mileage is not None) else None
        rows.append(PlanRow(status, str(u.unit_id), u.name, a.id if a else None, a.name if a else None,
                            a.mileage if a else None, u.mileage, diff, u.engine_hours,
                            suspect_absolute(u.mileage, u.engine_hours), bool(a and a.id in state_asset_ids)))
    for a in assets:
        if a.wialon_id and a.id not in seen_assets:
            rows.append(PlanRow("asset_without_unit", str(a.wialon_id), None, a.id, a.name, a.mileage,
                                None, None, None, False, a.id in state_asset_ids))
    return rows


def summarize(rows: list[PlanRow]) -> dict[str, int]:
    c = Counter(r.status for r in rows)
    c["suspect_absolute"] = sum(r.suspect_absolute for r in rows)
    c["mapped_without_state"] = sum(r.status == "mapped" and not r.has_state for r in rows)
    c["big_diff_gt_1000km"] = sum(r.diff is not None and abs(r.diff) > 1000 for r in rows)
    return dict(c)
