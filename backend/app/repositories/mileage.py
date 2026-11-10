from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.mileage import WagonMileageOpeningBalance
from app.models.mileage import WagonMileageLedger


async def has_confirmed_projection(db: AsyncSession, asset_id: UUID) -> bool:
    return bool(
        await db.scalar(
            select(
                exists().where(
                    WagonMileageLedger.wagon_asset_id == asset_id,
                    WagonMileageLedger.status == "active",
                    WagonMileageLedger.classification == "CONFIRMED",
                    WagonMileageLedger.calculation_eligible.is_(True),
                )
            )
        )
    )


async def get_asset_for_opening(
    db: AsyncSession,
    asset_id: UUID,
    *,
    section_id: UUID | None = None,
    lock: bool = False,
) -> FixedAsset | None:
    statement = select(FixedAsset).where(FixedAsset.id == asset_id)
    if section_id is not None:
        statement = statement.where(FixedAsset.section_id == section_id)
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def add_opening_balance(
    db: AsyncSession, opening: WagonMileageOpeningBalance
) -> WagonMileageOpeningBalance:
    db.add(opening)
    await db.flush()
    return opening


async def get_opening_for_update(
    db: AsyncSession, opening_id: UUID
) -> WagonMileageOpeningBalance | None:
    result = await db.execute(
        select(WagonMileageOpeningBalance)
        .where(WagonMileageOpeningBalance.id == opening_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_approved_opening_for_update(
    db: AsyncSession, asset_id: UUID
) -> WagonMileageOpeningBalance | None:
    result = await db.execute(
        select(WagonMileageOpeningBalance)
        .where(
            WagonMileageOpeningBalance.asset_id == asset_id,
            WagonMileageOpeningBalance.status == "approved",
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def list_opening_balances(
    db: AsyncSession,
    *,
    asset_id: UUID | None = None,
    section_id: UUID | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[WagonMileageOpeningBalance], int]:
    statement = select(WagonMileageOpeningBalance).join(
        FixedAsset, FixedAsset.id == WagonMileageOpeningBalance.asset_id
    )
    count_statement = (
        select(func.count())
        .select_from(WagonMileageOpeningBalance)
        .join(FixedAsset, FixedAsset.id == WagonMileageOpeningBalance.asset_id)
    )
    if asset_id is not None:
        statement = statement.where(WagonMileageOpeningBalance.asset_id == asset_id)
        count_statement = count_statement.where(
            WagonMileageOpeningBalance.asset_id == asset_id
        )
    if section_id is not None:
        statement = statement.where(FixedAsset.section_id == section_id)
        count_statement = count_statement.where(FixedAsset.section_id == section_id)
    if status is not None:
        statement = statement.where(WagonMileageOpeningBalance.status == status)
        count_statement = count_statement.where(
            WagonMileageOpeningBalance.status == status
        )

    total = await db.scalar(count_statement)
    result = await db.execute(
        statement.order_by(
            WagonMileageOpeningBalance.created_at.desc(),
            WagonMileageOpeningBalance.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)
