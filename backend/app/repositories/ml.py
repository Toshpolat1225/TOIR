from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset, MileageHistory
from app.models.maintenance import MaintenanceInterval, WorkType
from app.models.work_orders import WorkOrder, WorkOrderItem, WorkOrderRepair
from app.models.work_records import AiInsight


def _order_repairs_statement():
    return (
        select(
            WorkOrderRepair.work_type_id,
            WorkType.code,
            func.coalesce(func.sum(WorkOrderItem.qty), 0).label("quantity"),
        )
        .join(WorkType, WorkType.id == WorkOrderRepair.work_type_id)
        .outerjoin(WorkOrderItem, WorkOrderItem.repair_id == WorkOrderRepair.id)
    )


async def get_completed_order(
    db: AsyncSession, order_id: UUID
) -> dict[str, Any] | None:
    row = (
        await db.execute(
            select(WorkOrder, FixedAsset)
            .join(FixedAsset, FixedAsset.id == WorkOrder.fixed_asset_id)
            .where(WorkOrder.id == order_id, WorkOrder.status == "completed")
        )
    ).one_or_none()
    if row is None:
        return None
    order, asset = row
    repair_rows = (
        await db.execute(
            _order_repairs_statement()
            .where(WorkOrderRepair.work_order_id == order.id)
            .group_by(WorkOrderRepair.work_type_id, WorkType.code)
            .order_by(WorkType.code)
        )
    ).all()
    return {
        "order": order,
        "asset": asset,
        "repairs": [
            {
                "work_type_id": repair.work_type_id,
                "work_type_code": repair.code,
                "quantity": repair.quantity,
            }
            for repair in repair_rows
        ],
    }


async def get_latest_completed_order(
    db: AsyncSession, asset_id: UUID
) -> dict[str, Any] | None:
    order_id = (
        await db.execute(
            select(WorkOrder.id)
            .where(
                WorkOrder.fixed_asset_id == asset_id,
                WorkOrder.status == "completed",
            )
            .order_by(WorkOrder.closed_at.desc(), WorkOrder.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return await get_completed_order(db, order_id) if order_id else None


async def list_assets_for_analysis(db: AsyncSession) -> list[FixedAsset]:
    return list(
        (
            await db.execute(
                select(FixedAsset)
                .where(FixedAsset.asset_type.in_(("locomotive", "diesel")))
                .order_by(FixedAsset.id)
            )
        ).scalars()
    )


async def get_anomaly_history(
    db: AsyncSession,
    *,
    work_order_id: UUID,
    section_id: UUID,
    work_type_id: UUID,
    closed_before: datetime,
) -> list[Any]:
    rows = (
        await db.execute(
            select(func.coalesce(func.sum(WorkOrderItem.qty), 0).label("quantity"))
            .select_from(WorkOrder)
            .join(
                WorkOrderRepair,
                WorkOrderRepair.work_order_id == WorkOrder.id,
            )
            .outerjoin(WorkOrderItem, WorkOrderItem.repair_id == WorkOrderRepair.id)
            .where(
                WorkOrder.status == "completed",
                WorkOrder.section_id == section_id,
                WorkOrderRepair.work_type_id == work_type_id,
                WorkOrder.id != work_order_id,
                WorkOrder.closed_at < closed_before,
            )
            .group_by(WorkOrder.id, WorkOrder.closed_at)
            .order_by(WorkOrder.closed_at.desc().nullslast())
            .limit(200)
        )
    ).all()
    return [row.quantity for row in rows]


async def list_maintenance_events(
    db: AsyncSession, asset: FixedAsset
) -> list[tuple[datetime, Any]]:
    rows = (
        await db.execute(
            select(
                WorkOrder.id,
                WorkOrder.closed_at,
                WorkOrder.mileage_at_creation,
            )
            .join(
                WorkOrderRepair,
                WorkOrderRepair.work_order_id == WorkOrder.id,
            )
            .join(
                MaintenanceInterval,
                MaintenanceInterval.work_type_id == WorkOrderRepair.work_type_id,
            )
            .where(
                WorkOrder.fixed_asset_id == asset.id,
                WorkOrder.status == "completed",
                WorkOrder.closed_at.is_not(None),
                MaintenanceInterval.is_active.is_(True),
                MaintenanceInterval.asset_types.any(asset.asset_type),
            )
            .distinct()
            .order_by(WorkOrder.closed_at.desc(), WorkOrder.id.desc())
            .limit(200)
        )
    ).all()
    return [
        (row.closed_at, row.mileage_at_creation)
        for row in reversed(rows)
        if row.closed_at is not None
    ]


async def list_mileage_samples(
    db: AsyncSession, asset_id: UUID
) -> list[tuple[datetime, Any]]:
    rows = (
        await db.execute(
            select(MileageHistory.recorded_at, MileageHistory.mileage)
            .where(MileageHistory.asset_id == asset_id)
            .order_by(MileageHistory.recorded_at.desc(), MileageHistory.id.desc())
            .limit(500)
        )
    ).all()
    return [(row.recorded_at, row.mileage) for row in reversed(rows)]


async def count_recent_anomalies(
    db: AsyncSession, asset_id: UUID, since: datetime
) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).where(
                    AiInsight.asset_id == asset_id,
                    AiInsight.insight_type == "anomaly",
                    AiInsight.created_at >= since,
                )
            )
        ).scalar_one()
    )


async def get_order_insights(
    db: AsyncSession, order_id: UUID, insight_type: str
) -> list[AiInsight]:
    return list(
        (
            await db.execute(
                select(AiInsight).where(
                    AiInsight.work_order_id == order_id,
                    AiInsight.insight_type == insight_type,
                )
            )
        ).scalars()
    )


async def get_prediction_insight(
    db: AsyncSession, asset_id: UUID, order_id: UUID | None
) -> AiInsight | None:
    statement = select(AiInsight).where(
        AiInsight.asset_id == asset_id,
        AiInsight.insight_type == "prediction",
    )
    if order_id is None:
        statement = statement.where(AiInsight.work_order_id.is_(None))
    else:
        statement = statement.where(AiInsight.work_order_id == order_id)
    return (await db.execute(statement)).scalar_one_or_none()


async def list_insights(
    db: AsyncSession,
    *,
    asset_id: UUID | None,
    insight_type: str | None,
    severity: str | None,
    is_resolved: bool | None,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    filters: list[Any] = []
    if asset_id is not None:
        filters.append(AiInsight.asset_id == asset_id)
    if insight_type is not None:
        filters.append(AiInsight.insight_type == insight_type)
    if severity is not None:
        filters.append(AiInsight.severity == severity)
    if is_resolved is not None:
        filters.append(AiInsight.is_resolved.is_(is_resolved))
    if master_section_id is not None:
        filters.append(FixedAsset.section_id == master_section_id)

    count_statement = select(func.count()).select_from(AiInsight)
    statement = (
        select(AiInsight, FixedAsset.name, WorkOrder.number)
        .outerjoin(FixedAsset, FixedAsset.id == AiInsight.asset_id)
        .outerjoin(WorkOrder, WorkOrder.id == AiInsight.work_order_id)
    )
    if filters:
        count_statement = count_statement.outerjoin(
            FixedAsset, FixedAsset.id == AiInsight.asset_id
        ).where(*filters)
        statement = statement.where(*filters)
    total = int((await db.execute(count_statement)).scalar_one())
    rows = (
        await db.execute(
            statement.order_by(AiInsight.created_at.desc(), AiInsight.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        {
            "insight": row[0],
            "asset_name": row[1],
            "work_order_number": row[2],
        }
        for row in rows
    ], total
