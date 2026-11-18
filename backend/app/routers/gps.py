from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.gps import GpsAssetDetail, GpsHealthPage, GpsOverview, GpsWagonDetail, GpsWagonPage
from app.services import gps_overview as service
from app.services import gps_wagons as wagons_service

router = APIRouter(tags=["gps"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
# Next to the map, under Analytics: the same permission (nothing new to seed).
GpsViewer = Annotated[User, Depends(require_permission("analytics.view"))]

PositionVerdictQ = Literal["confirmed", "diverged", "gtk_stale", "wialon_stale", "both_stale_agree", "both_stale_apart", "wialon_only", "gtk_only", "no_position"]
DistanceVerdictQ = Literal["match", "minor_diff", "gtk_gap", "wialon_gap", "idle", "no_data", "not_collected"]
CauseQ = Literal["ok", "method", "day_open", "gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse", "wialon_gaps", "both_gaps", "not_collected", "idle", "no_data"]
HealthQ = Literal["ok", "intermittent", "dead", "frozen", "no_gtk"]


def _filters(
    days: int, date_from: date | None, date_to: date | None, q: str | None, section_id: UUID | None, asset_type: list[str] | None, model_id: UUID | None,
    verdict: list[str] | None, distance_verdict: list[str] | None, cause: list[str] | None, severity: list[str] | None, link: str | None,
    health: list[str] | None, min_diff_m: float | None, min_silence_h: float | None, moving: bool | None, min_km: float | None, max_km: float | None,
    bbox: str | None, only_issues: bool, sort_by: str, sort_dir: str,
) -> service.Filters:
    return service.Filters(
        days=days, date_from=date_from, date_to=date_to, q=q, section_id=section_id, asset_type=list(asset_type or []), model_id=model_id,
        verdict=list(verdict or []), distance_verdict=list(distance_verdict or []), cause=list(cause or []), severity=list(severity or []), link=link,
        health=list(health or []), min_diff_m=min_diff_m, min_silence_h=min_silence_h, moving=moving, min_km=min_km, max_km=max_km,
        bbox=service.parse_bbox(bbox), only_issues=only_issues, sort_by=sort_by, sort_dir=sort_dir,
    )


@router.get("/gps/overview", response_model=GpsOverview)
async def read_gps_overview(
    user: GpsViewer,
    db: DatabaseSession,
    days: Annotated[int, Query(ge=1, le=31)] = 7,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    section_id: Annotated[UUID | None, Query()] = None,
    asset_type: Annotated[list[str] | None, Query(max_length=10)] = None,
    model_id: Annotated[UUID | None, Query()] = None,
    verdict: Annotated[list[PositionVerdictQ] | None, Query()] = None,
    distance_verdict: Annotated[list[DistanceVerdictQ] | None, Query()] = None,
    cause: Annotated[list[CauseQ] | None, Query()] = None,
    severity: Annotated[list[Literal["ok", "warn", "bad"]] | None, Query()] = None,
    link: Annotated[Literal["both", "wialon_only", "gtk_only", "none"] | None, Query()] = None,
    health: Annotated[list[HealthQ] | None, Query()] = None,
    min_diff_m: Annotated[float | None, Query(ge=0)] = None,
    min_silence_h: Annotated[float | None, Query(ge=0)] = None,
    moving: Annotated[bool | None, Query()] = None,
    min_km: Annotated[float | None, Query(ge=0)] = None,
    max_km: Annotated[float | None, Query(ge=0)] = None,
    bbox: Annotated[str | None, Query(max_length=80)] = None,
    only_issues: Annotated[bool, Query()] = False,
    sort_by: Annotated[str, Query(max_length=20)] = "severity",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "desc",
    facets: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GpsOverview:
    """Every locomotive with the Wialon and the GTK tracker side by side: position verdict, daily distances with causes, health, week totals.

    Master: own section only. Filters narrow the list; the summary always describes the whole scope; `facets=true` adds per-filter counts.
    """
    f = _filters(days, date_from, date_to, q, section_id, asset_type, model_id, verdict, distance_verdict, cause, severity, link, health, min_diff_m, min_silence_h, moving, min_km, max_km, bbox, only_issues, sort_by, sort_dir)
    return await service.get_overview(db, user, f, with_facets=facets, limit=limit, offset=offset)


@router.get("/gps/overview/export")
async def export_gps_overview(
    user: GpsViewer,
    db: DatabaseSession,
    format: Annotated[Literal["csv", "xlsx"], Query()] = "csv",
    days: Annotated[int, Query(ge=1, le=31)] = 7,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    section_id: Annotated[UUID | None, Query()] = None,
    asset_type: Annotated[list[str] | None, Query(max_length=10)] = None,
    model_id: Annotated[UUID | None, Query()] = None,
    verdict: Annotated[list[PositionVerdictQ] | None, Query()] = None,
    distance_verdict: Annotated[list[DistanceVerdictQ] | None, Query()] = None,
    cause: Annotated[list[CauseQ] | None, Query()] = None,
    severity: Annotated[list[Literal["ok", "warn", "bad"]] | None, Query()] = None,
    link: Annotated[Literal["both", "wialon_only", "gtk_only", "none"] | None, Query()] = None,
    health: Annotated[list[HealthQ] | None, Query()] = None,
    min_diff_m: Annotated[float | None, Query(ge=0)] = None,
    min_silence_h: Annotated[float | None, Query(ge=0)] = None,
    moving: Annotated[bool | None, Query()] = None,
    min_km: Annotated[float | None, Query(ge=0)] = None,
    max_km: Annotated[float | None, Query(ge=0)] = None,
    bbox: Annotated[str | None, Query(max_length=80)] = None,
    only_issues: Annotated[bool, Query()] = False,
    sort_by: Annotated[str, Query(max_length=20)] = "severity",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> Response:
    """The filtered list as a file (≤ 5000 rows; the same rows and numbers as the page; master: own section only)."""
    f = _filters(days, date_from, date_to, q, section_id, asset_type, model_id, verdict, distance_verdict, cause, severity, link, health, min_diff_m, min_silence_h, moving, min_km, max_km, bbox, only_issues, sort_by, sort_dir)
    _, shown, window = await service.filtered_rows(db, user, f)
    shown = shown[:5000]
    name = f"gps_{window[-1].isoformat()}_{window[0].isoformat()}"
    if format == "xlsx":
        return Response(service.to_xlsx(shown), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    return Response(service.to_csv(shown), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@router.get("/gps/health", response_model=GpsHealthPage)
async def read_gps_health(
    user: GpsViewer,
    db: DatabaseSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    section_id: Annotated[UUID | None, Query()] = None,
    health: Annotated[list[HealthQ] | None, Query()] = None,
    days: Annotated[int, Query(ge=7, le=60)] = 30,
    sort_by: Annotated[str, Query(max_length=20)] = "worst",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GpsHealthPage:
    """The GTK trackers ranked by how reliably they report (worst first): dead, frozen, intermittent, ok."""
    return await service.get_health(db, user, q=q, section_id=section_id, health=list(health or []), days=days, sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset)


@router.get("/gps/assets/{asset_id}", response_model=GpsAssetDetail)
async def read_gps_asset(
    asset_id: UUID,
    user: GpsViewer,
    db: DatabaseSession,
    days: Annotated[int, Query(ge=1, le=31)] = 7,
    track_days: Annotated[int, Query(ge=1, le=14)] = 2,
) -> GpsAssetDetail:
    """One locomotive: both live fixes, the day-by-day table of both trackers and both stored tracks (a stranger's section: 404)."""
    return await service.get_asset_detail(db, user, asset_id, days=days, track_days=track_days)


@router.get("/gps/wagons", response_model=GpsWagonPage)
async def read_gps_wagons(
    user: GpsViewer,
    db: DatabaseSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    section_id: Annotated[UUID | None, Query()] = None,
    train: Annotated[str | None, Query(max_length=40)] = None,
    loco: Annotated[str | None, Query(max_length=60)] = None,
    confidence: Annotated[list[Literal["high", "medium", "low", "none"]] | None, Query()] = None,
    flag: Annotated[list[Literal["two_trains", "stale_membership", "loco_silent", "no_loco", "no_history"]] | None, Query()] = None,
    in_train: Annotated[bool | None, Query()] = None,
    asset_type: Annotated[str | None, Query(max_length=40)] = None,
    days: Annotated[int, Query(ge=1, le=31)] = 14,
    sort_by: Annotated[str, Query(max_length=20)] = "inv_number",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GpsWagonPage:
    """Wagons have no GPS of their own: position and km are derived from the locomotive of their GTK train (master: own section only)."""
    return await wagons_service.list_wagons(
        db, user, q=q, section_id=section_id, train=train, loco=loco, confidence=list(confidence or []), flag=list(flag or []), in_train=in_train,
        asset_type=asset_type, days=days, sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset,
    )


@router.get("/gps/wagons/{key}", response_model=GpsWagonDetail)
async def read_gps_wagon(
    key: str,
    user: GpsViewer,
    db: DatabaseSession,
    days: Annotated[int, Query(ge=1, le=31)] = 31,
) -> GpsWagonDetail:
    """One wagon (`key` = asset UUID or `gtk-<carriage id>`): its segments behind locomotives with the four distance candidates."""
    return await wagons_service.wagon_detail(db, user, key, days=days)
