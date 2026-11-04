from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.gtk import (
    GtkCarriageRead,
    GtkCreateAssetRequest,
    GtkCreateAssetsResponse,
    GtkLinkBatchRequest,
    GtkLinkBatchResponse,
    GtkLocomotiveRead,
    GtkMatchReport,
    GtkStatusRead,
    GtkSyncRunRead,
    GtkTrainDetail,
    GtkTrainRead,
    GtkWagonMileageList,
)
from app.services import gtk as service

router = APIRouter(prefix="/gtk", tags=["GTK source"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
GtkViewer = Annotated[User, Depends(require_permission("gtk.view"))]
GtkManager = Annotated[User, Depends(require_permission("gtk.manage"))]
AssetLinkManager = Annotated[
    User, Depends(require_permission("asset_links.manage"))
]
SortOrder = Literal["asc", "desc"]
LocomotiveSort = Literal[
    "gtk_id",
    "name",
    "garage_number",
    "inventory_number",
    "model_name",
    "start_expl_date",
    "end_expl_date",
    "is_active",
    "last_synced_at",
]
CarriageSort = Literal[
    "gtk_id",
    "name",
    "reg_number",
    "inventory_number",
    "model_name",
    "start_expl_date",
    "end_expl_date",
    "is_active",
    "state_duration_s",
    "last_synced_at",
]
TrainSort = Literal[
    "gtk_id", "number", "title", "begin_time", "end_time", "is_open", "last_synced_at"
]


@router.get("/status", response_model=GtkStatusRead)
async def get_gtk_status(_: GtkViewer, db: DatabaseSession) -> GtkStatusRead:
    return await service.get_status(db)


@router.get("/wagon-mileage", response_model=GtkWagonMileageList)
async def get_gtk_wagon_mileage(
    _: GtkViewer,
    db: DatabaseSession,
    asset_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
) -> GtkWagonMileageList:
    return await service.list_wagon_mileage(db, asset_id=asset_id, limit=limit)


@router.post("/sync", response_model=GtkSyncRunRead | None)
async def post_gtk_sync(_: GtkManager, db: DatabaseSession):
    return await service.sync_gtk(db)


@router.get("/match-report", response_model=None)
async def get_gtk_match_report(
    _: GtkViewer,
    db: DatabaseSession,
    kind: Literal["locomotive", "carriage"],
    format: Literal["json", "csv"] = "json",
):
    report = await service.get_match_report(db, kind)
    if format == "csv":
        return Response(
            content=service.match_report_csv(report),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="gtk-{kind}-match-report.csv"'
            },
        )
    return GtkMatchReport.model_validate(report)


@router.post("/links", response_model=GtkLinkBatchResponse)
async def post_gtk_links(
    payload: GtkLinkBatchRequest,
    user: GtkManager,
    __: AssetLinkManager,
    db: DatabaseSession,
) -> GtkLinkBatchResponse:
    return GtkLinkBatchResponse(
        updated=await service.save_links(db, payload, by=user.id)
    )


@router.delete("/links/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gtk_link(
    asset_id: UUID,
    _: GtkManager,
    __: AssetLinkManager,
    db: DatabaseSession,
) -> Response:
    await service.delete_link(db, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/locomotives", response_model=PaginatedResponse[GtkLocomotiveRead]
)
async def get_gtk_locomotives(
    _: GtkViewer,
    db: DatabaseSession,
    q: str | None = Query(default=None, max_length=200),
    is_active: bool | None = None,
    in_train: bool | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: LocomotiveSort = "gtk_id",
    sort_order: SortOrder = "asc",
) -> PaginatedResponse[GtkLocomotiveRead]:
    items, total = await service.list_locomotives(
        db,
        q=q,
        is_active=is_active,
        in_train=in_train,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[GtkLocomotiveRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/carriages", response_model=PaginatedResponse[GtkCarriageRead])
async def get_gtk_carriages(
    _: GtkViewer,
    db: DatabaseSession,
    q: str | None = Query(default=None, max_length=200),
    is_active: bool | None = None,
    in_train: bool | None = None,
    duplicate: bool | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: CarriageSort = "gtk_id",
    sort_order: SortOrder = "asc",
) -> PaginatedResponse[GtkCarriageRead]:
    items, total = await service.list_carriages(
        db,
        q=q,
        is_active=is_active,
        in_train=in_train,
        duplicate=duplicate,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[GtkCarriageRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.post("/carriages/create-assets", response_model=GtkCreateAssetsResponse)
async def post_create_gtk_carriage_assets(
    user: GtkManager,
    __: AssetLinkManager,
    db: DatabaseSession,
    payload: GtkCreateAssetRequest = Body(default=GtkCreateAssetRequest()),
) -> GtkCreateAssetsResponse:
    return await service.create_carriage_assets(
        db, dry_run=payload.dry_run, by=user.id
    )


@router.post(
    "/carriages/{gtk_id}/create-asset", response_model=GtkCreateAssetsResponse
)
async def post_create_gtk_carriage_asset(
    gtk_id: int,
    user: GtkManager,
    __: AssetLinkManager,
    db: DatabaseSession,
    payload: GtkCreateAssetRequest = Body(default=GtkCreateAssetRequest()),
) -> GtkCreateAssetsResponse:
    return await service.create_carriage_asset(
        db, gtk_id, dry_run=payload.dry_run, by=user.id
    )


@router.get("/trains", response_model=PaginatedResponse[GtkTrainRead])
async def get_gtk_trains(
    _: GtkViewer,
    db: DatabaseSession,
    q: str | None = Query(default=None, max_length=200),
    is_open: bool | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: TrainSort = "gtk_id",
    sort_order: SortOrder = "asc",
) -> PaginatedResponse[GtkTrainRead]:
    items, total = await service.list_trains(
        db,
        q=q,
        is_open=is_open,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[GtkTrainRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/trains/{gtk_id}", response_model=GtkTrainDetail)
async def get_gtk_train(
    gtk_id: int,
    _: GtkViewer,
    db: DatabaseSession,
) -> GtkTrainDetail:
    result = await service.get_train_detail(db, gtk_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="GTK train not found"
        )
    return GtkTrainDetail.model_validate(result)
