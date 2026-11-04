from datetime import datetime
from typing import Any

from sqlalchemy import String, cast, delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gtk import (
    GtkCarriage,
    GtkLocomotive,
    GtkLocomotiveMileageCheckpoint,
    GtkSyncRun,
    GtkTrain,
    GtkTrainMember,
    GtkWagonMileageLog,
)
from app.models.assets import FixedAsset
from app.models.asset_source_links import AssetSourceLink

LOCOMOTIVE_SORT_FIELDS = frozenset(
    {
        "gtk_id",
        "name",
        "garage_number",
        "inventory_number",
        "model_name",
        "start_expl_date",
        "end_expl_date",
        "is_active",
        "last_synced_at",
    }
)
CARRIAGE_SORT_FIELDS = frozenset(
    {
        "gtk_id",
        "name",
        "reg_number",
        "inventory_number",
        "model_name",
        "start_expl_date",
        "end_expl_date",
        "is_active",
        "state_duration_s",
        "last_synced_at",
    }
)
TRAIN_SORT_FIELDS = frozenset(
    {"gtk_id", "number", "title", "begin_time", "end_time", "is_open", "last_synced_at"}
)


def _sort_clause(model: Any, sort_by: str, sort_order: str, allowed: frozenset[str]):
    if sort_by not in allowed:
        raise ValueError("Unsupported GTK sort field")
    column = getattr(model, sort_by)
    return column.desc() if sort_order == "desc" else column.asc()


def _open_membership(kind: str, object_id: Any):
    return (
        select(GtkTrainMember.id)
        .where(
            GtkTrainMember.kind == kind,
            GtkTrainMember.object_gtk_id == object_id,
            GtkTrainMember.observed_to.is_(None),
        )
        .exists()
    )


async def _list_rows(
    db: AsyncSession,
    model: Any,
    *,
    filters: list[Any],
    sort_by: str,
    sort_order: str,
    allowed: frozenset[str],
    limit: int,
    offset: int,
) -> tuple[list[Any], int]:
    total = (
        await db.execute(select(func.count()).select_from(model).where(*filters))
    ).scalar_one()
    result = await db.execute(
        select(model)
        .where(*filters)
        .order_by(_sort_clause(model, sort_by, sort_order, allowed), model.gtk_id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def list_locomotives(
    db: AsyncSession,
    *,
    q: str | None,
    is_active: bool | None,
    in_train: bool | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[tuple[GtkLocomotive, bool]], int]:
    filters: list[Any] = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                GtkLocomotive.name.ilike(pattern),
                GtkLocomotive.garage_number.ilike(pattern),
                GtkLocomotive.inventory_number.ilike(pattern),
                GtkLocomotive.model_name.ilike(pattern),
            )
        )
    if is_active is not None:
        filters.append(GtkLocomotive.is_active.is_(is_active))
    if in_train is not None:
        membership = _open_membership("locomotive", GtkLocomotive.gtk_id)
        filters.append(membership if in_train else ~membership)
    total = (
        await db.execute(
            select(func.count()).select_from(GtkLocomotive).where(*filters)
        )
    ).scalar_one()
    result = await db.execute(
        select(
            GtkLocomotive,
            _open_membership("locomotive", GtkLocomotive.gtk_id).label("in_train"),
        )
        .where(*filters)
        .order_by(
            _sort_clause(
                GtkLocomotive, sort_by, sort_order, LOCOMOTIVE_SORT_FIELDS
            ),
            GtkLocomotive.gtk_id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.all()), total


async def list_carriages(
    db: AsyncSession,
    *,
    q: str | None,
    is_active: bool | None,
    in_train: bool | None,
    duplicate: bool | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[tuple[GtkCarriage, bool, bool]], int]:
    filters: list[Any] = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                GtkCarriage.name.ilike(pattern),
                GtkCarriage.reg_number.ilike(pattern),
                GtkCarriage.inventory_number.ilike(pattern),
                GtkCarriage.model_name.ilike(pattern),
            )
        )
    if is_active is not None:
        filters.append(GtkCarriage.is_active.is_(is_active))
    if in_train is not None:
        membership = _open_membership("carriage", GtkCarriage.gtk_id)
        filters.append(membership if in_train else ~membership)
    in_train_expression = _open_membership("carriage", GtkCarriage.gtk_id)
    ranked_carriages = (
        select(
            GtkCarriage.gtk_id.label("gtk_id"),
            func.row_number()
            .over(
                partition_by=func.lower(func.trim(GtkCarriage.reg_number)),
                order_by=(in_train_expression.desc(), GtkCarriage.gtk_id.asc()),
            )
            .label("registration_rank"),
        )
        .where(
            GtkCarriage.reg_number.is_not(None),
            func.trim(GtkCarriage.reg_number) != "",
        )
        .subquery()
    )
    is_duplicate = GtkCarriage.gtk_id.in_(
        select(ranked_carriages.c.gtk_id).where(
            ranked_carriages.c.registration_rank > 1
        )
    )
    if duplicate is True:
        filters.append(is_duplicate)
    elif duplicate is False:
        filters.append(or_(GtkCarriage.reg_number.is_(None), ~is_duplicate))

    total = (
        await db.execute(select(func.count()).select_from(GtkCarriage).where(*filters))
    ).scalar_one()
    result = await db.execute(
        select(
            GtkCarriage,
            is_duplicate.label("duplicate"),
            in_train_expression.label("in_train"),
        )
        .where(*filters)
        .order_by(
            _sort_clause(
                GtkCarriage, sort_by, sort_order, CARRIAGE_SORT_FIELDS
            ),
            GtkCarriage.gtk_id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.all()), total


async def list_trains(
    db: AsyncSession,
    *,
    q: str | None,
    is_open: bool | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[GtkTrain], int]:
    filters: list[Any] = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(GtkTrain.number.ilike(pattern), GtkTrain.title.ilike(pattern)))
    if is_open is not None:
        filters.append(GtkTrain.is_open.is_(is_open))
    return await _list_rows(
        db,
        GtkTrain,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
        allowed=TRAIN_SORT_FIELDS,
        limit=limit,
        offset=offset,
    )


async def get_train(db: AsyncSession, gtk_id: int) -> GtkTrain | None:
    return (
        await db.execute(select(GtkTrain).where(GtkTrain.gtk_id == gtk_id))
    ).scalar_one_or_none()


async def get_locomotive(db: AsyncSession, gtk_id: int) -> GtkLocomotive | None:
    return (
        await db.execute(select(GtkLocomotive).where(GtkLocomotive.gtk_id == gtk_id))
    ).scalar_one_or_none()


async def get_carriage(db: AsyncSession, gtk_id: int) -> GtkCarriage | None:
    return (
        await db.execute(select(GtkCarriage).where(GtkCarriage.gtk_id == gtk_id))
    ).scalar_one_or_none()


async def list_all_locomotives(db: AsyncSession) -> list[GtkLocomotive]:
    result = await db.execute(select(GtkLocomotive).order_by(GtkLocomotive.gtk_id))
    return list(result.scalars().all())


async def list_all_carriages(db: AsyncSession) -> list[tuple[GtkCarriage, bool]]:
    in_train = _open_membership("carriage", GtkCarriage.gtk_id)
    result = await db.execute(
        select(GtkCarriage, in_train.label("in_train")).order_by(GtkCarriage.gtk_id)
    )
    return list(result.all())


async def list_unlinked_source_objects(
    db: AsyncSession,
) -> list[GtkLocomotive | GtkCarriage]:
    records: list[GtkLocomotive | GtkCarriage] = []
    for model in (GtkLocomotive, GtkCarriage):
        has_link = exists(
            select(AssetSourceLink.id).where(
                AssetSourceLink.source == "gtk",
                AssetSourceLink.status == "active",
                AssetSourceLink.external_id == cast(model.gtk_id, String),
            )
        )
        result = await db.execute(
            select(model).where(~has_link).order_by(model.gtk_id.asc())
        )
        records.extend(result.scalars().all())
    return records


async def list_assets_for_kind(db: AsyncSession, kind: str) -> list[FixedAsset]:
    asset_types = (
        ("locomotive", "diesel") if kind == "locomotive" else ("wagon",)
    )
    linked = (
        select(AssetSourceLink.id)
        .where(
            AssetSourceLink.asset_id == FixedAsset.id,
            AssetSourceLink.source == "gtk",
            AssetSourceLink.status == "active",
        )
        .exists()
    )
    result = await db.execute(
        select(FixedAsset)
        .where(
            FixedAsset.asset_type.in_(asset_types),
            ~linked,
        )
        .order_by(FixedAsset.id)
    )
    return list(result.scalars().all())


async def get_linked_assets(
    db: AsyncSession, gtk_ids: set[str]
) -> dict[str, FixedAsset]:
    if not gtk_ids:
        return {}
    result = await db.execute(
        select(AssetSourceLink.external_id, FixedAsset)
        .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
        .where(
            AssetSourceLink.source == "gtk",
            AssetSourceLink.status == "active",
            AssetSourceLink.external_id.in_(gtk_ids),
        )
    )
    return {external_id: asset for external_id, asset in result.all()}


async def get_linked_assets_for_update(
    db: AsyncSession, gtk_ids: set[str]
) -> dict[str, FixedAsset]:
    if not gtk_ids:
        return {}
    result = await db.execute(
        select(AssetSourceLink.external_id, FixedAsset)
        .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id)
        .where(
            AssetSourceLink.source == "gtk",
            AssetSourceLink.status == "active",
            AssetSourceLink.external_id.in_(gtk_ids),
        )
        .with_for_update()
    )
    return {external_id: asset for external_id, asset in result.all()}


async def get_asset(db: AsyncSession, asset_id: Any) -> FixedAsset | None:
    return (
        await db.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
    ).scalar_one_or_none()


async def get_asset_by_gtk_id(db: AsyncSession, gtk_id: str) -> FixedAsset | None:
    result = await db.execute(
        select(FixedAsset)
        .join(AssetSourceLink, AssetSourceLink.asset_id == FixedAsset.id)
        .where(
            AssetSourceLink.source == "gtk",
            AssetSourceLink.external_id == gtk_id,
            AssetSourceLink.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def inventory_number_exists(db: AsyncSession, inv_number: str) -> bool:
    return (
        await db.execute(
            select(FixedAsset.id).where(FixedAsset.inv_number == inv_number).limit(1)
        )
    ).scalar_one_or_none() is not None


async def gtk_kind(db: AsyncSession, gtk_id: str) -> str | None:
    if not gtk_id.isdigit():
        return None
    numeric_id = int(gtk_id)
    if await get_locomotive(db, numeric_id) is not None:
        return "locomotive"
    if await get_carriage(db, numeric_id) is not None:
        return "carriage"
    return None


async def list_assets_by_ids(db: AsyncSession, asset_ids: set[Any]) -> dict[Any, FixedAsset]:
    if not asset_ids:
        return {}
    result = await db.execute(select(FixedAsset).where(FixedAsset.id.in_(asset_ids)))
    return {asset.id: asset for asset in result.scalars().all()}


async def list_gtk_objects(
    db: AsyncSession, kind: str, gtk_ids: set[int]
) -> dict[int, GtkLocomotive | GtkCarriage]:
    if not gtk_ids:
        return {}
    model = GtkLocomotive if kind == "locomotive" else GtkCarriage
    result = await db.execute(select(model).where(model.gtk_id.in_(gtk_ids)))
    return {row.gtk_id: row for row in result.scalars().all()}


async def get_linked_asset_for_update(
    db: AsyncSession, gtk_id: str
) -> FixedAsset | None:
    result = await db.execute(
        select(FixedAsset)
        .join(AssetSourceLink, AssetSourceLink.asset_id == FixedAsset.id)
        .where(
            AssetSourceLink.source == "gtk",
            AssetSourceLink.external_id == gtk_id,
            AssetSourceLink.status == "active",
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def list_open_memberships(db: AsyncSession) -> list[GtkTrainMember]:
    result = await db.execute(
        select(GtkTrainMember).where(GtkTrainMember.observed_to.is_(None))
    )
    return list(result.scalars().all())


async def get_locomotive_mileage_checkpoints(
    db: AsyncSession, locomotive_ids: set[int]
) -> dict[int, GtkLocomotiveMileageCheckpoint]:
    if not locomotive_ids:
        return {}
    result = await db.execute(
        select(GtkLocomotiveMileageCheckpoint)
        .where(
            GtkLocomotiveMileageCheckpoint.locomotive_gtk_id.in_(locomotive_ids)
        )
        .with_for_update()
    )
    return {
        row.locomotive_gtk_id: row
        for row in result.scalars().all()
    }


async def save_locomotive_mileage_checkpoints(
    db: AsyncSession,
    checkpoints: dict[int, tuple[Any, Any, datetime]],
) -> None:
    if not checkpoints:
        return
    existing = await get_locomotive_mileage_checkpoints(db, set(checkpoints))
    for gtk_id, (asset_id, mileage, checkpoint_at) in checkpoints.items():
        checkpoint = existing.get(gtk_id)
        if checkpoint is None:
            db.add(
                GtkLocomotiveMileageCheckpoint(
                    locomotive_gtk_id=gtk_id,
                    locomotive_asset_id=asset_id,
                    mileage=mileage,
                    checkpoint_at=checkpoint_at,
                )
            )
        else:
            checkpoint.locomotive_asset_id = asset_id
            checkpoint.mileage = mileage
            checkpoint.checkpoint_at = checkpoint_at


async def reset_locomotive_mileage_checkpoint(
    db: AsyncSession, locomotive_gtk_id: int
) -> None:
    await db.execute(
        delete(GtkLocomotiveMileageCheckpoint).where(
            GtkLocomotiveMileageCheckpoint.locomotive_gtk_id == locomotive_gtk_id
        )
    )


async def add_wagon_mileage_log(
    db: AsyncSession, log: GtkWagonMileageLog
) -> None:
    db.add(log)


async def list_wagon_mileage_logs(
    db: AsyncSession, *, asset_id: Any | None, limit: int, offset: int = 0
) -> tuple[list[GtkWagonMileageLog], int]:
    filters = (
        [GtkWagonMileageLog.wagon_asset_id == asset_id]
        if asset_id is not None
        else []
    )
    total = (
        await db.execute(
            select(func.count()).select_from(GtkWagonMileageLog).where(*filters)
        )
    ).scalar_one()
    result = await db.execute(
        select(GtkWagonMileageLog)
        .where(*filters)
        .order_by(
            GtkWagonMileageLog.period_to.desc(),
            GtkWagonMileageLog.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def recent_asset_wagon_mileage_logs(
    db: AsyncSession, asset_id: Any, *, limit: int = 10
) -> list[GtkWagonMileageLog]:
    result = await db.execute(
        select(GtkWagonMileageLog)
        .where(
            or_(
                GtkWagonMileageLog.wagon_asset_id == asset_id,
                GtkWagonMileageLog.loco_asset_id == asset_id,
            )
        )
        .order_by(
            GtkWagonMileageLog.period_to.desc(),
            GtkWagonMileageLog.id.desc(),
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_current_trains_for_member(
    db: AsyncSession, kind: str, object_gtk_id: int
) -> list[GtkTrain]:
    result = await db.execute(
        select(GtkTrain)
        .join(GtkTrainMember, GtkTrainMember.train_gtk_id == GtkTrain.gtk_id)
        .where(
            GtkTrainMember.kind == kind,
            GtkTrainMember.object_gtk_id == object_gtk_id,
            GtkTrainMember.observed_to.is_(None),
        )
        .order_by(GtkTrain.begin_time.desc().nullslast(), GtkTrain.gtk_id)
    )
    return list(result.scalars().all())


async def get_train_members(
    db: AsyncSession, gtk_id: int, *, current_only: bool = False
) -> list[tuple[GtkTrainMember, GtkLocomotive | GtkCarriage | None]]:
    filters = [GtkTrainMember.train_gtk_id == gtk_id]
    if current_only:
        filters.append(GtkTrainMember.observed_to.is_(None))
    members_result = await db.execute(
        select(GtkTrainMember)
        .where(*filters)
        .order_by(
            GtkTrainMember.kind.asc(),
            GtkTrainMember.object_gtk_id.asc(),
            GtkTrainMember.observed_from.desc(),
            GtkTrainMember.id.desc(),
        )
    )
    latest_members: dict[tuple[str, int], GtkTrainMember] = {}
    for member in members_result.scalars().all():
        latest_members.setdefault((member.kind, member.object_gtk_id), member)
    members = sorted(
        latest_members.values(),
        key=lambda member: (member.kind, member.ord, member.id),
    )
    locomotive_ids = {
        row.object_gtk_id for row in members if row.kind == "locomotive"
    }
    carriage_ids = {row.object_gtk_id for row in members if row.kind == "carriage"}
    locomotives = {}
    carriages = {}
    if locomotive_ids:
        rows = await db.execute(
            select(GtkLocomotive).where(GtkLocomotive.gtk_id.in_(locomotive_ids))
        )
        locomotives = {row.gtk_id: row for row in rows.scalars().all()}
    if carriage_ids:
        rows = await db.execute(
            select(GtkCarriage).where(GtkCarriage.gtk_id.in_(carriage_ids))
        )
        carriages = {row.gtk_id: row for row in rows.scalars().all()}
    return [
        (
            member,
            (locomotives if member.kind == "locomotive" else carriages).get(
                member.object_gtk_id
            ),
        )
        for member in members
    ]


async def latest_sync_run(db: AsyncSession) -> GtkSyncRun | None:
    result = await db.execute(
        select(GtkSyncRun).order_by(
            GtkSyncRun.started_at.desc(), GtkSyncRun.id.desc()
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def update_sync_run_counts(
    db: AsyncSession, run_id: int, counts: dict[str, Any]
) -> None:
    result = await db.execute(
        select(GtkSyncRun)
        .where(GtkSyncRun.id == run_id)
        .with_for_update()
    )
    run = result.scalar_one_or_none()
    if run is not None:
        run.counts = counts


async def latest_successful_counts(db: AsyncSession) -> dict[str, int] | None:
    result = await db.execute(
        select(GtkSyncRun.counts)
        .where(GtkSyncRun.status == "ok", GtkSyncRun.counts.is_not(None))
        .order_by(GtkSyncRun.finished_at.desc(), GtkSyncRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_mirror(
    db: AsyncSession, snapshot: dict[str, Any], *, synced_at: datetime
) -> None:
    for model, records, update_fields in (
        (
            GtkLocomotive,
            snapshot["locomotives"],
            (
                "name", "garage_number", "inventory_number", "model_name",
                "vehicle_type_name", "division_name", "start_expl_date",
                "end_expl_date", "is_active",
            ),
        ),
        (
            GtkCarriage,
            snapshot["carriages"],
            (
                "name", "reg_number", "inventory_number", "model_name",
                "start_expl_date", "end_expl_date", "is_active", "is_loaded",
                "is_not_serviceable", "lat", "lon", "state_duration_s",
            ),
        ),
        (
            GtkTrain,
            snapshot["trains"],
            ("number", "title", "begin_time", "end_time", "is_open"),
        ),
    ):
        values = [
            {
                **{key: row.get(key) for key in update_fields},
                "gtk_id": row["gtk_id"],
                "last_synced_at": synced_at,
            }
            for row in records
        ]
        if not values:
            continue
        statement = insert(model).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[model.gtk_id],
            set_={
                **{key: getattr(statement.excluded, key) for key in update_fields},
                "last_synced_at": statement.excluded.last_synced_at,
            },
        )
        await db.execute(statement)


async def sync_memberships(
    db: AsyncSession, snapshot: dict[str, Any], *, observed_at: datetime
) -> None:
    incoming: dict[tuple[int, str, int], dict[str, Any]] = {}
    for train in snapshot["trains"]:
        if not train["is_open"]:
            continue
        for member in train["locomotives"]:
            key = (train["gtk_id"], "locomotive", member["gtk_id"])
            incoming[key] = {
                "is_main": member["is_main"],
                "ord": member.get("order") or 0,
                "gtk_begin_time": train["begin_time"],
            }
        for member in train["carriages"]:
            key = (train["gtk_id"], "carriage", member["gtk_id"])
            incoming[key] = {
                "is_main": False,
                "ord": member.get("order") or 0,
                "gtk_begin_time": train["begin_time"],
            }

    result = await db.execute(
        select(GtkTrainMember).where(GtkTrainMember.observed_to.is_(None))
    )
    existing = {
        (member.train_gtk_id, member.kind, member.object_gtk_id): member
        for member in result.scalars().all()
    }
    for key, member in existing.items():
        if key not in incoming:
            member.observed_to = observed_at
            continue
        details = incoming.pop(key)
        member.is_main = details["is_main"]
        member.ord = details["ord"]
        member.gtk_begin_time = details["gtk_begin_time"]
    for (train_id, kind, object_id), details in incoming.items():
        db.add(
            GtkTrainMember(
                train_gtk_id=train_id,
                kind=kind,
                object_gtk_id=object_id,
                is_main=details["is_main"],
                ord=details["ord"],
                gtk_begin_time=details["gtk_begin_time"],
                observed_from=observed_at,
            )
        )


async def add_sync_run(db: AsyncSession, run: GtkSyncRun) -> None:
    db.add(run)
    await db.flush()
