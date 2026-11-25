"""Supplier terms and purchase orders (small read/write layer). A master sees only parts his section has used (issued TMC documents)."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.inventory import Nomenclature
from app.models.stock import PurchaseOrder, SupplierTerm
from app.models.tmc import TmcDocument, TmcDocumentItem
from app.schemas.stock import PurchaseOrderCreate, PurchaseOrderWrite, SupplierTermWrite

ORDER_SORT = {"expected_on": PurchaseOrder.expected_on, "ordered_on": PurchaseOrder.ordered_on, "status": PurchaseOrder.status, "created_at": PurchaseOrder.created_at}


def _master_filter(stmt: Select, user: User, nomenclature_col) -> Select:
    if user.role != "master":
        return stmt
    if user.section_id is None:
        raise HTTPException(status_code=403, detail="Master user must be assigned to a section")
    used = exists().where(TmcDocumentItem.nomenclature_id == nomenclature_col, TmcDocumentItem.document_id == TmcDocument.id, TmcDocument.section_id == user.section_id)
    return stmt.where(used)


async def _require_nomenclature(db: AsyncSession, nomenclature_id: UUID) -> Nomenclature:
    row = await db.get(Nomenclature, nomenclature_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Nomenclature not found")
    return row


async def list_terms(db: AsyncSession, user: User, *, nomenclature_id: UUID | None, limit: int, offset: int) -> tuple[list[dict], int]:
    base = select(SupplierTerm, Nomenclature.name).join(Nomenclature, Nomenclature.id == SupplierTerm.nomenclature_id)
    if nomenclature_id:
        base = base.where(SupplierTerm.nomenclature_id == nomenclature_id)
    base = _master_filter(base, user, SupplierTerm.nomenclature_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(Nomenclature.name, SupplierTerm.id).limit(limit).offset(offset))).all()
    return [{**_cols(t), "nomenclature_name": name} for t, name in rows], total


def _cols(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


async def put_term(db: AsyncSession, nomenclature_id: UUID, payload: SupplierTermWrite) -> dict:
    nom = await _require_nomenclature(db, nomenclature_id)
    term = (await db.execute(select(SupplierTerm).where(SupplierTerm.nomenclature_id == nomenclature_id))).scalar_one_or_none()
    if term is None:
        term = SupplierTerm(nomenclature_id=nomenclature_id, **payload.model_dump())
        db.add(term)
    else:
        for k, v in payload.model_dump().items():
            setattr(term, k, v)
        term.updated_at = func.now()
    await db.commit()
    await db.refresh(term)
    return {**_cols(term), "nomenclature_name": nom.name}


async def list_orders(db: AsyncSession, user: User, *, nomenclature_id: UUID | None, status: str | None, open_only: bool, sort_by: str, sort_dir: str, limit: int, offset: int) -> tuple[list[dict], int]:
    if sort_by not in ORDER_SORT:
        raise HTTPException(status_code=422, detail="Unsupported sort_by")
    base = select(PurchaseOrder, Nomenclature.name).join(Nomenclature, Nomenclature.id == PurchaseOrder.nomenclature_id)
    if nomenclature_id:
        base = base.where(PurchaseOrder.nomenclature_id == nomenclature_id)
    if status:
        base = base.where(PurchaseOrder.status == status)
    if open_only:
        base = base.where(PurchaseOrder.status.in_(("ordered", "in_transit", "partial")))
    base = _master_filter(base, user, PurchaseOrder.nomenclature_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    col = ORDER_SORT[sort_by]
    order = (col.desc() if sort_dir == "desc" else col.asc()).nulls_last()
    rows = (await db.execute(base.order_by(order, PurchaseOrder.id).limit(limit).offset(offset))).all()
    return [{**_cols(o), "nomenclature_name": name} for o, name in rows], total


def _check_order(payload: PurchaseOrderWrite) -> None:
    if payload.ordered_on and payload.expected_on and payload.expected_on < payload.ordered_on:
        raise HTTPException(status_code=422, detail="expected_on must not be before ordered_on")
    if payload.qty_received > payload.qty:
        raise HTTPException(status_code=422, detail="qty_received must not exceed qty")


async def create_order(db: AsyncSession, payload: PurchaseOrderCreate) -> dict:
    nom = await _require_nomenclature(db, payload.nomenclature_id)
    _check_order(payload)
    order = PurchaseOrder(**payload.model_dump())
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return {**_cols(order), "nomenclature_name": nom.name}


async def put_order(db: AsyncSession, order_id: UUID, payload: PurchaseOrderWrite) -> dict:
    order = await db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    _check_order(payload)
    for k, v in payload.model_dump().items():
        setattr(order, k, v)
    await db.commit()
    await db.refresh(order)
    nom = await db.get(Nomenclature, order.nomenclature_id)
    return {**_cols(order), "nomenclature_name": nom.name if nom else None}
