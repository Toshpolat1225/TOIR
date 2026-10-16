from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import FixedAsset
from app.models.maintenance import WorkType
from app.models.organization import Section
from app.models.tmc import TmcDocument, TmcDocumentItem
from app.models.work_orders import WorkOrder


async def list_documents(
    db: AsyncSession,
    *,
    section_id: UUID | None,
    department_id: UUID | None,
    status_filter: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    filters = []
    if section_id is not None:
        filters.append(TmcDocument.section_id == section_id)
    if department_id is not None:
        filters.append(
            TmcDocument.section_id.in_(
                select(Section.id).where(Section.department_id == department_id)
            )
        )
    if status_filter is not None:
        filters.append(TmcDocument.status == status_filter)

    total = (
        await db.execute(
            select(func.count()).select_from(TmcDocument).where(*filters)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(
                TmcDocument,
                WorkOrder.number.label("work_order_number"),
                FixedAsset.name.label("loco"),
                FixedAsset.depot.label("depot"),
                WorkType.name.label("work_type"),
                Section.name.label("section_name"),
            )
            .outerjoin(WorkOrder, WorkOrder.id == TmcDocument.work_order_id)
            .outerjoin(FixedAsset, FixedAsset.id == WorkOrder.fixed_asset_id)
            .outerjoin(WorkType, WorkType.id == TmcDocument.work_type_id)
            .outerjoin(Section, Section.id == TmcDocument.section_id)
            .where(*filters)
            .order_by(TmcDocument.created_at.desc(), TmcDocument.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    document_ids = [document.id for document, *_ in rows]
    item_rows = []
    if document_ids:
        item_rows = (
            await db.execute(
                select(TmcDocumentItem)
                .where(TmcDocumentItem.document_id.in_(document_ids))
                .order_by(TmcDocumentItem.sort_order, TmcDocumentItem.id)
            )
        ).scalars().all()
    items_by_document: dict[UUID, list[TmcDocumentItem]] = {}
    for item in item_rows:
        items_by_document.setdefault(item.document_id, []).append(item)

    result = []
    for document, work_order_number, loco, depot, work_type, section_name in rows:
        result.append(
            {
                "id": document.id,
                "doc_no": document.doc_no,
                "doc_date": document.doc_date,
                "work_order_id": document.work_order_id,
                "work_order_number": work_order_number,
                "section_id": document.section_id,
                "section_name": section_name,
                "work_type_id": document.work_type_id,
                "loco": loco,
                "work_type": work_type,
                "depot": depot,
                "warehouse": document.warehouse,
                "issued_by": document.issued_by,
                "accepted_by": document.accepted_by,
                "chief": document.chief,
                "status": document.status,
                "created_at": document.created_at,
                "items": [
                    {
                        "id": item.id,
                        "nomenclature_id": item.nomenclature_id,
                        "name": item.name,
                        "inv_no": item.inv_no,
                        "unit": item.unit,
                        "qty": item.qty,
                        "price": item.price,
                        "note": item.note,
                        "sort_order": item.sort_order,
                    }
                    for item in items_by_document.get(document.id, [])
                ],
            }
        )
    return result, total
