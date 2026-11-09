import asyncio
import csv
import io
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory
from app.integrations.gtk_client import (
    GtkClient,
    GtkClientError,
    GtkLoginError,
    GtkParseError,
)
from app.integrations.gtk_adapter import GtkSourceAdapter
from app.models.gtk import GtkSyncRun, GtkWagonMileageLog
from app.repositories import asset_source_links as asset_links_repository
from app.repositories import asset_models as asset_models_repository
from app.repositories import gtk as repository
from app.models.assets import FixedAsset
from app.schemas.gtk import GtkLinkBatchRequest
from app.services import assets as assets_service
from app.services import asset_links as asset_links_service
from app.services import asset_passport
from app.services import asset_field_changes as field_changes_service
from app.services.audit_log import set_audit_system_context
from app.services import gtk_matching
from app.services.mileage_attribution import (
    LocomotiveMileage,
    MileageCheckpoint,
    TrainMembership,
    WagonAsset,
    compute_attribution,
)

logger = logging.getLogger(__name__)
_sync_lock = asyncio.Lock()
_consecutive_login_failures = 0
_auto_sync_stopped = False


def auto_sync_stopped() -> bool:
    return _auto_sync_stopped


def _counts(snapshot: dict[str, Any]) -> dict[str, int]:
    return {
        "locomotives": len(snapshot["locomotives"]),
        "carriages": len(snapshot["carriages"]),
        "trains": len(snapshot["trains"]),
    }


def _suspicious(current: dict[str, int], previous: dict[str, int] | None) -> bool:
    if not previous:
        return False
    return any(
        previous.get(key, 0) > 0
        and current.get(key, 0) * 2 < previous.get(key, 0)
        for key in ("carriages", "trains")
    )


def _failure_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, GtkLoginError):
        return "login_failed", "GTK login failed"
    if isinstance(exc, GtkParseError):
        return "parse_error", "GTK page could not be parsed"
    if isinstance(exc, GtkClientError):
        return "error", "GTK request failed"
    return "error", "GTK synchronization failed"


async def _write_run(db: AsyncSession, run: GtkSyncRun) -> GtkSyncRun:
    async with db.begin():
        await repository.add_sync_run(db, run)
    return run


def _snapshot_memberships(
    snapshot: dict[str, Any],
) -> list[TrainMembership]:
    memberships: list[TrainMembership] = []
    for train in snapshot["trains"]:
        if not train["is_open"]:
            continue
        memberships.extend(
            TrainMembership(
                train_gtk_id=train["gtk_id"],
                kind="locomotive",
                object_gtk_id=member["gtk_id"],
                is_main=member["is_main"],
            )
            for member in train["locomotives"]
        )
        memberships.extend(
            TrainMembership(
                train_gtk_id=train["gtk_id"],
                kind="carriage",
                object_gtk_id=member["gtk_id"],
            )
            for member in train["carriages"]
        )
    return memberships


async def _attribute_snapshot_mileage(
    db: AsyncSession,
    snapshot: dict[str, Any],
    previous_memberships: list[TrainMembership],
    run_id: int,
    base_counts: dict[str, int],
    *,
    observed_at: datetime,
) -> dict[str, int | float]:
    current_memberships = _snapshot_memberships(snapshot)
    locomotive_ids = {row["gtk_id"] for row in snapshot["locomotives"]}
    carriage_rows = {row["gtk_id"]: row for row in snapshot["carriages"]}
    carriage_ids = set(carriage_rows)
    all_gtk_ids = locomotive_ids | carriage_ids

    async with db.begin():
        linked_assets = await repository.get_linked_assets_for_update(
            db, {str(gtk_id) for gtk_id in all_gtk_ids}
        )
        locomotive_assets = {
            gtk_id: LocomotiveMileage(asset.id, asset.mileage)
            for gtk_id in locomotive_ids
            if (asset := linked_assets.get(str(gtk_id))) is not None
            and asset.asset_type in {"locomotive", "diesel"}
        }
        wagon_assets = {
            gtk_id: WagonAsset(asset.id, carriage_rows[gtk_id]["is_active"])
            for gtk_id in carriage_ids
            if (asset := linked_assets.get(str(gtk_id))) is not None
            and asset.asset_type == "wagon"
        }
        checkpoint_rows = await repository.get_locomotive_mileage_checkpoints(
            db, locomotive_ids
        )
        checkpoints = {
            gtk_id: MileageCheckpoint(
                row.locomotive_asset_id,
                row.mileage,
                row.checkpoint_at,
            )
            for gtk_id, row in checkpoint_rows.items()
        }
        result = compute_attribution(
            previous_memberships,
            current_memberships,
            locomotive_assets,
            wagon_assets,
            checkpoints,
            observed_at=observed_at,
        )
        if result.loco_rejected:
            logger.warning(
                "GTK locomotive mileage attribution rejected: count=%s",
                result.loco_rejected,
            )

        updated_mileage: dict[UUID, Decimal] = {}
        assets_by_id = {asset.id: asset for asset in linked_assets.values()}
        for entry in result.entries:
            updated_mileage[entry.wagon_asset_id] = (
                updated_mileage.get(
                    entry.wagon_asset_id,
                    assets_by_id[entry.wagon_asset_id].mileage,
                )
                + entry.km
            )
            await repository.add_wagon_mileage_log(
                db,
                GtkWagonMileageLog(
                    wagon_asset_id=entry.wagon_asset_id,
                    loco_asset_id=entry.loco_asset_id,
                    train_gtk_id=entry.train_gtk_id,
                    period_from=entry.period_from,
                    period_to=entry.period_to,
                    km=entry.km,
                ),
            )
        for asset_id, mileage in updated_mileage.items():
            asset = assets_by_id[asset_id]
            asset.mileage = mileage
            asset.updated_at = observed_at
            await assets_service.repository.add_mileage_history(
                db, asset_id, mileage, "gtk"
            )

        await repository.save_locomotive_mileage_checkpoints(
            db,
            {
                gtk_id: (checkpoint.asset_id, checkpoint.mileage, checkpoint.at)
                for gtk_id, checkpoint in result.checkpoints.items()
            },
        )
        attribution_counts: dict[str, int | float] = {
            "attributed_km": float(result.attributed_km),
            "unattributed_km": float(result.unattributed_km),
            "wagons_updated": result.wagons_updated,
            "loco_unlinked": result.loco_unlinked,
            "loco_rejected": result.loco_rejected,
        }
        await repository.update_sync_run_counts(
            db, run_id, {**base_counts, **attribution_counts}
        )
        return attribution_counts


async def _propose_gtk_passport_fields(
    db: AsyncSession, snapshot: dict[str, Any]
) -> None:
    carriages = snapshot["carriages"]
    linked_assets = await repository.get_linked_assets_for_update(
        db, {str(row["gtk_id"]) for row in carriages}
    )
    for row in carriages:
        asset = linked_assets.get(str(row["gtk_id"]))
        if asset is None:
            continue
        registration = row.get("reg_number")
        if registration:
            await field_changes_service.propose_field(
                db,
                asset_id=asset.id,
                field="number",
                value=registration,
                source="gtk",
            )
        model_name = (row.get("model_name") or "").strip()
        if not model_name:
            continue
        normalized_name = asset_passport.normalize_token(model_name)
        if not normalized_name:
            continue
        model = await asset_models_repository.get_by_normalized_name(
            db, normalized_name
        )
        if model is None and asset.model_id is None:
            model = await asset_models_repository.add_if_missing(
                db,
                name=model_name,
                name_normalized=normalized_name,
                asset_type="wagon",
                series=model_name,
            )
        if model is None or model.asset_type != "wagon":
            logger.warning(
                "GTK carriage model proposal could not be resolved for asset %s",
                asset.id,
            )
            continue
        await field_changes_service.propose_field(
            db,
            asset_id=asset.id,
            field="model_id",
            value=model.id,
            source="gtk",
        )


async def _run_gtk_passport_proposals(snapshot: dict[str, Any]) -> None:
    try:
        async with SessionFactory() as proposal_db:
            async with proposal_db.begin():
                await _propose_gtk_passport_fields(proposal_db, snapshot)
    except Exception:
        logger.exception(
            "GTK passport field proposals failed; the GTK snapshot was retained"
        )


async def sync_gtk(db: AsyncSession) -> GtkSyncRun | None:
    global _consecutive_login_failures, _auto_sync_stopped
    async with _sync_lock:
        if _auto_sync_stopped:
            return None

        set_audit_system_context(db, "gtk")
        started_at = datetime.now(timezone.utc)
        adapter = GtkSourceAdapter(
            GtkClient(
                settings.gtk_host,
                settings.gtk_user,
                settings.gtk_password,
                settings.gtk_page_path,
                settings.gtk_page_query,
            )
        )
        try:
            snapshot = await adapter.fetch_gtk_snapshot()
            counts = _counts(snapshot)
            run_at = datetime.now(timezone.utc)
            previous_memberships: list[TrainMembership] = []
            async with db.begin():
                previous = await repository.latest_successful_counts(db)
                is_suspicious = _suspicious(counts, previous)
                if not is_suspicious:
                    previous_memberships = [
                        TrainMembership(
                            train_gtk_id=member.train_gtk_id,
                            kind=member.kind,
                            object_gtk_id=member.object_gtk_id,
                            is_main=member.is_main,
                        )
                        for member in await repository.list_open_memberships(db)
                    ]
                    await repository.upsert_mirror(db, snapshot, synced_at=run_at)
                    await repository.sync_memberships(
                        db, snapshot, observed_at=run_at
                    )
                run = GtkSyncRun(
                    started_at=started_at,
                    finished_at=run_at,
                    status="suspicious" if is_suspicious else "ok",
                    counts=counts,
                    quality=snapshot["quality"],
                    error=(
                        "GTK snapshot count dropped by more than 50%"
                        if is_suspicious
                        else None
                    ),
                )
                await repository.add_sync_run(db, run)
            if not is_suspicious:
                try:
                    async with SessionFactory() as attribution_db:
                        set_audit_system_context(attribution_db, "gtk")
                        attribution_counts = await _attribute_snapshot_mileage(
                            attribution_db,
                            snapshot,
                            previous_memberships,
                            run.id,
                            counts,
                            observed_at=run_at,
                        )
                    run.counts = {**counts, **attribution_counts}
                except Exception:
                    logger.exception(
                        "GTK locomotive mileage attribution failed; GTK snapshot was retained"
                    )
                await _run_gtk_passport_proposals(snapshot)
            _consecutive_login_failures = 0
            logger.info("GTK sync finished with status=%s counts=%s", run.status, counts)
            return run
        except Exception as exc:
            _consecutive_login_failures = (
                _consecutive_login_failures + 1
                if isinstance(exc, GtkLoginError)
                else 0
            )
            if _consecutive_login_failures >= 3:
                _auto_sync_stopped = True
            status, safe_error = _failure_details(exc)
            finished_at = datetime.now(timezone.utc)
            try:
                run = await _write_run(
                    db,
                    GtkSyncRun(
                        started_at=started_at,
                        finished_at=finished_at,
                        status=status,
                        error=safe_error,
                    ),
                )
            except Exception:
                logger.error("GTK sync run could not be recorded (%s)", type(exc).__name__)
                raise
            logger.error("GTK sync failed with status=%s (%s)", status, type(exc).__name__)
            return run


async def get_status(db: AsyncSession) -> dict[str, Any]:
    return {
        "enabled": settings.gtk_pull_enabled,
        "interval_minutes": settings.gtk_sync_interval_minutes,
        "auto_sync_stopped": auto_sync_stopped(),
        "last_run": await repository.latest_sync_run(db),
    }


async def list_locomotives(db: AsyncSession, **filters: Any):
    rows, total = await repository.list_locomotives(db, **filters)
    matches = await _match_context(db, "locomotive")
    all_report = {
        row["gtk_id"]: row for row in gtk_matching.match_report(
            "locomotive", matches["gtk_rows"], matches["assets"]
        )
    }
    linked_assets = await repository.get_linked_assets(
        db, {str(row.gtk_id) for row, _ in rows}
    )
    return [
        {
            **{
                column.name: getattr(row, column.name)
                for column in row.__table__.columns
            },
            "in_train": in_train,
            "linked_asset": _asset_preview(linked_assets.get(str(row.gtk_id))),
            "suggestion": _suggestion(all_report.get(row.gtk_id)),
        }
        for row, in_train in rows
    ], total


async def list_carriages(db: AsyncSession, **filters: Any):
    rows, total = await repository.list_carriages(db, **filters)
    context = await _match_context(db, "carriage")
    all_report = gtk_matching.match_report(
        "carriage",
        context["gtk_rows"],
        context["assets"],
        in_train_ids=context["in_train_ids"],
    )
    report_by_id = {row["gtk_id"]: row for row in all_report}
    linked_assets = await repository.get_linked_assets(
        db, {str(row.gtk_id) for row, _, _ in rows}
    )
    return [
        {
            **{
                column.name: getattr(row, column.name)
                for column in row.__table__.columns
            },
            "in_train": in_train,
            "duplicate": duplicate,
            "linked_asset": _asset_preview(linked_assets.get(str(row.gtk_id))),
            "suggestion": _suggestion(report_by_id.get(row.gtk_id)),
        }
        for row, duplicate, in_train in rows
    ], total


async def list_trains(db: AsyncSession, **filters: Any):
    rows, total = await repository.list_trains(db, **filters)
    return rows, total


async def get_train_detail(
    db: AsyncSession, gtk_id: int, *, current_only: bool = False
) -> dict[str, Any] | None:
    train = await repository.get_train(db, gtk_id)
    if train is None:
        return None
    locomotives = []
    carriages = []
    for member, vehicle in await repository.get_train_members(
        db, gtk_id, current_only=current_only
    ):
        if vehicle is None:
            continue
        values = {
            column.name: getattr(vehicle, column.name)
            for column in vehicle.__table__.columns
        }
        values.update(
            in_train=True,
            ord=member.ord,
            is_main=member.is_main,
        )
        if member.kind == "locomotive":
            locomotives.append(values)
        else:
            carriages.append(values)
    return {
        **{
            column.name: getattr(train, column.name)
            for column in train.__table__.columns
        },
        "locomotives": locomotives,
        "carriages": carriages,
    }


async def list_wagon_mileage(
    db: AsyncSession, *, asset_id: UUID | None, limit: int
) -> dict[str, Any]:
    items, total = await repository.list_wagon_mileage_logs(
        db, asset_id=asset_id, limit=limit
    )
    return {"items": items, "total": total, "limit": limit}


async def get_fixed_asset_gtk_detail(
    db: AsyncSession,
    asset_id: UUID,
    *,
    master_section_id: UUID | None,
) -> dict[str, Any]:
    asset = await assets_service.get_fixed_asset(
        db, asset_id, master_section_id=master_section_id
    )
    active_links = await asset_links_service.get_active(db, asset_id)
    gtk_link = next((row for row in active_links if row.source == "gtk"), None)
    if gtk_link is None or not gtk_link.external_id.isdigit():
        raise HTTPException(status_code=404, detail="GTK link not found")
    gtk_id = int(gtk_link.external_id)
    if asset.asset_type in {"locomotive", "diesel"}:
        kind = "locomotive"
        gtk_object = await repository.get_locomotive(db, gtk_id)
    elif asset.asset_type == "wagon":
        kind = "carriage"
        gtk_object = await repository.get_carriage(db, gtk_id)
    else:
        raise HTTPException(status_code=404, detail="GTK link not found")
    if gtk_object is None:
        raise HTTPException(status_code=404, detail="GTK record not found")

    trains = await repository.list_current_trains_for_member(db, kind, gtk_id)
    current_trains = []
    for train in trains:
        detail = await get_train_detail(db, train.gtk_id, current_only=True)
        if detail is not None:
            current_trains.append(detail)
    logs = await repository.recent_asset_wagon_mileage_logs(db, asset_id, limit=10)
    return {
        "asset_id": asset.id,
        "gtk_id": gtk_id,
        "kind": kind,
        "gtk_object": {
            **{
                column.name: getattr(gtk_object, column.name)
                for column in gtk_object.__table__.columns
            },
            "in_train": bool(trains),
            "linked_asset": _asset_preview(
                await repository.get_asset_by_gtk_id(db, str(gtk_id))
            ),
        },
        "current_trains": current_trains,
        "recent_mileage_logs": logs,
    }


async def _match_context(db: AsyncSession, kind: str) -> dict[str, Any]:
    in_train_ids: set[int] = set()
    if kind == "locomotive":
        gtk_rows = await repository.list_all_locomotives(db)
    else:
        rows = await repository.list_all_carriages(db)
        gtk_rows = [carriage for carriage, _ in rows]
        in_train_ids = {
            carriage.gtk_id for carriage, in_train in rows if in_train
        }
    return {
        "gtk_rows": gtk_rows,
        "in_train_ids": in_train_ids,
        "assets": await repository.list_assets_for_kind(db, kind),
    }


def _asset_preview(asset: FixedAsset | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "name": asset.name,
        "inv_number": asset.inv_number,
        "asset_type": asset.asset_type,
    }


def _suggestion(match: dict[str, Any] | None) -> dict[str, Any]:
    if match is None or match["level"] == "duplicate":
        return {"level": "none", "candidate_count": 0, "asset": None, "signals": []}
    return {
        "level": match["level"],
        "candidate_count": match["candidate_count"],
        "asset": match["suggestion"],
        "signals": match.get("signals", []),
    }


async def get_match_report(db: AsyncSession, kind: str) -> dict[str, Any]:
    context = await _match_context(db, kind)
    report = gtk_matching.match_report(
        kind,
        context["gtk_rows"],
        context["assets"],
        in_train_ids=context["in_train_ids"],
    )
    linked_assets = await repository.get_linked_assets(
        db, {str(row.gtk_id) for row in context["gtk_rows"]}
    )
    for item in report:
        item["linked_asset"] = _asset_preview(
            linked_assets.get(str(item["gtk_id"]))
        )
    totals: dict[str, int] = {}
    for item in report:
        totals[item["level"]] = totals.get(item["level"], 0) + 1
    return {"kind": kind, "totals": totals, "items": report}


def match_report_csv(report: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        (
            "gtk_id",
            "kind",
            "level",
            "candidate_count",
            "suggested_asset_id",
            "suggested_asset_name",
            "suggested_inv_number",
            "signals",
            "linked_asset_id",
        )
    )
    for item in report["items"]:
        suggestion = item.get("suggestion") or {}
        linked = item.get("linked_asset") or {}
        writer.writerow(
            (
                item["gtk_id"],
                item["kind"],
                item["level"],
                item["candidate_count"],
                suggestion.get("id"),
                suggestion.get("name"),
                suggestion.get("inv_number"),
                ",".join(item.get("signals") or ()),
                linked.get("id"),
            )
        )
    return output.getvalue()


async def save_links(
    db: AsyncSession, payload: GtkLinkBatchRequest, *, by: UUID | None = None
) -> int:
    links = payload.links
    asset_ids = [link.asset_id for link in links]
    keys = [(link.kind, link.gtk_id) for link in links]
    if len(set(asset_ids)) != len(asset_ids) or len(set(keys)) != len(keys):
        raise HTTPException(
            status_code=422, detail="A link batch cannot repeat an asset or GTK object"
        )
    try:
        assets = await repository.list_assets_by_ids(db, set(asset_ids))
        objects_by_kind = {
            kind: await repository.list_gtk_objects(
                db, kind, {gtk_id for link_kind, gtk_id in keys if link_kind == kind}
            )
            for kind in ("locomotive", "carriage")
        }
        if len(assets) != len(asset_ids):
            raise HTTPException(status_code=404, detail="Fixed asset not found")
        for link in links:
            asset = assets[link.asset_id]
            gtk_object = objects_by_kind[link.kind].get(link.gtk_id)
            if gtk_object is None:
                raise HTTPException(status_code=404, detail="GTK record not found")
            if link.kind == "locomotive" and asset.asset_type not in {
                "locomotive",
                "diesel",
            }:
                raise HTTPException(status_code=422, detail="GTK locomotive needs a locomotive or diesel asset")
            if link.kind == "carriage" and asset.asset_type != "wagon":
                raise HTTPException(status_code=422, detail="GTK carriage needs a wagon asset")
            current = await asset_links_repository.get_active_for_update(
                db, asset.id, "gtk"
            )
            previous_id = current.external_id if current is not None else None
            await asset_links_service.link(
                db,
                asset.id,
                "gtk",
                str(link.gtk_id),
                by,
                external_name=gtk_object.name,
            )
            if previous_id != str(link.gtk_id):
                if previous_id is not None and await repository.gtk_kind(
                    db, previous_id
                ) == "locomotive":
                    await repository.reset_locomotive_mileage_checkpoint(
                        db, int(previous_id)
                    )
                if link.kind == "locomotive":
                    await repository.reset_locomotive_mileage_checkpoint(
                        db, link.gtk_id
                    )
        await db.commit()
        return len(links)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GTK ID is already linked to another fixed asset",
        ) from exc
    except Exception:
        await db.rollback()
        raise


async def delete_link(db: AsyncSession, asset_id: UUID) -> None:
    asset = await repository.get_asset(db, asset_id)
    current = await asset_links_repository.get_active_for_update(
        db, asset_id, "gtk"
    )
    if asset is None or current is None:
        raise HTTPException(status_code=404, detail="GTK link not found")
    if await repository.gtk_kind(db, current.external_id) == "locomotive":
        await repository.reset_locomotive_mileage_checkpoint(
            db, int(current.external_id)
        )
    try:
        await asset_links_service.unlink(db, asset_id, "gtk")
        await db.commit()
    except Exception:
        await db.rollback()
        raise


def _clean_gtk_name(value: str | None) -> str:
    return " ".join((value or "").split())


async def _carriage_preview(db: AsyncSession, carriage) -> tuple[dict[str, Any] | None, str | None]:
    if not carriage.is_active:
        return None, "inactive"
    if not _clean_gtk_name(carriage.name):
        return None, "empty_name"
    model_name = asset_passport.derive_model_name(
        carriage.name, series=carriage.model_name
    )
    number = (getattr(carriage, "reg_number", None) or "").strip() or (
        asset_passport.extract_passport_number(carriage.name, series=model_name)
    )
    if not model_name:
        return None, "missing_model"
    if not number:
        return None, "missing_number"
    if await repository.get_linked_assets(db, {str(carriage.gtk_id)}):
        return None, "already_linked"
    inventory = (carriage.inventory_number or "").strip()
    if not inventory or await repository.inventory_number_exists(db, inventory):
        inventory = f"GTK-{carriage.gtk_id}"
    if await repository.inventory_number_exists(db, inventory):
        return None, "inventory_number_in_use"
    return {
        "name": _clean_gtk_name(carriage.name),
        "asset_type": "wagon",
        "series": model_name,
        "inv_number": inventory,
        "mileage": Decimal("0"),
        "gtk_id": str(carriage.gtk_id),
        "number": number,
        "number_normalized": asset_passport.normalize_token(number),
        "inv_number_is_provisional": inventory.upper().startswith("WIALON-"),
    }, None


async def create_carriage_asset(
    db: AsyncSession, gtk_id: int, *, dry_run: bool, by: UUID | None = None
) -> dict[str, Any]:
    carriage = await repository.get_carriage(db, gtk_id)
    if carriage is None:
        raise HTTPException(status_code=404, detail="GTK carriage not found")
    preview, reason = await _carriage_preview(db, carriage)
    if preview is None:
        return {
            "dry_run": dry_run,
            "created": 0,
            "would_create": 0,
            "skipped": 1,
            "items": [{"gtk_id": gtk_id, "status": "skipped", "reason": reason}],
        }
    if dry_run:
        return {
            "dry_run": True,
            "created": 0,
            "would_create": 1,
            "skipped": 0,
            "items": [
                {
                    "gtk_id": gtk_id,
                    "status": "would_create",
                    "asset": preview,
                }
            ],
        }
    await _ensure_wagon_catalog(db)
    passport_fields = await asset_passport.prepare_new_asset(
        db,
        asset_type="wagon",
        name=preview["name"],
        model_id=None,
        model_name=preview["series"],
        number=preview["number"],
    )
    asset = FixedAsset(**(preview | passport_fields))
    try:
        db.add(asset)
        await db.flush()
        field_changes_service.record_changes(
            db,
            asset,
            old_values={},
            new_values={
                field: getattr(asset, field)
                for field in field_changes_service.PASSPORT_FIELD_NAMES
            },
            source="gtk",
            kind="manual",
        )
        await asset_links_service.link(
            db,
            asset.id,
            "gtk",
            str(gtk_id),
            by,
            external_name=carriage.name,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="GTK ID or inventory number is already linked",
        ) from exc
    except Exception:
        await db.rollback()
        raise
    await db.refresh(asset)
    return {
        "dry_run": False,
        "created": 1,
        "would_create": 0,
        "skipped": 0,
        "items": [
            {
                "gtk_id": gtk_id,
                "status": "created",
                "asset": {
                    "name": asset.name,
                    "asset_type": asset.asset_type,
                    "series": asset.series,
                    "inv_number": asset.inv_number,
                    "mileage": asset.mileage,
                    "gtk_id": str(gtk_id),
                },
            }
        ],
    }


async def _ensure_wagon_catalog(db: AsyncSession) -> None:
    if not await assets_service.repository.active_catalog_value_exists(
        db, kind="types", code="wagon"
    ):
        raise HTTPException(status_code=422, detail="Wagon asset type is unavailable")
    if not await assets_service.repository.active_catalog_value_exists(
        db, kind="statuses", code="operational"
    ):
        raise HTTPException(status_code=422, detail="Operational asset status is unavailable")


async def create_carriage_assets(
    db: AsyncSession, *, dry_run: bool, by: UUID | None = None
) -> dict[str, Any]:
    rows = await repository.list_all_carriages(db)
    carriages = [row for row, _ in rows]
    in_train_ids = {row.gtk_id for row, in_train in rows if in_train}
    duplicate_ids = gtk_matching.preferred_carriage_ids(carriages, in_train_ids)
    linked_assets = await repository.get_linked_assets(
        db, {str(carriage.gtk_id) for carriage in carriages}
    )

    eligible: list[tuple[Any, dict[str, Any]]] = []
    reports = []
    reserved_inventories: set[str] = set()
    for carriage in carriages:
        reason = None
        preview = None
        if not carriage.is_active:
            reason = "inactive"
        elif carriage.gtk_id in duplicate_ids:
            reason = "duplicate_reg_number"
        elif str(carriage.gtk_id) in linked_assets:
            reason = "already_linked"
        elif not _clean_gtk_name(carriage.name):
            reason = "empty_name"
        else:
            model_name = asset_passport.derive_model_name(
                carriage.name, series=carriage.model_name
            )
            number = (
                (getattr(carriage, "reg_number", None) or "").strip()
                or asset_passport.extract_passport_number(
                    carriage.name, series=model_name
                )
            )
            if not model_name:
                reason = "missing_model"
            elif not number:
                reason = "missing_number"
            else:
                inventory = (carriage.inventory_number or "").strip()
                if (
                    not inventory
                    or inventory in reserved_inventories
                    or await repository.inventory_number_exists(db, inventory)
                ):
                    inventory = f"GTK-{carriage.gtk_id}"
                if (
                    inventory in reserved_inventories
                    or await repository.inventory_number_exists(db, inventory)
                ):
                    reason = "inventory_number_in_use"
                else:
                    reserved_inventories.add(inventory)
                    preview = {
                        "name": _clean_gtk_name(carriage.name),
                        "asset_type": "wagon",
                        "series": model_name,
                        "inv_number": inventory,
                        "mileage": Decimal("0"),
                        "gtk_id": str(carriage.gtk_id),
                        "number": number,
                        "number_normalized": asset_passport.normalize_token(number),
                        "inv_number_is_provisional": inventory.upper().startswith(
                            "WIALON-"
                        ),
                    }
        if reason:
            reports.append(
                {"gtk_id": carriage.gtk_id, "status": "skipped", "reason": reason}
            )
        else:
            eligible.append((carriage, preview))
            reports.append(
                {
                    "gtk_id": carriage.gtk_id,
                    "status": "would_create" if dry_run else "created",
                    "asset": preview,
                }
            )
    if dry_run or not eligible:
        return {
            "dry_run": dry_run,
            "created": 0,
            "would_create": len(eligible),
            "skipped": len(reports) - len(eligible),
            "items": reports,
        }

    await _ensure_wagon_catalog(db)
    try:
        new_assets = []
        for carriage, preview in eligible:
            passport_fields = await asset_passport.prepare_new_asset(
                db,
                asset_type="wagon",
                name=preview["name"],
                model_id=None,
                model_name=preview["series"],
                number=preview["number"],
            )
            asset = FixedAsset(**(preview | passport_fields))
            db.add(asset)
            new_assets.append((carriage, asset))
        await db.flush()
        for carriage, asset in new_assets:
            field_changes_service.record_changes(
                db,
                asset,
                old_values={},
                new_values={
                    field: getattr(asset, field)
                    for field in field_changes_service.PASSPORT_FIELD_NAMES
                },
                source="gtk",
                kind="manual",
            )
            await asset_links_service.link(
                db,
                asset.id,
                "gtk",
                str(carriage.gtk_id),
                by,
                external_name=carriage.name,
            )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Bulk GTK asset creation conflicted; no assets were created",
        ) from exc
    except Exception:
        await db.rollback()
        raise
    return {
        "dry_run": False,
        "created": len(eligible),
        "would_create": 0,
        "skipped": len(reports) - len(eligible),
        "items": reports,
    }


async def run_periodic_gtk_sync() -> None:
    while True:
        if settings.gtk_pull_enabled and not auto_sync_stopped():
            try:
                async with SessionFactory() as db:
                    await sync_gtk(db)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Background GTK synchronization failed (%s)", type(exc).__name__)
        await asyncio.sleep(settings.gtk_sync_interval_minutes * 60)
