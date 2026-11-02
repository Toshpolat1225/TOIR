from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import unified_assets as repository
from app.schemas.wialon import UnifiedAssetRead
from app.services.wialon import is_wialon_unit_online


async def list_unified_assets(
    db: AsyncSession,
    *,
    source: str | None,
    asset_type: str | None,
    asset_status: str | None,
    section_id: UUID | None,
    master_section_id: UUID | None,
    q: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[UnifiedAssetRead], int]:
    now = datetime.now(timezone.utc)
    try:
        rows, total = await repository.list_unified_assets(
            db,
            source=source,
            asset_type=asset_type,
            status=asset_status,
            section_id=section_id,
            master_section_id=master_section_id,
            q=q,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            now=now,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported sort field",
        ) from exc

    items: list[UnifiedAssetRead] = []
    for asset, unit, section in rows:
        source_value = (
            "both" if asset is not None and unit is not None
            else "toir" if asset is not None
            else "wialon"
        )
        items.append(
            UnifiedAssetRead(
                source=source_value,
                asset_id=asset.id if asset is not None else None,
                unit_id=unit.unit_id if unit is not None else None,
                name=asset.name if asset is not None else unit.name,
                asset_type=asset.asset_type if asset is not None else None,
                series=asset.series if asset is not None else None,
                inv_number=asset.inv_number if asset is not None else None,
                status=asset.status if asset is not None else None,
                section=section.name if section is not None else None,
                section_id=asset.section_id if asset is not None else None,
                mileage=asset.mileage if asset is not None else None,
                wialon_cnm=unit.cnm if unit is not None else None,
                wialon_cneh=unit.cneh if unit is not None else None,
                speed=unit.speed if unit is not None else None,
                last_message_at=unit.last_message_at if unit is not None else None,
                is_online=(
                    is_wialon_unit_online(unit.last_message_at, now=now)
                    if unit is not None
                    else False
                ),
                suspect_absolute=(
                    unit.suspect_absolute if unit is not None else False
                ),
            )
        )
    return items, total
