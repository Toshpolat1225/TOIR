from calendar import monthrange
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics import dashboard_assets_and_orders


async def dashboard_summary(
    db: AsyncSession, *, section_id: UUID | None, today: date
) -> dict[str, Any]:
    assets, orders = await dashboard_assets_and_orders(db, section_id=section_id)
    orders.sort(key=lambda order: (order["created_at"], str(order["id"])), reverse=True)
    month_starts = []
    for offset in range(5, -1, -1):
        year, month = today.year, today.month - offset
        while month <= 0:
            year -= 1
            month += 12
        month_starts.append(date(year, month, 1))
    # Current month is measured at its end, even when that date is in the future.
    month_ends = [date(m.year, m.month, monthrange(m.year, m.month)[1]) for m in month_starts]
    params: dict[str, Any] = {f"end_{i}": end for i, end in enumerate(month_ends)}
    values_sql = ", ".join(f"(CAST(:end_{i} AS date))" for i in range(6))
    scope_sql = " AND fa.section_id = :section_id" if section_id is not None else ""
    if section_id is not None:
        params["section_id"] = section_id
    result = await db.execute(
        text(
            f"""
            WITH month_ends(month_end) AS (VALUES {values_sql}),
            totals AS (
                SELECT count(*) AS asset_count FROM fixed_assets fa
                WHERE true {scope_sql}
            ),
            open_assets AS (
                SELECT me.month_end, count(DISTINCT wo.fixed_asset_id) AS count
                FROM month_ends me
                JOIN work_orders wo ON wo.created_at::date <= me.month_end
                JOIN fixed_assets fa ON fa.id = wo.fixed_asset_id
                WHERE (wo.closed_at IS NULL OR wo.closed_at::date > me.month_end)
                  {scope_sql}
                GROUP BY me.month_end
            )
            SELECT me.month_end, totals.asset_count,
                   coalesce(open_assets.count, 0) AS open_asset_count
            FROM month_ends me CROSS JOIN totals
            LEFT JOIN open_assets USING (month_end)
            ORDER BY me.month_end
            """), params
    )
    availability = []
    for row in result.mappings():
        total = int(row["asset_count"])
        open_count = int(row["open_asset_count"])
        availability.append({
            "month": row["month_end"].strftime("%Y-%m"),
            "label": row["month_end"].strftime("%b"),
            "pct": round((1 - open_count / total) * 100, 1) if total else 0,
        })
    return {
        "assets": assets,
        "orders": orders,
        "availability": availability,
    }
