"""SQL of the spare-part analytics. Every function is one statement; the master section filter is part of the statement."""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OPEN_PLAN_STATUSES = ("scheduled", "blocked", "in_progress")
OPEN_ORDER_STATUSES = ("ordered", "in_transit", "partial")
ISSUED_STATUSES = ("issued", "closed")


async def plan_rows(db: AsyncSession, *, end: date, section_id: UUID | None) -> list[dict[str, Any]]:
    """Open plan rows with a date up to `end` (overdue rows included), their unit and interval."""
    where = "AND fa.section_id = :section_id" if section_id is not None else ""
    sql = f"""
        SELECT mp.id::text AS plan_id, fa.id::text AS asset_id, fa.inv_number, fa.asset_type, fa.section_id,
               COALESCE(EXTRACT(year FROM fa.commissioned_at)::int, fa.year_built) AS year,
               mi.code AS interval_code, mi.name AS interval_name, wt.id AS work_type_id, wt.code AS work_type_code,
               mi.rank, mi.interval_days, mi.interval_km, mp.scheduled_date, mp.status
        FROM maintenance_plan mp
        JOIN fixed_assets fa ON fa.id = mp.asset_id
        JOIN maintenance_intervals mi ON mi.id = mp.interval_id
        LEFT JOIN work_types wt ON wt.id = mi.work_type_id OR (mi.work_type_id IS NULL AND wt.code = mi.code)
        WHERE mp.status = ANY(:statuses) AND mp.scheduled_date IS NOT NULL AND mp.scheduled_date <= :end
          AND mi.is_active AND fa.decommissioned_at IS NULL {where}
        ORDER BY mp.scheduled_date, fa.inv_number
    """
    params: dict[str, Any] = {"statuses": list(OPEN_PLAN_STATUSES), "end": end}
    if section_id is not None:
        params["section_id"] = section_id
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


async def norms_for(db: AsyncSession, work_type_ids: list[UUID]) -> list[dict[str, Any]]:
    if not work_type_ids:
        return []
    sql = """
        SELECT nn.nomenclature_id, nn.work_type_id, d.name AS department, nn.standard_quantity, nn.avg_price
        FROM nomenclature_norms nn JOIN departments d ON d.id = nn.department_id
        WHERE nn.work_type_id = ANY(:ids)
    """
    return [dict(r) for r in (await db.execute(text(sql), {"ids": work_type_ids})).mappings().all()]


async def history_totals(db: AsyncSession, *, date_from: date, section_id: UUID | None) -> list[dict[str, Any]]:
    """Issued quantity and money per nomenclature since `date_from`."""
    where = "AND d.section_id = :section_id" if section_id is not None else ""
    sql = f"""
        SELECT i.nomenclature_id, sum(i.qty) AS qty, sum(i.qty * COALESCE(i.price, 0)) AS cost
        FROM tmc_document_items i JOIN tmc_documents d ON d.id = i.document_id
        WHERE d.status = ANY(:statuses) AND d.doc_date >= :date_from AND i.nomenclature_id IS NOT NULL {where}
        GROUP BY i.nomenclature_id
    """
    params: dict[str, Any] = {"statuses": list(ISSUED_STATUSES), "date_from": date_from}
    if section_id is not None:
        params["section_id"] = section_id
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


async def nomenclature_meta(db: AsyncSession, ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    if not ids:
        return {}
    sql = """
        SELECT n.id, n.name, n.code, n.unit, d.name AS department
        FROM nomenclature n JOIN departments d ON d.id = n.department_id WHERE n.id = ANY(:ids)
    """
    return {r["id"]: dict(r) for r in (await db.execute(text(sql), {"ids": ids})).mappings().all()}


async def consumption_rows(db: AsyncSession, *, date_from: date, section_id: UUID | None) -> list[dict[str, Any]]:
    """Issued lines grouped by (nomenclature, month, work type, asset type) with the overuse against the repair norm."""
    where = "AND d.section_id = :section_id" if section_id is not None else ""
    sql = f"""
        SELECT i.nomenclature_id, n.name, n.code, n.unit, date_trunc('month', d.doc_date)::date AS month,
               wt.code AS work_type, fa.asset_type,
               sum(i.qty) AS qty,
               sum(i.qty * COALESCE(i.price, nn.avg_price, 0)) AS cost,
               sum(CASE WHEN nn.standard_quantity IS NOT NULL THEN GREATEST(i.qty - nn.standard_quantity, 0) ELSE 0 END) AS over_qty,
               sum(CASE WHEN nn.standard_quantity IS NOT NULL
                        THEN GREATEST(i.qty - nn.standard_quantity, 0) * COALESCE(i.price, nn.avg_price, 0) ELSE 0 END) AS over_cost
        FROM tmc_document_items i
        JOIN tmc_documents d ON d.id = i.document_id
        JOIN nomenclature n ON n.id = i.nomenclature_id
        LEFT JOIN work_types wt ON wt.id = d.work_type_id
        LEFT JOIN work_orders wo ON wo.id = d.work_order_id
        LEFT JOIN fixed_assets fa ON fa.id = wo.fixed_asset_id
        LEFT JOIN nomenclature_norms nn
               ON nn.nomenclature_id = i.nomenclature_id AND nn.department_id = n.department_id AND nn.work_type_id = d.work_type_id
        WHERE d.status = ANY(:statuses) AND d.doc_date >= :date_from {where}
        GROUP BY i.nomenclature_id, n.name, n.code, n.unit, date_trunc('month', d.doc_date), wt.code, fa.asset_type
    """
    params: dict[str, Any] = {"statuses": list(ISSUED_STATUSES), "date_from": date_from}
    if section_id is not None:
        params["section_id"] = section_id
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


async def stock_now(db: AsyncSession) -> dict[UUID, dict[str, Any]]:
    """The latest balance of every (nomenclature, warehouse), summed per nomenclature."""
    sql = """
        SELECT nomenclature_id, sum(qty) AS qty, max(as_of) AS as_of, count(*) AS warehouses
        FROM (SELECT DISTINCT ON (nomenclature_id, warehouse) nomenclature_id, warehouse, qty, as_of
              FROM stock_balances ORDER BY nomenclature_id, warehouse, as_of DESC) latest
        GROUP BY nomenclature_id
    """
    return {r["nomenclature_id"]: dict(r) for r in (await db.execute(text(sql))).mappings().all()}


async def supplier_terms_map(db: AsyncSession) -> dict[UUID, dict[str, Any]]:
    rows = (await db.execute(text("SELECT nomenclature_id, supplier, lead_time_days, min_order_qty, safety_days FROM supplier_terms"))).mappings().all()
    return {r["nomenclature_id"]: dict(r) for r in rows}


async def open_orders(db: AsyncSession) -> list[dict[str, Any]]:
    sql = """
        SELECT nomenclature_id, qty - qty_received AS qty_open, expected_on, ordered_on
        FROM purchase_orders WHERE status = ANY(:statuses) AND qty > qty_received
    """
    return [dict(r) for r in (await db.execute(text(sql), {"statuses": list(OPEN_ORDER_STATUSES)})).mappings().all()]
