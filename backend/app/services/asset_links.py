from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.repositories import asset_source_links as repository
from app.repositories import gtk as gtk_repository

AssetLinkSource = Literal["wialon", "gtk", "vesavoy", "onec"]
_MIRROR_FIELDS = {"wialon": "wialon_id", "gtk": "gtk_id"}


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="External source ID is already linked",
    )


async def _validate_asset_source(
    db: AsyncSession, asset_type: str, source: AssetLinkSource, external_id: str
) -> None:
    if source == "wialon":
        if asset_type not in {"locomotive", "diesel"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Wialon unit can only be linked to a locomotive or diesel asset",
            )
    elif source == "gtk":
        kind = await gtk_repository.gtk_kind(db, external_id)
        if kind is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="GTK record was not found",
            )
        if kind == "locomotive" and asset_type not in {"locomotive", "diesel"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="GTK locomotive needs a locomotive or diesel asset",
            )
        if kind == "carriage" and asset_type != "wagon":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="GTK carriage needs a wagon asset",
            )


async def validate_asset_type(
    db: AsyncSession,
    asset_type: str,
    source: AssetLinkSource,
    external_id: str,
) -> None:
    await _validate_asset_source(db, asset_type, source, external_id)


async def link(
    db: AsyncSession,
    asset_id: UUID,
    source: AssetLinkSource,
    external_id: str,
    by: UUID | None,
    *,
    external_name: str | None = None,
    method: Literal["manual", "migrated", "import"] = "manual",
) -> AssetSourceLink:
    external_id = external_id.strip()
    if not external_id or len(external_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="External ID must contain between 1 and 100 characters",
        )
    result = await db.execute(
        select(FixedAsset).where(FixedAsset.id == asset_id).with_for_update()
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    await _validate_asset_source(db, asset.asset_type, source, external_id)

    existing_external = await repository.find_active(db, source, external_id)
    if existing_external is not None and existing_external[1].id != asset_id:
        raise _conflict()

    current = await repository.get_active_for_update(db, asset_id, source)
    if current is not None and current.external_id == external_id:
        current.external_name = external_name or current.external_name
        if source in _MIRROR_FIELDS:
            setattr(asset, _MIRROR_FIELDS[source], external_id)
        return current

    now = datetime.now(timezone.utc)
    if current is not None:
        await repository.end(current, at=now)
    link_row = AssetSourceLink(
        asset_id=asset_id,
        source=source,
        external_id=external_id,
        external_name=external_name,
        status="active",
        link_method=method,
        linked_by=by,
        linked_at=now,
    )
    try:
        await repository.add(db, link_row)
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict() from exc
    if source in _MIRROR_FIELDS:
        setattr(asset, _MIRROR_FIELDS[source], external_id)
    return link_row


async def unlink(
    db: AsyncSession, asset_id: UUID, source: AssetLinkSource
) -> AssetSourceLink:
    asset_result = await db.execute(
        select(FixedAsset).where(FixedAsset.id == asset_id).with_for_update()
    )
    asset = asset_result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    current = await repository.get_active_for_update(db, asset_id, source)
    if current is None:
        raise HTTPException(status_code=404, detail="Active source link not found")
    await repository.end(current)
    if source in _MIRROR_FIELDS and getattr(asset, _MIRROR_FIELDS[source]) == current.external_id:
        setattr(asset, _MIRROR_FIELDS[source], None)
    return current


async def get_active(db: AsyncSession, asset_id: UUID) -> list[AssetSourceLink]:
    return await repository.get_active(db, asset_id)


async def find_asset(
    db: AsyncSession, source: AssetLinkSource, external_id: str
) -> FixedAsset | None:
    found = await repository.find_active(db, source, external_id)
    return found[1] if found is not None else None


async def list_for_asset(
    db: AsyncSession, asset_id: UUID, *, include_ended: bool
) -> list[AssetSourceLink]:
    return await repository.get_for_asset(
        db, asset_id, include_ended=include_ended
    )
