from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.inventory import Nomenclature, NomenclatureNorm
from app.repositories import nomenclature as repository
from app.schemas.nomenclature import (
    NomenclatureCreate,
    NomenclatureNormCreate,
    NomenclatureNormRead,
    NomenclatureNormUpdate,
    NomenclatureRead,
    NomenclatureUpdate,
)


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )


def _unsupported_sort() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Unsupported sort field",
    )


async def _commit_or_conflict(db: AsyncSession, detail: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc


def _nomenclature_read(row: Nomenclature, department_name: str) -> NomenclatureRead:
    return NomenclatureRead(
        id=row.id,
        department_id=row.department_id,
        department_name=department_name,
        name=row.name,
        code=row.code,
        unit=row.unit,
        extra=row.extra,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _norm_read(
    row: NomenclatureNorm,
    nomenclature_name: str,
    nomenclature_code: str | None,
    nomenclature_unit: str,
    work_type_code: str,
) -> NomenclatureNormRead:
    return NomenclatureNormRead(
        id=row.id,
        nomenclature_id=row.nomenclature_id,
        department_id=row.department_id,
        work_type_id=row.work_type_id,
        standard_quantity=row.standard_quantity,
        avg_price=row.avg_price,
        min_quantity=row.min_quantity,
        max_quantity=row.max_quantity,
        nomenclature_name=nomenclature_name,
        nomenclature_code=nomenclature_code,
        nomenclature_unit=nomenclature_unit,
        work_type_code=work_type_code,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_nomenclature(
    db: AsyncSession,
    *,
    department_id: UUID | None,
    q: str | None,
    master_only: bool,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[NomenclatureRead], int]:
    try:
        rows, total = await repository.list_nomenclature(
            db,
            department_id=department_id,
            q=q,
            master_only=master_only,
            master_section_id=master_section_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc
    return [_nomenclature_read(row, department_name) for row, department_name in rows], total


async def get_nomenclature(
    db: AsyncSession,
    nomenclature_id: UUID,
    *,
    master_only: bool,
    master_section_id: UUID | None,
) -> NomenclatureRead:
    record = await repository.get_nomenclature_read(
        db,
        nomenclature_id,
        master_only=master_only,
        master_section_id=master_section_id,
    )
    if record is None:
        raise _not_found("Nomenclature")
    row, department_name = record
    return _nomenclature_read(row, department_name)


async def create_nomenclature(
    db: AsyncSession, payload: NomenclatureCreate
) -> NomenclatureRead:
    row = Nomenclature(**payload.model_dump())
    db.add(row)
    await _commit_or_conflict(
        db,
        "Nomenclature with this name already exists in the department, or the department does not exist",
    )
    await db.refresh(row)
    return await get_nomenclature(
        db, row.id, master_only=False, master_section_id=None
    )


async def update_nomenclature(
    db: AsyncSession, nomenclature_id: UUID, payload: NomenclatureUpdate
) -> NomenclatureRead:
    row = await repository.get_nomenclature(db, nomenclature_id)
    if row is None:
        raise _not_found("Nomenclature")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field_name, value)
    await _commit_or_conflict(
        db,
        "Nomenclature with this name already exists in the department, or the department does not exist",
    )
    await db.refresh(row)
    return await get_nomenclature(
        db, row.id, master_only=False, master_section_id=None
    )


async def delete_nomenclature(db: AsyncSession, nomenclature_id: UUID) -> None:
    row = await repository.get_nomenclature(db, nomenclature_id)
    if row is None:
        raise _not_found("Nomenclature")
    if await repository.count_work_order_items(db, nomenclature_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete nomenclature: it is used by a work order",
        )
    await db.delete(row)
    await _commit_or_conflict(
        db,
        "Cannot delete nomenclature because it is referenced by existing records",
    )


async def list_norms(
    db: AsyncSession,
    *,
    department_id: UUID | None,
    work_type_id: UUID | None,
    nomenclature_id: UUID | None,
    master_only: bool,
    master_section_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[NomenclatureNormRead], int]:
    try:
        rows, total = await repository.list_norms(
            db,
            department_id=department_id,
            work_type_id=work_type_id,
            nomenclature_id=nomenclature_id,
            master_only=master_only,
            master_section_id=master_section_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise _unsupported_sort() from exc
    return [
        _norm_read(
            row,
            nomenclature_name,
            nomenclature_code,
            nomenclature_unit,
            work_type_code,
        )
        for row, nomenclature_name, nomenclature_code, nomenclature_unit, work_type_code in rows
    ], total


async def get_norm(
    db: AsyncSession,
    norm_id: UUID,
    *,
    master_only: bool,
    master_section_id: UUID | None,
) -> NomenclatureNormRead:
    record = await repository.get_norm_read(
        db,
        norm_id,
        master_only=master_only,
        master_section_id=master_section_id,
    )
    if record is None:
        raise _not_found("Nomenclature norm")
    row, nomenclature_name, nomenclature_code, nomenclature_unit, work_type_code = record
    return _norm_read(
        row,
        nomenclature_name,
        nomenclature_code,
        nomenclature_unit,
        work_type_code,
    )


def _validate_norm_range(
    *,
    minimum: Decimal | None,
    maximum: Decimal | None,
) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_quantity cannot exceed max_quantity",
        )


async def create_norm(
    db: AsyncSession, payload: NomenclatureNormCreate
) -> NomenclatureNormRead:
    row = NomenclatureNorm(**payload.model_dump())
    db.add(row)
    await _commit_or_conflict(
        db,
        "Norm already exists for this nomenclature, department and work type, or a referenced record does not exist",
    )
    await db.refresh(row)
    return await get_norm(db, row.id, master_only=False, master_section_id=None)


async def update_norm(
    db: AsyncSession, norm_id: UUID, payload: NomenclatureNormUpdate
) -> NomenclatureNormRead:
    row = await repository.get_norm(db, norm_id)
    if row is None:
        raise _not_found("Nomenclature norm")
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
    _validate_norm_range(
        minimum=changes.get("min_quantity", row.min_quantity),
        maximum=changes.get("max_quantity", row.max_quantity),
    )
    for field_name, value in changes.items():
        setattr(row, field_name, value)
    await _commit_or_conflict(
        db,
        "Norm already exists for this nomenclature, department and work type, or a referenced record does not exist",
    )
    await db.refresh(row)
    return await get_norm(db, row.id, master_only=False, master_section_id=None)


async def delete_norm(db: AsyncSession, norm_id: UUID) -> None:
    row = await repository.get_norm(db, norm_id)
    if row is None:
        raise _not_found("Nomenclature norm")
    await db.delete(row)
    await _commit_or_conflict(
        db,
        "Cannot delete nomenclature norm because it is referenced by existing records",
    )
