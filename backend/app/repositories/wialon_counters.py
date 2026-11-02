from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.wialon_counters import WialonCounterState, WialonRejectedReading
from app.services.wialon_quality import CounterState, GateResult, Reading, Verdict


async def get_asset_by_wialon_id(db: AsyncSession, wialon_id: str) -> FixedAsset | None:
    """Faqat ANIQ wialon_id bo'yicha (nom bo'yicha taxminiy moslash yo'q)."""
    return (await db.execute(select(FixedAsset).where(FixedAsset.wialon_id == wialon_id))).scalar_one_or_none()


async def get_state_row(db: AsyncSession, asset_id) -> WialonCounterState | None:
    return (
        await db.execute(select(WialonCounterState).where(WialonCounterState.asset_id == asset_id))
    ).scalar_one_or_none()


def to_state(row: WialonCounterState | None) -> CounterState | None:
    if row is None:
        return None
    return CounterState(row.baseline_cnm, row.last_cnm, row.last_cnm_at,
                        row.baseline_cneh, row.last_cneh, row.last_cneh_at)


async def save_decision(
    db: AsyncSession, asset_id, row: WialonCounterState | None, gate: GateResult,
    reading: Reading, *, now: datetime,
) -> None:
    """Holatni upsert qiladi, qabul qilingan moto-soat deltasini yig'adi, rad etilganlarni auditga yozadi.
    Commit QILMAYDI (chaqiruvchi tranzaksiyasi ichida flush)."""
    engine_hours: Decimal | None = row.engine_hours if row is not None else None
    if gate.hours.verdict is Verdict.ACCEPTED and gate.hours.delta:
        engine_hours = (engine_hours or Decimal(0)) + gate.hours.delta
    prev = to_state(row) or CounterState()
    reasons = [d.reason for d in (gate.mileage, gate.hours) if d.reason]
    values = dict(
        asset_id=asset_id,
        baseline_cnm=gate.state.baseline_cnm, last_cnm=gate.state.last_cnm, last_cnm_at=gate.state.last_cnm_at,
        baseline_cneh=gate.state.baseline_cneh, last_cneh=gate.state.last_cneh, last_cneh_at=gate.state.last_cneh_at,
        engine_hours=engine_hours, suspect_absolute=gate.suspect_absolute,
        last_status=f"mileage={gate.mileage.verdict.value}, hours={gate.hours.verdict.value}",
        last_reason="; ".join(reasons)[:500] or None, updated_at=now,
    )
    stmt = insert(WialonCounterState).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[WialonCounterState.asset_id],
        set_={k: v for k, v in values.items() if k != "asset_id"},
    )
    await db.execute(stmt)
    for counter, decision, value, previous in (
        ("mileage", gate.mileage, reading.cnm, prev.last_cnm),
        ("engine_hours", gate.hours, reading.cneh, prev.last_cneh),
    ):
        if decision.verdict is Verdict.REJECTED:
            db.add(WialonRejectedReading(
                asset_id=asset_id, counter=counter, value=value, previous_value=previous,
                reading_at=reading.at, reason=(decision.reason or "")[:500]))
    await db.flush()


async def rebaseline(
    db: AsyncSession, asset_id, *, cnm: Decimal | None, cneh: Decimal | None, at: datetime
) -> None:
    """ADMIN amali: rad etilgan qiymat haqiqatan to'g'ri bo'lsa (masalan Wialon admini hisoblagichni
    tuzatgach) yangi baseline o'rnatadi. TOIR mileage'iga TEGMAYDI."""
    row = await get_state_row(db, asset_id)
    values = dict(asset_id=asset_id, baseline_cnm=cnm, last_cnm=cnm, last_cnm_at=at,
                  baseline_cneh=cneh, last_cneh=cneh, last_cneh_at=at,
                  engine_hours=row.engine_hours if row else None,
                  last_status="rebaselined", last_reason=None, updated_at=at)
    stmt = insert(WialonCounterState).values(**values)
    await db.execute(stmt.on_conflict_do_update(
        index_elements=[WialonCounterState.asset_id],
        set_={k: v for k, v in values.items() if k != "asset_id"}))
    await db.flush()
