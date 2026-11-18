"""mileage.asset: total mileage of an asset (a locomotive: the odometer figure + the last 7 days from GPS; a wagon: the ledger projection + the train-derived km)."""
from __future__ import annotations

from fastapi import HTTPException

from app.schemas.assistant import CardRow
from app.services import assets as assets_service
from app.services import gps_overview
from app.services.assistant.handlers._common import asset_row_card, entity_for, km, km_value, need_asset, not_found, t
from app.services.assistant.registry import handler
from app.services.assistant.types import Ctx, Result, Slots


@handler("mileage.asset")
async def mileage(ctx: Ctx, slots: Slots) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    try:
        read = await assets_service.get_fixed_asset(ctx.db, asset.id, master_section_id=ctx.master_section_id)
    except HTTPException:
        return not_found(ctx, "Texnika topilmadi", "Техника не найдена")
    rows = [CardRow(label=t(ctx, "Umumiy probeg", "Общий пробег"), value=km_value(read.mileage, 0), tone="ok")]
    week = None
    if asset.is_locomotive:
        try:
            detail = await gps_overview.get_asset_detail(ctx.db, ctx.user, asset.id, days=7, track_days=1, now=ctx.now)
            week = detail.row.week_fused_m
            rows.append(CardRow(label=t(ctx, "So'nggi 7 kun (GPS)", "За 7 дней (GPS)"), value=km(week)))
        except HTTPException:
            pass
    else:
        rows.append(CardRow(label=t(ctx, "Eslatma", "Примечание"), value=t(ctx, "Vagon probegi sostav a'zoligi bo'yicha hisoblanadi.", "Пробег вагона считается по составу.")))
    card = asset_row_card(ctx, asset, kind="metric", extra=rows)
    speak = t(ctx, f"{asset.inv_number} umumiy probegi {float(read.mileage):.0f} kilometr.", f"Общий пробег {asset.inv_number}: {float(read.mileage):.0f} километров.")
    return Result(cards=[card], speak=speak, entities=entity_for(asset))
