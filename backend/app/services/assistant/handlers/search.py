"""find.asset, asset.info: the asset card, read through the assets service (master: only his section)."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.assets import FixedAsset

from app.schemas.assistant import Card, CardRow
from app.services import assets as assets_service
from app.services.assistant.handlers._common import (
    asset_row_card, card_href, entity_for, error_card, km_value, need_asset, not_found, t, text_card, type_name,
)
from app.services.assistant.registry import handler
from app.services.assistant.types import Ctx, Result, Slots


async def _read(ctx: Ctx, asset_id):
    try:
        return await assets_service.get_fixed_asset(ctx.db, asset_id, master_section_id=ctx.master_section_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise


def _rows(ctx: Ctx, read, full: bool) -> list[CardRow]:
    rows = [
        CardRow(label=t(ctx, "Holati", "Статус"), value=str(read.status)),
        CardRow(label=t(ctx, "Probeg", "Пробег"), value=km_value(read.mileage, 0)),
    ]
    if full:
        rows += [
            CardRow(label=t(ctx, "Oxirgi ТО", "Последнее ТО"), value=read.last_maint_date.isoformat() if read.last_maint_date else "—"),
            CardRow(label=t(ctx, "Keyingi ТО", "Следующее ТО"), value=read.next_maint_date.isoformat() if read.next_maint_date else "—"),
            CardRow(label=t(ctx, "Ishlab chiqarilgan yil", "Год выпуска"), value=str(read.year_built) if read.year_built else "—"),
            CardRow(label=t(ctx, "Seriya / reg. raqam", "Серийный / рег. номер"), value=read.serial_number or "—"),
            CardRow(label="Wialon", value=t(ctx, "ulangan", "привязан") if read.wialon_id else t(ctx, "ulanmagan", "не привязан")),
        ]
    return rows


async def _asset_answer(ctx: Ctx, slots: Slots, full: bool) -> Result:
    asset, ask = await need_asset(ctx, slots)
    if asset is None:
        return ask  # type: ignore[return-value]
    read = await _read(ctx, asset.id)
    if read is None:
        return not_found(ctx, "Texnika topilmadi", "Техника не найдена")
    asset.section_id = read.section_id
    card = asset_row_card(ctx, asset, extra=_rows(ctx, read, full), href=card_href(asset))
    speak = t(ctx, f"{asset.inv_number}: {asset.name}, probeg {float(read.mileage):.0f} km, holati {read.status}.", f"{asset.inv_number}: {asset.name}, пробег {float(read.mileage):.0f} км, статус {read.status}.")
    return Result(cards=[card], speak=speak, entities=entity_for(asset))


@handler("find.asset")
async def find_asset(ctx: Ctx, slots: Slots) -> Result:
    return await _asset_answer(ctx, slots, full=False)


@handler("asset.info")
async def asset_info(ctx: Ctx, slots: Slots) -> Result:
    return await _asset_answer(ctx, slots, full=True)


@handler("fleet.count")
async def fleet_count(ctx: Ctx, slots: Slots) -> Result:
    """How many units there are, by type (a master: his own section only)."""
    stmt = select(FixedAsset.asset_type, func.count()).where(FixedAsset.decommissioned_at.is_(None)).group_by(FixedAsset.asset_type)
    if ctx.user.role == "master":
        stmt = stmt.where(FixedAsset.section_id == ctx.user.section_id)
    rows = sorted((await ctx.db.execute(stmt)).all(), key=lambda r: -r[1])
    total = sum(n for _type, n in rows)
    if not total:
        msg = t(ctx, "Texnika topilmadi.", "Техника не найдена.")
        return Result(cards=[text_card(msg, tone="info")], speak=msg)
    card = Card(kind="metric", title=t(ctx, "Texnika soni", "Количество техники"), rows=[CardRow(label=t(ctx, "Jami", "Всего"), value=str(total))] + [CardRow(label=type_name(ctx, a_type), value=str(n)) for a_type, n in rows], href="/dashboard/os")
    top = ", ".join(f"{type_name(ctx, a_type)} {n}" for a_type, n in rows[:3])
    return Result(cards=[card], speak=t(ctx, f"Jami {total} ta texnika: {top}.", f"Всего техники {total}: {top}."))
