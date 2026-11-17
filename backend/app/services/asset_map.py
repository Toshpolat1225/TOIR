"""The asset map: where every fixed asset is, from the Wialon unit (GPS) or the GTK carriage state.

Wialon is preferred (a live GPS fix with its own time); GTK is used for assets Wialon cannot place (wagons). An
asset without a link or without coordinates is not drawn but is counted with the reason, so a gap is never silent.
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.repositories import asset_map as repository
from app.schemas.asset_map import AssetMapPoint, AssetMapRead, AssetMapSummary

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
