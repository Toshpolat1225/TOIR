from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.services import analytics as service

router = APIRouter(tags=["analytics"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
AnalyticsBlock = Literal[
    "executive-summary",
    "section-efficiency",
    "work-type-efficiency",
    "monthly-efficiency",
    "ai-insights-summary",
    "fleet-health",
    "work-order-tmc-details",
    "maintenance-schedule",
]
ReportName = Literal["work-orders", "fixed-assets", "tmc-documents"]
VIEW_NAMES = {
    "executive-summary": "executive_summary",
    "section-efficiency": "section_efficiency",
    "work-type-efficiency": "work_type_efficiency",
    "monthly-efficiency": "monthly_efficiency",
    "ai-insights-summary": "ai_insights_summary",
    "fleet-health": "fleet_health",
    "work-order-tmc-details": "work_order_tmc_details",
    "maintenance-schedule": "maintenance_schedule",
}


@router.get("/analytics/{block}", response_model=PaginatedResponse[dict])
async def get_analytics_block(
    block: AnalyticsBlock,
    user: AuthenticatedUser,
    db: DatabaseSession,
    section_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[dict]:
    items, total = await service.list_analytics(
        db,
        user,
        view_name=VIEW_NAMES[block],
        section_id=section_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


async def _report_response(
    report: ReportName,
    *,
    user: User,
    db: AsyncSession,
    section_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    status_filter: str | None,
    asset_type: str | None,
    q: str | None,
    limit: int,
    offset: int,
    csv: bool,
) -> Response | dict:
    if date_from and date_to and date_from > date_to:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    filters = {
        "report": report,
        "section_id": section_id,
        "date_from": date_from,
        "date_to": date_to,
        "status_filter": status_filter,
        "asset_type": asset_type,
        "q": q,
    }
    if csv:
        content, filename = await service.report_csv(db, user, **filters)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )
    return await service.get_report(
        db, user, **filters, limit=limit, offset=offset
    )


def _report_route(report: ReportName):
    async def endpoint(
        user: AuthenticatedUser,
        db: DatabaseSession,
        section_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status_filter: str | None = Query(default=None, alias="status", max_length=50),
        asset_type: str | None = None,
        q: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        format: Literal["json", "csv"] = "json",
    ):
        return await _report_response(
            report,
            user=user,
            db=db,
            section_id=section_id,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
            asset_type=asset_type,
            q=q,
            limit=limit,
            offset=offset,
            csv=format == "csv",
        )

    endpoint.__name__ = f"get_{report}_report"
    return endpoint


router.add_api_route(
    "/reports/work-orders", _report_route("work-orders"), methods=["GET"]
)
router.add_api_route(
    "/reports/fixed-assets", _report_route("fixed-assets"), methods=["GET"]
)
router.add_api_route(
    "/reports/tmc-documents", _report_route("tmc-documents"), methods=["GET"]
)
