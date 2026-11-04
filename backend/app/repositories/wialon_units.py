from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.wialon_client import WialonUnit
from app.models.assets import FixedAsset
from app.models.asset_source_links import AssetSourceLink
from app.models.organization import Section
from app.models.wialon_counters import WialonCounterState, WialonRejectedReading
from app.models.wialon_units import WialonUnitRecord
from app.services.wialon_quality import suspect_absolute

UNIT_SORT_FIELDS = frozenset(
    {
        "unit_id",
        "name",
        "cnm",
        "cneh",
        "speed",
        "last_message_at",
        "first_seen_at",
        "last_synced_at",
    }
)


def build_upsert_statement(
    units: list[WialonUnit], *, synced_at: datetime
):
    values = [
        {
            "unit_id": unit.unit_id,
            "name": unit.name,
            "cnm": unit.mileage,
            "cneh": unit.engine_hours,
            "calc_flags": unit.calc_flags,
            "speed": unit.speed,
            "last_message_at": unit.last_message_at,
            "suspect_absolute": suspect_absolute(unit.mileage, unit.engine_hours),
            "last_synced_at": synced_at,
            "updated_at": synced_at,
        }
        for unit in units
    ]
    statement = insert(WialonUnitRecord).values(values)
    return statement.on_conflict_do_update(
        index_elements=[WialonUnitRecord.unit_id],
        set_={
            "name": statement.excluded.name,
            "cnm": statement.excluded.cnm,
            "cneh": statement.excluded.cneh,
            "calc_flags": statement.excluded.calc_flags,
            "speed": statement.excluded.speed,
            "last_message_at": statement.excluded.last_message_at,
            "suspect_absolute": statement.excluded.suspect_absolute,
            "last_synced_at": statement.excluded.last_synced_at,
            "updated_at": statement.excluded.updated_at,
        },
    )


async def upsert_units(
    db: AsyncSession, units: list[WialonUnit], *, synced_at: datetime
) -> None:
    if not units:
        return
    await db.execute(build_upsert_statement(units, synced_at=synced_at))
    await db.flush()


def _unit_filters(
    *,
    linked: bool | None,
    q: str | None,
    online: bool | None,
    suspect: bool | None,
    stale: bool | None,
    master_section_id,
    now: datetime,
) -> list[Any]:
    filters: list[Any] = []
    if linked is True:
        filters.append(FixedAsset.id.is_not(None))
    elif linked is False:
        filters.append(FixedAsset.id.is_(None))
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                WialonUnitRecord.name.ilike(pattern),
                WialonUnitRecord.unit_id.ilike(pattern),
            )
        )
    online_clause = (
        WialonUnitRecord.last_message_at.is_not(None)
        & (WialonUnitRecord.last_message_at >= now - timedelta(minutes=15))
    )
    if online is True:
        filters.append(online_clause)
    elif online is False:
        filters.append(~online_clause)
    if suspect is not None:
        filters.append(WialonUnitRecord.suspect_absolute.is_(suspect))
    stale_clause = (
        WialonUnitRecord.last_message_at.is_(None)
        | (WialonUnitRecord.last_message_at < now - timedelta(hours=24))
    )
    if stale is True:
        filters.append(stale_clause)
    elif stale is False:
        filters.append(~stale_clause)
    if master_section_id is not None:
        filters.append(FixedAsset.section_id == master_section_id)
    return filters


def _active_asset_links():
    return and_(
        AssetSourceLink.source == "wialon",
        AssetSourceLink.status == "active",
    )


def _unit_rows_query():
    rejected_count = (
        select(func.count(WialonRejectedReading.id))
        .where(WialonRejectedReading.asset_id == FixedAsset.id)
        .correlate(FixedAsset)
        .scalar_subquery()
    )
    return (
        select(
            WialonUnitRecord,
            FixedAsset,
            WialonCounterState,
            rejected_count.label("rejected_count"),
        )
        .select_from(
            WialonUnitRecord.__table__
            .outerjoin(
                AssetSourceLink.__table__,
                and_(
                    AssetSourceLink.external_id == WialonUnitRecord.unit_id,
                    _active_asset_links(),
                ),
            )
            .outerjoin(FixedAsset.__table__, FixedAsset.id == AssetSourceLink.asset_id)
        )
        .outerjoin(WialonCounterState, WialonCounterState.asset_id == FixedAsset.id)
    )


async def list_units(
    db: AsyncSession,
    *,
    linked: bool | None,
    q: str | None,
    online: bool | None,
    suspect: bool | None,
    stale: bool | None,
    master_section_id,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
    now: datetime,
):
    if sort_by not in UNIT_SORT_FIELDS:
        raise ValueError("Unsupported sort field")
    filters = _unit_filters(
        linked=linked,
        q=q,
        online=online,
        suspect=suspect,
        stale=stale,
        master_section_id=master_section_id,
        now=now,
    )
    count_query = (
        select(func.count())
        .select_from(WialonUnitRecord)
        .outerjoin(
            AssetSourceLink,
            and_(
                AssetSourceLink.external_id == WialonUnitRecord.unit_id,
                _active_asset_links(),
            ),
        )
        .outerjoin(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
    )
    rows_query = _unit_rows_query()
    if filters:
        count_query = count_query.where(*filters)
        rows_query = rows_query.where(*filters)
    total = (await db.execute(count_query)).scalar_one()
    column = getattr(WialonUnitRecord, sort_by)
    ordering = column.desc() if sort_order == "desc" else column.asc()
    result = await db.execute(
        rows_query.order_by(ordering, WialonUnitRecord.unit_id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all()), total


async def get_unit(
    db: AsyncSession, unit_id: str, *, master_section_id
):
    query = _unit_rows_query().where(WialonUnitRecord.unit_id == unit_id)
    if master_section_id is not None:
        query = query.where(FixedAsset.section_id == master_section_id)
    result = await db.execute(query)
    return result.one_or_none()


async def list_rejected_readings(
    db: AsyncSession, asset_id, *, limit: int = 20
) -> list[WialonRejectedReading]:
    result = await db.execute(
        select(WialonRejectedReading)
        .where(WialonRejectedReading.asset_id == asset_id)
        .order_by(
            WialonRejectedReading.created_at.desc(),
            WialonRejectedReading.id.desc(),
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_unlinked_assets(
    db: AsyncSession, *, master_section_id
) -> list[FixedAsset]:
    has_link = exists(
        select(AssetSourceLink.id).where(
            AssetSourceLink.asset_id == FixedAsset.id,
            AssetSourceLink.source == "wialon",
            AssetSourceLink.status == "active",
        )
    )
    query = (
        select(FixedAsset)
        .where(
            ~has_link,
            FixedAsset.asset_type.in_(("locomotive", "diesel")),
        )
        .order_by(FixedAsset.name.asc(), FixedAsset.id.asc())
    )
    if master_section_id is not None:
        query = query.where(FixedAsset.section_id == master_section_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_unlinked_source_objects(
    db: AsyncSession,
) -> list[WialonUnitRecord]:
    has_link = exists(
        select(AssetSourceLink.id).where(
            AssetSourceLink.source == "wialon",
            AssetSourceLink.status == "active",
            AssetSourceLink.external_id == WialonUnitRecord.unit_id,
        )
    )
    result = await db.execute(
        select(WialonUnitRecord)
        .where(~has_link)
        .order_by(WialonUnitRecord.name.asc(), WialonUnitRecord.unit_id.asc())
    )
    return list(result.scalars().all())


async def get_unit_record(
    db: AsyncSession, unit_id: str, *, master_section_id=None
) -> WialonUnitRecord | None:
    query = select(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit_id)
    if master_section_id is not None:
        query = query.join(
            AssetSourceLink,
            and_(
                AssetSourceLink.external_id == WialonUnitRecord.unit_id,
                _active_asset_links(),
            ),
        ).join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id).where(
            FixedAsset.section_id == master_section_id
        )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_linked_asset(
    db: AsyncSession, unit_id: str
) -> FixedAsset | None:
    result = await db.execute(
        select(FixedAsset)
        .join(AssetSourceLink, AssetSourceLink.asset_id == FixedAsset.id)
        .where(
            AssetSourceLink.source == "wialon",
            AssetSourceLink.status == "active",
            AssetSourceLink.external_id == unit_id,
        )
    )
    return result.scalar_one_or_none()


async def get_section(
    db: AsyncSession, section_id
) -> Section | None:
    result = await db.execute(
        select(Section).where(
            Section.id == section_id,
            Section.is_archived.is_(False),
        )
    )
    return result.scalar_one_or_none()
