from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DailyReadinessSnapshot
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.localization import FixedAssetStatus
from app.models.organization import Section
from app.models.work_orders import WorkOrder

ANALYTICS_VIEWS = frozenset(
    {
        "executive_summary",
        "section_efficiency",
        "work_type_efficiency",
        "monthly_efficiency",
        "ai_insights_summary",
        "fleet_health",
        "work_order_tmc_details",
        "maintenance_schedule",
    }
)

REPORT_SQL: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "work-orders": (
        """
        SELECT number, unit, asset_inv_number, section, section_id, repair_kind AS work_type,
               status, priority, created_at, closed, tech, description,
               total_cost, total_norm_cost, cost_savings, avg_deviation_percent
        FROM executive_summary
        """,
        "SELECT count(*) FROM executive_summary",
        (
            "number", "unit", "asset_inv_number", "section", "work_type", "status",
            "priority", "created_at", "closed", "tech", "description",
            "total_cost", "total_norm_cost", "cost_savings", "avg_deviation_percent",
        ),
    ),
    "fixed-assets": (
        """
        SELECT fa.id, fa.inv_number, fa.name, fa.asset_type, fa.series, fa.depot,
               fa.section_id,
               s.name AS section, fa.status, fa.comm_date, fa.year_built, fa.mileage,
               fa.initial_cost, fa.owner, fa.created_at
        FROM fixed_assets fa
        LEFT JOIN sections s ON s.id = fa.section_id
        """,
        "SELECT count(*) FROM fixed_assets fa",
        (
            "id", "inv_number", "name", "asset_type", "series", "depot", "section",
            "status", "comm_date", "year_built", "mileage", "initial_cost", "owner",
            "created_at",
        ),
    ),
    "tmc-documents": (
        """
        SELECT td.id, td.doc_no, td.doc_date, td.work_order_id, wo.number AS work_order_number,
               td.section_id,
               s.name AS section, td.warehouse, td.status, td.issued_by, td.accepted_by,
               COALESCE(items.item_count, 0) AS item_count,
               COALESCE(items.total_quantity, 0) AS total_quantity,
               COALESCE(items.total_cost, 0) AS total_cost, td.created_at
        FROM tmc_documents td
        LEFT JOIN work_orders wo ON wo.id = td.work_order_id
        LEFT JOIN sections s ON s.id = td.section_id
        LEFT JOIN (
            SELECT document_id, count(*) AS item_count,
                   sum(qty) AS total_quantity, sum(qty * COALESCE(price, 0)) AS total_cost
            FROM tmc_document_items GROUP BY document_id
        ) items ON items.document_id = td.id
        """,
        """
        SELECT count(*)
        FROM tmc_documents td
        LEFT JOIN work_orders wo ON wo.id = td.work_order_id
        """,
        (
            "id", "doc_no", "doc_date", "work_order_id", "work_order_number", "section",
            "warehouse", "status", "issued_by", "accepted_by", "item_count",
            "total_quantity", "total_cost", "created_at",
        ),
    ),
}


async def list_analytics(
    db: AsyncSession,
    *,
    view_name: str,
    section_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    if view_name not in ANALYTICS_VIEWS:
        raise ValueError("Unsupported analytics block")
    where = " WHERE section_id = :section_id" if section_id is not None else ""
    parameters: dict[str, Any] = {}
    if section_id is not None:
        parameters["section_id"] = section_id
    total = (
        await db.execute(text(f"SELECT count(*) FROM {view_name}{where}"), parameters)
    ).scalar_one()
    rows = await db.execute(
        text(
            f"SELECT * FROM {view_name}{where} "
            "ORDER BY 1 NULLS LAST LIMIT :limit OFFSET :offset"
        ),
        {**parameters, "limit": limit, "offset": offset},
    )
    return [dict(row) for row in rows.mappings().all()], total


async def dashboard_assets_and_orders(
    db: AsyncSession, *, section_id: UUID | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    asset_query = (
        select(FixedAsset, Section.name.label("section_name"))
        .outerjoin(Section, Section.id == FixedAsset.section_id)
        .order_by(FixedAsset.name, FixedAsset.id)
    )
    order_query = (
        text(
            """
            SELECT wo.id, wo.number, fa.name AS unit, s.name AS section,
                   wo.section_id, wo.status, wo.priority, wo.description,
                   wo.created_at, wo.date_start, e.full_name AS tech,
                   types.work_types AS repair_kind,
                   types.work_type_ids
            FROM work_orders wo
            JOIN fixed_assets fa ON fa.id = wo.fixed_asset_id
            JOIN sections s ON s.id = wo.section_id
            LEFT JOIN employees e ON e.id = wo.executor_id
            LEFT JOIN LATERAL (
                SELECT string_agg(wt.code, ', ' ORDER BY wor.sort_order) AS work_types,
                       string_agg(wor.work_type_id::text, ', ' ORDER BY wor.sort_order) AS work_type_ids
                FROM work_order_repairs wor
                JOIN work_types wt ON wt.id = wor.work_type_id
                WHERE wor.work_order_id = wo.id
            ) types ON true
            """
        )
    )
    if section_id is not None:
        asset_query = asset_query.where(FixedAsset.section_id == section_id)
        order_query = text(f"{order_query.text} WHERE wo.section_id = :section_id")
        order_rows = await db.execute(order_query, {"section_id": section_id})
    else:
        order_rows = await db.execute(order_query)
    assets_result = (await db.execute(asset_query)).all()
    assets = [
        {
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "series": asset.series,
            "status": asset.status,
            "section_id": asset.section_id,
            "section": section_name,
            "depot": section_name,
            "mileage": asset.mileage,
        }
        for asset, section_name in assets_result
    ]
    orders = [dict(row) for row in order_rows.mappings().all()]
    return assets, orders


async def save_daily_readiness_snapshots(
    db: AsyncSession, *, snapshot_date: date, master_section_id: UUID | None
) -> None:
    asset_query = select(
        FixedAsset.id, FixedAsset.section_id, FixedAssetStatus.behavior
    ).join(FixedAssetStatus, FixedAsset.status == FixedAssetStatus.code).order_by(FixedAsset.id)
    if master_section_id is not None:
        asset_query = asset_query.where(FixedAsset.section_id == master_section_id)
    assets = (await db.execute(asset_query)).all()
    open_asset_ids = set(
        (
            await db.execute(
                select(WorkOrder.fixed_asset_id)
                .where(WorkOrder.status.in_(("pending", "in_progress")))
                .distinct()
            )
        ).scalars().all()
    )
    groups: dict[str, dict[str, Any]] = {}
    total = {"section_id": None, "asset_count": 0, "ready_count": 0}
    for asset_id, asset_section_id, asset_status in assets:
        total["asset_count"] += 1
        ready = asset_status == "operational" and asset_id not in open_asset_ids
        total["ready_count"] += int(ready)
        if asset_section_id is None:
            continue
        key = str(asset_section_id)
        group = groups.setdefault(
            key,
            {"section_id": asset_section_id, "asset_count": 0, "ready_count": 0},
        )
        group["asset_count"] += 1
        group["ready_count"] += int(ready)

    snapshots = []
    if master_section_id is None:
        snapshots.append(("all", total))
    snapshots.extend(groups.items())
    if master_section_id is not None and str(master_section_id) not in groups:
        snapshots.append(
            (
                str(master_section_id),
                {"section_id": master_section_id, "asset_count": 0, "ready_count": 0},
            )
        )
    for scope_key, values in snapshots:
        count = values["asset_count"]
        ready_count = values["ready_count"]
        snapshots_to_insert = {
            "snapshot_date": snapshot_date,
            "scope_key": scope_key,
            "section_id": values["section_id"],
            "asset_count": count,
            "ready_count": ready_count,
            "availability_percent": round(ready_count * 100 / count, 2) if count else 0,
        }
        statement = insert(DailyReadinessSnapshot).values(**snapshots_to_insert)
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                DailyReadinessSnapshot.snapshot_date,
                DailyReadinessSnapshot.scope_key,
            ]
        )
        await db.execute(statement)
    await db.commit()


async def monthly_readiness(
    db: AsyncSession, *, month_start: date, month_end: date, scope_key: str
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(
            func.date_trunc("month", DailyReadinessSnapshot.snapshot_date).label("month"),
            func.round(func.avg(DailyReadinessSnapshot.availability_percent), 2).label("pct"),
            func.count().label("days_recorded"),
        )
        .where(
            DailyReadinessSnapshot.scope_key == scope_key,
            DailyReadinessSnapshot.snapshot_date >= month_start,
            DailyReadinessSnapshot.snapshot_date < month_end,
        )
        .group_by(func.date_trunc("month", DailyReadinessSnapshot.snapshot_date))
        .order_by(func.date_trunc("month", DailyReadinessSnapshot.snapshot_date))
    )
    return [dict(row) for row in rows.mappings().all()]


async def list_report_rows(
    db: AsyncSession,
    *,
    report: str,
    section_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    status: str | None,
    asset_type: str | None,
    q: str | None,
    limit: int | None,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, tuple[str, ...]]:
    if report not in REPORT_SQL:
        raise ValueError("Unsupported report")
    select_sql, count_sql, columns = REPORT_SQL[report]
    filters: list[str] = []
    parameters: dict[str, Any] = {}
    if section_id is not None:
        filters.append("section_id = :section_id" if report == "work-orders" else (
            "fa.section_id = :section_id" if report == "fixed-assets" else "td.section_id = :section_id"
        ))
        parameters["section_id"] = section_id
    if date_from is not None:
        column = (
            "created_at" if report == "work-orders" else
            "fa.created_at" if report == "fixed-assets" else
            "td.doc_date"
        )
        filters.append(f"{column} >= :date_from")
        parameters["date_from"] = date_from
    if date_to is not None:
        column = (
            "created_at" if report == "work-orders" else
            "fa.created_at" if report == "fixed-assets" else
            "td.doc_date"
        )
        filters.append(f"{column} < :date_to_exclusive")
        parameters["date_to_exclusive"] = date_to
    if status is not None:
        filters.append("status = :status" if report == "work-orders" else (
            "fa.status = :status" if report == "fixed-assets" else "td.status = :status"
        ))
        parameters["status"] = status
    if asset_type is not None and report == "fixed-assets":
        filters.append("fa.asset_type = :asset_type")
        parameters["asset_type"] = asset_type
    if q is not None and q.strip():
        if report == "work-orders":
            filters.append("(number ILIKE :q OR unit ILIKE :q OR description ILIKE :q)")
        elif report == "fixed-assets":
            filters.append("(fa.name ILIKE :q OR fa.inv_number ILIKE :q OR fa.series ILIKE :q)")
        else:
            filters.append("(td.doc_no ILIKE :q OR wo.number ILIKE :q)")
        parameters["q"] = f"%{q.strip()}%"
    where = " WHERE " + " AND ".join(filters) if filters else ""
    total = (
        await db.execute(text(count_sql + where), parameters)
    ).scalar_one()
    sort_column = (
        "created_at" if report == "work-orders" else
        "fa.created_at" if report == "fixed-assets" else
        "td.created_at"
    )
    query = text(select_sql + where + f" ORDER BY {sort_column} DESC NULLS LAST")
    if limit is not None:
        query = text(query.text + " LIMIT :limit OFFSET :offset")
        parameters.update(limit=limit, offset=offset)
    rows = await db.execute(query, parameters)
    return [dict(row) for row in rows.mappings().all()], total, columns
