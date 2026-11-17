"""The asset map: where every fixed asset is, from the Wialon unit (GPS) or the GTK carriage state.

Wialon is preferred (a live GPS fix with its own time); GTK is used for assets Wialon cannot place (wagons). An
asset without a link or without coordinates is not drawn but is counted with the reason, so a gap is never silent.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.repositories import asset_map as repository
from app.schemas.asset_map import (
    AssetMapPoint, AssetMapRead, AssetMapSummary, AssetUnplacedItem, AssetUnplacedPage, AssetUnplacedSummary, GtkCandidate, TypeCount,
)

_COMMON = (
    "asset_id", "inv_number", "name", "asset_type", "asset_type_name", "status", "status_name",
    "section_id", "section_name", "model_name",
)


def _master_section_scope(user: User) -> UUID | None:
    if user.role != "master":
        return None
    if user.section_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Master user must be assigned to a section")
    return user.section_id


def _valid(lat, lon) -> bool:
    return lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180 and not (lat == 0 and lon == 0)


def _train_for(row: dict, trains: dict[str, dict]) -> dict | None:
    """The train position of a wagon (never of a locomotive: GTK locomotive and carriage ids are different spaces)."""
    external_id = row.get("gtk_external_id")
    if external_id is None or row["asset_type"] in repository.LOCOMOTIVE_TYPES:
        return None
    train = trains.get(str(external_id))
    return train if train is not None and _valid(train["lat"], train["lon"]) else None


def build_points(
    rows: list[dict], since, source: str | None = None, trains: dict[str, dict] | None = None, scope_section_id: UUID | None = None,
) -> AssetMapRead:
    """Pure part: choose the best position of every row and count what cannot be drawn.

    Order: the asset's own Wialon fix, then (wagons only) the position of the locomotive pulling its open GTK train, then the
    carriage's own GTK coordinate. `scope_section_id` is a master's section: a locomotive of another section is not named.
    """
    trains = trains or {}
    points: list[AssetMapPoint] = []
    summary = AssetMapSummary(total_assets=len(rows))
    for row in rows:
        common = {key: row[key] for key in _COMMON}
        if _valid(row["wialon_lat"], row["wialon_lon"]):
            last = row["wialon_last_message_at"]
            point = AssetMapPoint(
                **common, lat=float(row["wialon_lat"]), lon=float(row["wialon_lon"]), source="wialon",
                position_at=row["wialon_position_at"] or last, speed=row["wialon_speed"],
                online=last is not None and last >= since,
            )
        elif (train := _train_for(row, trains)) is not None:
            last = train["last_message_at"]
            loco_visible = scope_section_id is None or train["locomotive_section_id"] == scope_section_id
            point = AssetMapPoint(
                **common, lat=float(train["lat"]), lon=float(train["lon"]), source="train",
                position_at=train["position_at"] or last, speed=train["speed"], online=last is not None and last >= since,
                train_number=train["train_number"],
                locomotive_asset_id=train["locomotive_asset_id"] if loco_visible else None,
                locomotive_inv_number=train["locomotive_inv_number"] if loco_visible else None,
                locomotive_name=train["locomotive_name"] if loco_visible else None,
            )
        elif _valid(row["gtk_lat"], row["gtk_lon"]):
            point = AssetMapPoint(
                **common, lat=float(row["gtk_lat"]), lon=float(row["gtk_lon"]), source="gtk",
                position_at=row["gtk_synced_at"],
            )
        else:
            reason = "no_position" if (row["wialon_link_id"] or row["gtk_link_id"]) else "no_link"
            summary.unplaced += 1
            summary.unplaced_reasons[reason] = summary.unplaced_reasons.get(reason, 0) + 1
            continue
        summary.placed += 1
        summary.by_source[point.source] = summary.by_source.get(point.source, 0) + 1
        if source is None or point.source == source:
            points.append(point)
    return AssetMapRead(points=points, summary=summary)


async def get_asset_map(
    db: AsyncSession,
    user: User,
    *,
    asset_type: str | None = None,
    source: str | None = None,
    section_id: UUID | None = None,
    q: str | None = None,
) -> AssetMapRead:
    scope = _master_section_scope(user)
    if scope is not None:
        section_id = scope  # a master only ever sees their own section, whatever the query says
    rows = await repository.list_asset_positions(db, asset_type=asset_type, section_id=section_id, q=q)
    trains = await repository.list_train_positions(db)
    return build_points(rows, repository.online_since(), source, trains, scope)


# ---- the "without coordinates" page: WHY an asset is not on the map -----------------------------------------
UNPLACED_SORT_FIELDS = {"inv_number", "asset_type", "reason", "age"}
_REASON_ORDER = (
    "no_link", "wialon_unit_missing", "wialon_no_fix", "gtk_locomotive_only", "gtk_carriage_missing", "gtk_no_coords", "train_no_gps",
)


def _is_placed(row: dict, trains: dict[str, dict]) -> bool:
    """The same decision as build_points: an own Wialon fix, a train position (wagons) or an own GTK coordinate."""
    return _valid(row["wialon_lat"], row["wialon_lon"]) or _train_for(row, trains) is not None or _valid(row["gtk_lat"], row["gtk_lon"])


def classify_unplaced(row: dict, open_trains: dict[str, dict]) -> tuple[str, str, dict | None]:
    """(group, detailed reason, open train of the carriage) for an asset that has no position."""
    is_locomotive = row["asset_type"] in repository.LOCOMOTIVE_TYPES
    wialon_linked, gtk_linked = row["wialon_link_id"] is not None, row["gtk_link_id"] is not None
    if not wialon_linked and not gtk_linked:
        return "no_link", "no_link", None
    if wialon_linked:  # Wialon is the preferred source, so its problem is the one to explain
        return "no_position", ("wialon_no_fix" if row.get("wialon_unit_id") is not None else "wialon_unit_missing"), None
    if is_locomotive:
        return "no_position", "gtk_locomotive_only", None
    if row.get("gtk_carriage_id") is None:
        return "no_position", "gtk_carriage_missing", None
    train = open_trains.get(str(row["gtk_external_id"]))
    if train is not None:
        return "no_position", "train_no_gps", train
    return "no_position", "gtk_no_coords", None


def _norm(value) -> str | None:
    text = ("" if value is None else str(value)).strip().lstrip("0").lower()
    return text or None


def find_gtk_candidate(row: dict, carriages: list[dict]) -> GtkCandidate | None:
    """The best GTK carriage for an UNLINKED wagon: the same inventory number and/or the same registration (= serial) number."""
    if row["asset_type"] in repository.LOCOMOTIVE_TYPES:
        return None
    inventory, serial = _norm(row["inv_number"]), _norm(row.get("serial_number"))
    best: tuple[int, int, int, dict, str] | None = None
    for carriage in carriages:
        by_inv = inventory is not None and _norm(carriage["inventory_number"]) == inventory
        by_reg = serial is not None and _norm(carriage["reg_number"]) == serial
        if not by_inv and not by_reg:
            continue
        # strongest match first, then a free carriage, then an active one, then the lowest id
        rank = (0 if (by_inv and by_reg) else 1 if by_inv else 2, 1 if carriage["taken_by_inv_number"] else 0, 0 if carriage["is_active"] else 1, carriage["gtk_id"])
        match = "inv_and_reg" if (by_inv and by_reg) else "inv" if by_inv else "reg"
        if best is None or rank < best[:4]:
            best = (*rank, carriage, match)  # type: ignore[assignment]
    if best is None:
        return None
    carriage, match = best[4], best[5]
    return GtkCandidate(
        gtk_id=carriage["gtk_id"], name=carriage["name"], reg_number=carriage["reg_number"], inventory_number=carriage["inventory_number"],
        is_active=bool(carriage["is_active"]), has_coordinates=_valid(carriage["lat"], carriage["lon"]), match=match,
        taken_by_inv_number=carriage["taken_by_inv_number"],
    )


def build_unplaced(
    rows: list[dict],
    trains: dict[str, dict],
    open_trains: dict[str, dict],
    carriages: list[dict],
    *,
    reason: str | None = None,
    asset_type: str | None = None,
    only_linkable: bool = False,
    sort_by: str = "reason",
    descending: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> AssetUnplacedPage:
    """Pure part: every asset the map cannot draw, with the reason, the source facts and (for unlinked wagons) a GTK candidate."""
    items: list[AssetUnplacedItem] = []
    for row in rows:
        if _is_placed(row, trains):
            continue
        group, detail, train = classify_unplaced(row, open_trains)
        candidate = find_gtk_candidate(row, carriages) if detail == "no_link" else None
        items.append(AssetUnplacedItem(
            **{key: row[key] for key in _COMMON}, group=group, reason=detail, asset_created_at=row.get("asset_created_at"),
            wialon_external_id=row.get("wialon_external_id"), wialon_unit_id=row.get("wialon_unit_id"),
            wialon_unit_name=row.get("wialon_unit_name"), wialon_linked_at=row.get("wialon_linked_at"),
            wialon_first_seen_at=row.get("wialon_first_seen_at"), wialon_last_message_at=row.get("wialon_last_message_at"),
            wialon_last_synced_at=row.get("wialon_last_synced_at"),
            gtk_external_id=row.get("gtk_external_id"), gtk_carriage_id=row.get("gtk_carriage_id"),
            gtk_carriage_name=row.get("gtk_carriage_name"), gtk_linked_at=row.get("gtk_linked_at"),
            gtk_first_seen_at=row.get("gtk_first_seen_at"), gtk_last_synced_at=row.get("gtk_synced_at"), gtk_is_active=row.get("gtk_is_active"),
            train_number=train["train_number"] if train else None, train_has_locomotive=train["has_locomotive"] if train else None,
            candidate=candidate,
        ))

    summary = AssetUnplacedSummary(total=len(items))
    type_counts: dict[str, TypeCount] = {}
    for item in items:
        summary.by_group[item.group] = summary.by_group.get(item.group, 0) + 1
        summary.by_reason[item.reason] = summary.by_reason.get(item.reason, 0) + 1
        entry = type_counts.setdefault(item.asset_type, TypeCount(value=item.asset_type, label=item.asset_type_name or item.asset_type, count=0))
        entry.count += 1
        if item.candidate is not None and item.candidate.match == "inv_and_reg" and item.candidate.taken_by_inv_number is None:
            summary.linkable += 1
    summary.by_type = sorted(type_counts.values(), key=lambda t: (-t.count, t.value))

    selected = [
        item for item in items
        if (reason is None or item.reason == reason or item.group == reason)
        and (asset_type is None or item.asset_type == asset_type)
        and (not only_linkable or (item.candidate is not None and item.candidate.taken_by_inv_number is None))
    ]
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    keys = {
        "inv_number": lambda i: (i.inv_number, str(i.asset_id)),
        "asset_type": lambda i: (i.asset_type, i.inv_number),
        "reason": lambda i: (_REASON_ORDER.index(i.reason), i.asset_type, i.inv_number),
        "age": lambda i: (i.asset_created_at or far_future, i.inv_number),
    }
    selected.sort(key=keys[sort_by], reverse=descending)
    return AssetUnplacedPage(items=selected[offset:offset + limit], total=len(selected), limit=limit, offset=offset, summary=summary)


async def get_unplaced(
    db: AsyncSession,
    user: User,
    *,
    reason: str | None = None,
    asset_type: str | None = None,
    section_id: UUID | None = None,
    q: str | None = None,
    only_linkable: bool = False,
    sort_by: str = "reason",
    descending: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> AssetUnplacedPage:
    if sort_by not in UNPLACED_SORT_FIELDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sort_by must be one of: " + ", ".join(sorted(UNPLACED_SORT_FIELDS)))
    scope = _master_section_scope(user)
    if scope is not None:
        section_id = scope  # a master only ever sees their own section, whatever the query says
    rows = await repository.list_asset_positions(db, asset_type=None, section_id=section_id, q=q)
    trains = await repository.list_train_positions(db)
    open_trains = await repository.list_open_train_members(db)
    carriages = await repository.list_gtk_carriages_for_matching(db)
    return build_unplaced(
        rows, trains, open_trains, carriages, reason=reason, asset_type=asset_type, only_linkable=only_linkable,
        sort_by=sort_by, descending=descending, limit=limit, offset=offset,
    )
