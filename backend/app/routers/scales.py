import hmac
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import today_local
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas import scales as schemas
from app.schemas import scales_insights as insight_schemas
from app.services import scales as service
from app.services import scales_insights as insights_service
from app.services import scales_trips as trips_service

router = APIRouter(prefix="/scales", tags=["scales"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission("scales.view"))]
Manager = Annotated[User, Depends(require_permission("scales.manage"))]
MAX_INGEST_BYTES = 4 * 1024 * 1024


async def require_ingest_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_ingest_token: Annotated[str | None, Header()] = None,
) -> None:
    configured = settings.scales_ingest_token
    expected = configured.get_secret_value() if configured is not None else ""
    candidates = [x_ingest_token.strip()] if x_ingest_token else []
    scheme, separator, value = (authorization or "").partition(" ")
    if separator and scheme.lower() == "bearer" and value.strip():
        candidates.append(value.strip())
    matched = False
    for candidate in candidates:
        matched = hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8")) or matched
    if not expected or not matched:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid scales ingest credentials", headers={"WWW-Authenticate": "Bearer"})
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_INGEST_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Scales batch exceeds 4 MB")


@router.post("/ingest", response_model=schemas.ScalesIngestResult, dependencies=[Depends(require_ingest_token)])
async def ingest_scales(payload: schemas.ScalesIngestIn, db: DatabaseSession) -> schemas.ScalesIngestResult:
    return await service.ingest(db, payload)


@router.get("/status", response_model=schemas.ScalesStatus)
async def read_status(user: Viewer, db: DatabaseSession) -> schemas.ScalesStatus:
    return await service.get_status(db)


@router.get("/trains", response_model=schemas.ScaleTrainPage)
async def read_trains(
    user: Viewer,
    db: DatabaseSession,
    post: Annotated[str | None, Query(max_length=10)] = None,
    match_status: Annotated[Literal["pending", "ok", "no_loco", "no_gtk_train", "excluded"] | None, Query()] = None,
    flag: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=40)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    sort_by: Annotated[str, Query(max_length=20)] = "started_at",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.ScaleTrainPage:
    return await service.list_trains(
        db, post=post, match_status=match_status, flag=flag, q=q, date_from=date_from, date_to=date_to,
        sort_by=sort_by, descending=sort_dir == "desc", limit=limit, offset=offset,
    )


@router.get("/unmatched", response_model=schemas.UnmatchedPage)
async def read_unmatched(
    user: Viewer,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.UnmatchedPage:
    return await service.list_unmatched(db, limit=limit, offset=offset)


@router.get("/summary", response_model=list[schemas.DaySummary])
async def read_summary(user: Viewer, db: DatabaseSession, days: Annotated[int, Query(ge=1, le=366)] = 30) -> list[schemas.DaySummary]:
    return await service.daily_summary(db, days)


@router.get("/assets/{asset_id}/work", response_model=schemas.AssetWorkRead)
async def read_asset_work(
    asset_id: UUID,
    user: Viewer,
    db: DatabaseSession,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> schemas.AssetWorkRead:
    end = date_to or today_local()
    start = date_from or end - timedelta(days=30)
    if start > end or (end - start).days > 800:
        raise HTTPException(status_code=422, detail="Invalid date range")
    return await service.asset_work(db, asset_id, start, end)


@router.get("/corrections", response_model=list[schemas.CorrectionRead])
async def read_corrections(user: Viewer, db: DatabaseSession) -> list[schemas.CorrectionRead]:
    return await service.list_corrections(db)


@router.post("/corrections", response_model=schemas.CorrectionRead, status_code=status.HTTP_201_CREATED)
async def create_correction(payload: schemas.CorrectionCreate, user: Manager, db: DatabaseSession) -> schemas.CorrectionRead:
    return await service.create_correction(db, user, payload)


@router.delete("/corrections/{correction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_correction(correction_id: UUID, user: Manager, db: DatabaseSession) -> None:
    await service.end_correction(db, correction_id)


@router.post("/rematch", status_code=status.HTTP_200_OK)
async def rematch_everything(user: Manager, db: DatabaseSession) -> dict[str, int]:
    """Recompute every derived column from the raw rows, GTK history and corrections (safe to repeat)."""
    return {"rematched": await service.rematch_all(db)}


# ── the wagon ledger: which wagon carried how much, when ─────────────────────────────────────────────────
@router.get("/wagon-trips", response_model=schemas.WagonTripPage)
async def read_wagon_trips(
    user: Viewer,
    db: DatabaseSession,
    asset_id: Annotated[UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=40)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    post: Annotated[str | None, Query(max_length=10)] = None,
    cargo_code: Annotated[int | None, Query()] = None,
    only_linked: Annotated[bool, Query()] = False,
    sort_by: Annotated[str, Query(max_length=20)] = "started_at",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.WagonTripPage:
    return await trips_service.wagon_trips(
        db, asset_id=asset_id, q=q, date_from=date_from, date_to=date_to, post=post, cargo_code=cargo_code, only_linked=only_linked,
        sort_by=sort_by, descending=sort_dir == "desc", limit=limit, offset=offset,
    )


@router.get("/wagon-trips/export.csv")
async def export_wagon_trips(
    user: Viewer,
    db: DatabaseSession,
    asset_id: Annotated[UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=40)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    post: Annotated[str | None, Query(max_length=10)] = None,
    cargo_code: Annotated[int | None, Query()] = None,
    only_linked: Annotated[bool, Query()] = False,
) -> Response:
    body = await trips_service.wagon_trips_csv(
        db, asset_id=asset_id, q=q, date_from=date_from, date_to=date_to, post=post, cargo_code=cargo_code, only_linked=only_linked
    )
    return Response(
        content=body.encode("utf-8"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="wagon_trips.csv"'},
    )


@router.get("/wagons", response_model=schemas.WagonTotalPage)
async def read_wagon_totals(
    user: Viewer,
    db: DatabaseSession,
    q: Annotated[str | None, Query(max_length=40)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    post: Annotated[str | None, Query(max_length=10)] = None,
    cargo_code: Annotated[int | None, Query()] = None,
    only_linked: Annotated[bool, Query()] = False,
    sort_by: Annotated[str, Query(max_length=20)] = "tonnes",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.WagonTotalPage:
    return await trips_service.wagon_totals(
        db, q=q, date_from=date_from, date_to=date_to, post=post, cargo_code=cargo_code, only_linked=only_linked,
        sort_by=sort_by, descending=sort_dir == "desc", limit=limit, offset=offset,
    )


# ── the command center: one request per screen ───────────────────────────────────────────────────────────
@router.get("/overview", response_model=insight_schemas.Overview)
async def read_overview(user: Viewer, db: DatabaseSession, days: Annotated[int, Query(ge=1, le=366)] = 30) -> insight_schemas.Overview:
    return await insights_service.overview(db, days)


@router.get("/trains/{train_id}", response_model=insight_schemas.TrainCard)
async def read_train_card(train_id: UUID, user: Viewer, db: DatabaseSession) -> insight_schemas.TrainCard:
    return await insights_service.train_card(db, train_id)


@router.get("/wagon-card", response_model=insight_schemas.WagonCard)
async def read_wagon_card(
    user: Viewer,
    db: DatabaseSession,
    asset_id: Annotated[UUID | None, Query()] = None,
    carriage_gtk_id: Annotated[int | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=366)] = 30,
) -> insight_schemas.WagonCard:
    return await insights_service.wagon_card(db, asset_id=asset_id, carriage_gtk_id=carriage_gtk_id, days=days)


@router.get("/loco-card/{asset_id}", response_model=insight_schemas.LocoCard)
async def read_loco_card(asset_id: UUID, user: Viewer, db: DatabaseSession, days: Annotated[int, Query(ge=1, le=366)] = 30) -> insight_schemas.LocoCard:
    return await insights_service.loco_card(db, asset_id, days)
