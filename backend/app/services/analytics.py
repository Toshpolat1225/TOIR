import csv
import io
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.organization import Section
from app.repositories import analytics as repository


def _scope_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Master user must be assigned to a section",
    )


def _effective_section(user: User, section_id: UUID | None) -> UUID | None:
    if user.role == "master":
        if user.section_id is None:
            raise _scope_error()
        if section_id is not None and section_id != user.section_id:
            raise HTTPException(status_code=404, detail="Analytics data not found")
        return user.section_id
    return section_id


async def list_analytics(
    db: AsyncSession,
    user: User,
    *,
    view_name: str,
    section_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    effective_section = _effective_section(user, section_id)
    try:
        return await repository.list_analytics(
            db,
            view_name=view_name,
            section_id=effective_section,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Analytics block not found") from exc


async def dashboard_summary(
    db: AsyncSession,
    user: User,
    *,
    section_id: UUID | None,
    section: str | None,
) -> dict[str, Any]:
    if section_id is not None and section is not None:
        raise HTTPException(
            status_code=422, detail="Use either section_id or section, not both"
        )
    if section is not None:
        if user.role == "master":
            effective_section_id = _effective_section(user, None)
        else:
            section_row = (
                await db.execute(select(Section).where(Section.name == section))
            ).scalar_one_or_none()
            if section_row is None:
                raise HTTPException(status_code=404, detail="Section not found")
            effective_section_id = section_row.id
    else:
        effective_section_id = _effective_section(user, section_id)

    assets, orders = await repository.dashboard_assets_and_orders(
        db, section_id=effective_section_id
    )
    snapshot_date = date.today()
    await repository.save_daily_readiness_snapshots(
        db,
        snapshot_date=snapshot_date,
        master_section_id=user.section_id if user.role == "master" else None,
    )

    month_start = (snapshot_date.replace(day=1) - timedelta(days=5 * 31)).replace(day=1)
    month_end = (snapshot_date.replace(day=1) + timedelta(days=monthrange(snapshot_date.year, snapshot_date.month)[1]))
    if month_end.month == 12:
        month_end = date(month_end.year + 1, 1, 1)
    else:
        month_end = date(month_end.year, month_end.month + 1, 1)
    scope_key = str(effective_section_id) if effective_section_id else "all"
    readiness_rows = await repository.monthly_readiness(
        db, month_start=month_start, month_end=month_end, scope_key=scope_key
    )
    readiness_by_month = {
        row["month"].strftime("%Y-%m"): row for row in readiness_rows
    }
    availability = []
    for offset in range(5, -1, -1):
        month_first = (snapshot_date.replace(day=1) - timedelta(days=offset * 31)).replace(day=1)
        month_key = month_first.strftime("%Y-%m")
        recorded = readiness_by_month.get(month_key)
        availability.append(
            {
                "month": month_key,
                "label": month_first.strftime("%b"),
                "pct": float(recorded["pct"]) if recorded else None,
                "days_recorded": int(recorded["days_recorded"]) if recorded else 0,
            }
        )
    return {
        "assets": assets,
        "orders": orders,
        "availability": availability,
        "availability_history_starts_at": snapshot_date.isoformat(),
    }


async def get_report(
    db: AsyncSession,
    user: User,
    *,
    report: str,
    section_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    status_filter: str | None,
    asset_type: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    effective_section = _effective_section(user, section_id)
    inclusive_end = date_to + timedelta(days=1) if date_to else None
    try:
        items, total, _ = await repository.list_report_rows(
            db,
            report=report,
            section_id=effective_section,
            date_from=date_from,
            date_to=inclusive_end,
            status=status_filter,
            asset_type=asset_type,
            q=q,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def report_csv(
    db: AsyncSession,
    user: User,
    *,
    report: str,
    section_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    status_filter: str | None,
    asset_type: str | None,
    q: str | None,
) -> tuple[str, str]:
    effective_section = _effective_section(user, section_id)
    inclusive_end = date_to + timedelta(days=1) if date_to else None
    try:
        rows, _, columns = await repository.list_report_rows(
            db,
            report=report,
            section_id=effective_section,
            date_from=date_from,
            date_to=inclusive_end,
            status=status_filter,
            asset_type=asset_type,
            q=q,
            limit=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(
            [
                value.isoformat() if isinstance(value, (date, datetime)) else value
                for value in (row.get(column) for column in columns)
            ]
        )
    return "\ufeff" + output.getvalue(), report
