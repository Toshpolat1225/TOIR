from datetime import datetime, timezone
from decimal import Decimal
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
    without_org_unit: bool = False,
    master_section_id: UUID | None,
    q: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
    connection: str | None = None,
    mileage_min: Decimal | None = None,
    mileage_max: Decimal | None = None,
    wialon_min: Decimal | None = None,
    wialon_max: Decimal | None = None,
    suspect: bool = False,
) -> tuple[list[UnifiedAssetRead], int]:
    now = datetime.now(timezone.utc)
    # Forward only the extra filters that are set, so callers/tests of the base
    # filter set keep seeing exactly the same repository call.
    extra_filters = {
        key: value
        for key, value in {
            "connection": connection,
            "mileage_min": mileage_min,
            "mileage_max": mileage_max,
            "wialon_min": wialon_min,
            "wialon_max": wialon_max,
            "suspect": suspect or None,
        }.items()
        if value is not None
    }
    try:
        rows, total = await repository.list_unified_assets(
            db,
            source=source,
            asset_type=asset_type,
            status=asset_status,
            section_id=section_id,
            without_org_unit=without_org_unit,
            master_section_id=master_section_id,
            q=q,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            now=now,
            **extra_filters,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported sort field",
        ) from exc

    items: list[UnifiedAssetRead] = []
    if source == "gtk":
        for row in rows:
            items.append(
                UnifiedAssetRead(
                    source="gtk",
                    asset_id=None,
                    unit_id=None,
                    name=row["name"],
                    asset_type="wagon" if row["kind"] == "carriage" else "locomotive",
                    series=None,
                    inv_number=row["inventory_number"],
                    status=None,
                    section=None,
                    section_id=None,
                    mileage=None,
                    wialon_cnm=None,
                    wialon_cneh=None,
                    speed=None,
                    last_message_at=None,
                    is_online=False,
                    suspect_absolute=False,
                    gtk_id=row["gtk_id"],
                    gtk_kind=row["kind"],
                )
            )
        return items, total
    for row in rows:
        has_gtk = bool(row[5]) if len(row) > 5 else False
        if len(row) == 3:
            asset, unit, section = row
            asset_name = getattr(asset, "name", None)
            asset_series = getattr(asset, "series", None)
        else:
            asset, unit, section, asset_name, asset_series = row[:5]
        if asset is None:
            source_value = "wialon"
        elif unit is not None:
            source_value = "toir_wialon_gtk" if has_gtk else "both"
        else:
            source_value = "toir_gtk" if has_gtk else "toir"
        items.append(
            UnifiedAssetRead(
                source=source_value,
                asset_id=asset.id if asset is not None else None,
                unit_id=unit.unit_id if unit is not None else None,
                name=(asset_name if asset is not None else unit.name),
                asset_type=asset.asset_type if asset is not None else None,
                series=asset_series if asset is not None else None,
                inv_number=asset.inv_number if asset is not None else None,
                status=asset.status if asset is not None else None,
                section=section.name if section is not None else None,
                section_id=asset.section_id if asset is not None else None,
                org_unit_id=(
                    getattr(asset, "org_unit_id", None)
                    if asset is not None
                    else None
                ),
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
