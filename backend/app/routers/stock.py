"""1C stock import (admin), supplier lead times and purchase orders (admin/operator write, others read)."""
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.common import PaginatedResponse
from app.schemas.stock import PurchaseOrderCreate, PurchaseOrderRead, PurchaseOrderWrite, SupplierTermRead, SupplierTermWrite
from app.services import stock as service
from app.services import stock_import

router = APIRouter(tags=["stock"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission("inventory.view"))]
Updater = Annotated[User, Depends(require_permission("inventory.update"))]
Importer = Annotated[User, Depends(require_permission("inventory.create"))]


async def _admin_only(user: Importer) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an administrator can import 1C files")
    return user


Admin = Annotated[User, Depends(_admin_only)]


@router.post("/stock/import", response_model=dict[str, Any])
async def import_stock(
    user: Admin,
    db: DatabaseSession,
    file: Annotated[UploadFile, File()],
    apply: bool = False,
    as_of: date | None = None,
    kind: Literal["stock", "orders", "lead_times"] | None = None,
) -> dict[str, Any]:
    """Dry run by default (`apply=false` reports what would be written). `file` is .xlsx or .csv, see docs/PARTS_ANALYTICS_API.md."""
    content = await file.read(stock_import.MAX_FILE_BYTES + 1)
    try:
        return await stock_import.import_file(db, content, file.filename or "", apply=apply, as_of=as_of, kind=kind)
    except stock_import.ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/supplier-terms", response_model=PaginatedResponse[SupplierTermRead])
async def list_terms(user: Viewer, db: DatabaseSession, nomenclature_id: UUID | None = None, limit: int = Query(default=50, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
    items, total = await service.list_terms(db, user, nomenclature_id=nomenclature_id, limit=limit, offset=offset)
    return PaginatedResponse(items=[SupplierTermRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.put("/supplier-terms/{nomenclature_id}", response_model=SupplierTermRead)
async def put_term(nomenclature_id: UUID, payload: SupplierTermWrite, user: Updater, db: DatabaseSession):
    return SupplierTermRead.model_validate(await service.put_term(db, nomenclature_id, payload))


@router.get("/purchase-orders", response_model=PaginatedResponse[PurchaseOrderRead])
async def list_orders(
    user: Viewer,
    db: DatabaseSession,
    nomenclature_id: UUID | None = None,
    status_filter: Literal["ordered", "in_transit", "partial", "received", "cancelled"] | None = Query(default=None, alias="status"),
    open_only: bool = False,
    sort_by: str = Query(default="expected_on", max_length=30),
    sort_dir: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    items, total = await service.list_orders(db, user, nomenclature_id=nomenclature_id, status=status_filter, open_only=open_only, sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset)
    return PaginatedResponse(items=[PurchaseOrderRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.post("/purchase-orders", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(payload: PurchaseOrderCreate, user: Updater, db: DatabaseSession):
    return PurchaseOrderRead.model_validate(await service.create_order(db, payload))


@router.put("/purchase-orders/{order_id}", response_model=PurchaseOrderRead)
async def put_order(order_id: UUID, payload: PurchaseOrderWrite, user: Updater, db: DatabaseSession):
    return PurchaseOrderRead.model_validate(await service.put_order(db, order_id, payload))
