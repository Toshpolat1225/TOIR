from typing import Annotated, Literal
from uuid import UUID
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission, user_has_permission
from app.models.identity import User
from app.schemas.assets import (
    AssetStatus,
    AssetType,
    FixedAssetBulkOrgUnitUpdate,
    FixedAssetBulkOrgUnitUpdateRead,
    FixedAssetCreate,
    FixedAssetInventoryImportApply,
    FixedAssetInventoryImportApplyRead,
    FixedAssetInventoryImportPreview,
    FixedAssetInventoryImportRequest,
    FixedAssetRead,
    FixedAssetStats,
    FixedAssetUpdate,
    MileageHistoryList,
    MileageUpdate,
)
from app.schemas.asset_catalogs import AssetBehavior
from app.schemas.common import PaginatedResponse
from app.schemas.gtk import GtkFixedAssetSourceDetail
from app.schemas.asset_source_links import (
    AssetSourceLinkCreate,
    AssetSourceLinkRead,
    AssetSourceLinksRead,
)
from app.schemas.asset_models import AssetModelRead
from app.schemas.asset_data_import import (
    FixedAssetsPassportImportApplyRead,
    FixedAssetsPassportImportApplyRequest,
    FixedAssetsPassportImportPreview,
    FixedAssetsPassportImportRequest,
)
from app.services import assets as service
from app.services import asset_passport
from app.services import asset_inventory_import
from app.services import asset_passport_import
from app.services import asset_links as asset_links_service
from app.services import gtk as gtk_service
from app.services import unified_assets as unified_service
from app.schemas.wialon import UnifiedAssetRead

router = APIRouter(prefix="/fixed-assets", tags=["fixed assets"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(require_permission("assets.view"))]
AssetLinksViewer = Annotated[User, Depends(require_permission("asset_links.view"))]
AssetLinksManager = Annotated[User, Depends(require_permission("asset_links.manage"))]
AssetCreator = Annotated[User, Depends(require_permission("assets.create"))]
AssetUpdater = Annotated[User, Depends(require_permission("assets.update"))]
AssetDeleter = Annotated[User, Depends(require_permission("assets.delete"))]
SortOrder = Literal["asc", "desc"]


async def _commit_source_link(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="External source link conflicts with an existing active link",
        ) from exc


def _safe_csv_cell(value):
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return f"'{value}"
    return value


def _master_section(user: User) -> UUID | None:
    if user.role == "master" and user.section_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master user must be assigned to a section",
        )
    return user.section_id if user.role == "master" else None


@router.get("/stats", response_model=FixedAssetStats)
async def get_fixed_asset_stats(
    user: AuthenticatedUser, db: DatabaseSession,
    asset_type: AssetType | None = None,
    status_filter: Annotated[AssetStatus | None, Query(alias="status")] = None,
    status_behavior: AssetBehavior | None = None, section_id: UUID | None = None,
    depot: str | None = None, q: str | None = Query(default=None, max_length=200),
) -> FixedAssetStats:
    return await service.get_fixed_asset_stats(
        db, master_section_id=_master_section(user), asset_type=asset_type,
        asset_status=status_filter, status_behavior=status_behavior,
        section_id=section_id, depot=depot, q=q,
    )


@router.get("", response_model=PaginatedResponse[FixedAssetRead])
async def get_fixed_assets(
    user: AuthenticatedUser,
    db: DatabaseSession,
    asset_type: AssetType | None = None,
    status_filter: Annotated[
        AssetStatus | None, Query(alias="status")
    ] = None,
    status_behavior: AssetBehavior | None = None,
    section_id: UUID | None = None,
    depot: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_order: SortOrder = Query(default="desc"),
) -> PaginatedResponse[FixedAssetRead]:
    items, total = await service.list_fixed_assets(
        db,
        asset_type=asset_type,
        asset_status=status_filter,
        status_behavior=status_behavior,
        section_id=section_id,
        master_section_id=_master_section(user),
        depot=depot,
        q=q,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[FixedAssetRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/unified",
    response_model=PaginatedResponse[UnifiedAssetRead],
)
async def get_unified_fixed_assets(
    user: AuthenticatedUser,
    db: DatabaseSession,
    source: Literal["toir", "wialon", "both"] | None = None,
    asset_type: AssetType | None = None,
    status_filter: Annotated[
        AssetStatus | None, Query(alias="status")
    ] = None,
    section_id: UUID | None = None,
    without_org_unit: bool = False,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = "name",
    sort_order: SortOrder = "asc",
) -> PaginatedResponse[UnifiedAssetRead]:
    items, total = await unified_service.list_unified_assets(
        db,
        source=source,
        asset_type=asset_type,
        asset_status=status_filter,
        section_id=section_id,
        without_org_unit=without_org_unit,
        master_section_id=_master_section(user),
        q=q,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse[UnifiedAssetRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/models", response_model=PaginatedResponse[AssetModelRead])
async def get_asset_models(
    _: AuthenticatedUser,
    db: DatabaseSession,
    asset_type: AssetType | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AssetModelRead]:
    items, total = await asset_passport.list_models(
        db,
        asset_type=asset_type,
        q=q,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[AssetModelRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.post(
    "/bulk-org-unit",
    response_model=FixedAssetBulkOrgUnitUpdateRead,
)
async def post_bulk_org_unit_update(
    payload: FixedAssetBulkOrgUnitUpdate,
    user: AssetUpdater,
    db: DatabaseSession,
) -> FixedAssetBulkOrgUnitUpdateRead:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    updated = await service.bulk_update_org_unit(db, payload, by=user.id)
    return FixedAssetBulkOrgUnitUpdateRead(updated=updated)


def _require_asset_operator(user: User) -> None:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


@router.post(
    "/inv-import/preview",
    response_model=FixedAssetInventoryImportPreview,
)
async def preview_inventory_import(
    payload: FixedAssetInventoryImportRequest,
    user: AssetUpdater,
    db: DatabaseSession,
) -> FixedAssetInventoryImportPreview:
    _require_asset_operator(user)
    return await asset_inventory_import.preview_inventory_import(db, payload)


@router.post(
    "/inv-import/apply",
    response_model=FixedAssetInventoryImportApplyRead,
)
async def apply_inventory_import(
    payload: FixedAssetInventoryImportApply,
    user: AssetUpdater,
    db: DatabaseSession,
) -> FixedAssetInventoryImportApplyRead:
    _require_asset_operator(user)
    updated = await asset_inventory_import.apply_inventory_import(db, payload)
    return FixedAssetInventoryImportApplyRead(updated=updated)


@router.post(
    "/passport-import/preview",
    response_model=FixedAssetsPassportImportPreview,
)
async def preview_passport_json_import(
    payload: FixedAssetsPassportImportRequest,
    user: AssetUpdater,
    db: DatabaseSession,
) -> FixedAssetsPassportImportPreview:
    _require_asset_operator(user)
    return await asset_passport_import.preview(db, payload)


@router.post(
    "/passport-import/apply",
    response_model=FixedAssetsPassportImportApplyRead,
)
async def apply_passport_json_import(
    payload: FixedAssetsPassportImportApplyRequest,
    user: AssetUpdater,
    db: DatabaseSession,
) -> FixedAssetsPassportImportApplyRead:
    _require_asset_operator(user)
    return await asset_passport_import.apply(db, payload)


@router.get("/{asset_id}/mileage-history", response_model=MileageHistoryList)
async def get_asset_mileage_history(
    asset_id: UUID,
    user: AuthenticatedUser,
    db: DatabaseSession,
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=100, ge=1, le=1000),
) -> MileageHistoryList:
    return await service.get_mileage_history(
        db,
        asset_id,
        days=days,
        limit=limit,
        master_section_id=_master_section(user),
    )


@router.post(
    "/{asset_id}/mileage",
    response_model=FixedAssetRead,
)
async def post_asset_mileage(
    asset_id: UUID, payload: MileageUpdate, _: AssetUpdater, db: DatabaseSession
) -> FixedAssetRead:
    return await service.set_fixed_asset_mileage(db, asset_id, payload)


@router.get("/{asset_id}/gtk", response_model=GtkFixedAssetSourceDetail)
async def get_fixed_asset_gtk_detail(
    asset_id: UUID, user: AuthenticatedUser, db: DatabaseSession
) -> GtkFixedAssetSourceDetail:
    result = await gtk_service.get_fixed_asset_gtk_detail(
        db,
        asset_id,
        master_section_id=_master_section(user),
    )
    return GtkFixedAssetSourceDetail.model_validate(result)


@router.get("/{asset_id}/links", response_model=AssetSourceLinksRead)
async def get_fixed_asset_links(
    asset_id: UUID,
    _: AssetLinksViewer,
    db: DatabaseSession,
    include_ended: bool = Query(default=False),
) -> AssetSourceLinksRead:
    await service.get_fixed_asset(db, asset_id, master_section_id=None)
    items = await asset_links_service.list_for_asset(
        db, asset_id, include_ended=include_ended
    )
    return AssetSourceLinksRead(asset_id=asset_id, items=items)


@router.post(
    "/{asset_id}/links",
    response_model=AssetSourceLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_fixed_asset_link(
    asset_id: UUID,
    payload: AssetSourceLinkCreate,
    user: AssetLinksManager,
    db: DatabaseSession,
) -> AssetSourceLinkRead:
    await service.get_fixed_asset(db, asset_id, master_section_id=None)
    item = await asset_links_service.link(
        db,
        asset_id,
        payload.source,
        payload.external_id,
        user.id,
        external_name=payload.external_name,
    )
    await _commit_source_link(db)
    await db.refresh(item)
    return AssetSourceLinkRead.model_validate(item)


@router.delete(
    "/{asset_id}/links/{source}",
    response_model=AssetSourceLinkRead,
)
async def delete_fixed_asset_link(
    asset_id: UUID,
    source: Literal["wialon", "gtk", "vesavoy", "onec"],
    _: AssetLinksManager,
    db: DatabaseSession,
) -> AssetSourceLinkRead:
    await service.get_fixed_asset(db, asset_id, master_section_id=None)
    item = await asset_links_service.unlink(db, asset_id, source)
    await _commit_source_link(db)
    await db.refresh(item)
    return AssetSourceLinkRead.model_validate(item)


@router.get("/passport-report")
async def get_fixed_asset_passport_report(
    user: AssetCreator,
    db: DatabaseSession,
    format: Literal["json", "csv"] = Query(default="json"),
):
    if user.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    report = await service.get_fixed_asset_passport_report(db)
    if format == "json":
        return report

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "category",
            "asset_id",
            "inv_number",
            "asset_type",
            "depot",
            "org_unit_id",
            "number_normalized",
            "details",
        ]
    )
    for row in report["depot_matches"]:
        writer.writerow(
            _safe_csv_cell(value)
            for value in [
                "depot_match",
                row["asset_id"],
                row["inv_number"],
                "",
                row["depot"],
                row["org_unit_id"] or row["candidate_sections"][0]["id"],
                "",
                "exact section name",
            ]
        )
    for row in report["depot_unmatched"]:
        writer.writerow(
            _safe_csv_cell(value)
            for value in [
                row["status"],
                row["asset_id"],
                row["inv_number"],
                "",
                row["depot"],
                row["org_unit_id"],
                "",
                "; ".join(section["name"] for section in row["candidate_sections"]),
            ]
        )
    for group in report["duplicate_numbers"]:
        for asset in group["assets"]:
            writer.writerow(
                _safe_csv_cell(value)
                for value in [
                    "duplicate_number",
                    asset["asset_id"],
                    asset["inv_number"],
                    group["asset_type"],
                    "",
                    "",
                    group["number_normalized"],
                    str(group["model_id"]),
                ]
            )
    for row in report["invalid_values"]:
        writer.writerow(
            _safe_csv_cell(value)
            for value in [
                "invalid_passport",
                row["asset_id"],
                row["inv_number"],
                "",
                "",
                "",
                "",
                "; ".join(row["issues"]),
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="asset-passport-report.csv"'},
    )


@router.get("/{asset_id}", response_model=FixedAssetRead)
async def get_fixed_asset(
    asset_id: UUID, user: AuthenticatedUser, db: DatabaseSession
) -> FixedAssetRead:
    return await service.get_fixed_asset(
        db, asset_id, master_section_id=_master_section(user)
    )


@router.post(
    "",
    response_model=FixedAssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_fixed_asset(
    payload: FixedAssetCreate, user: AssetCreator, db: DatabaseSession
) -> FixedAssetRead:
    if (payload.gtk_id is not None or payload.wialon_id is not None) and not await user_has_permission(
        db, user, "asset_links.manage"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return await service.create_fixed_asset(db, payload, by=user.id)


@router.patch("/{asset_id}", response_model=FixedAssetRead)
async def patch_fixed_asset(
    asset_id: UUID,
    payload: FixedAssetUpdate,
    user: AssetUpdater,
    db: DatabaseSession,
) -> FixedAssetRead:
    if {"gtk_id", "wialon_id"} & payload.model_fields_set and not await user_has_permission(
        db, user, "asset_links.manage"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return await service.update_fixed_asset(db, asset_id, payload, by=user.id)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_fixed_asset(
    asset_id: UUID, _: AssetDeleter, db: DatabaseSession
) -> Response:
    await service.delete_fixed_asset(db, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
