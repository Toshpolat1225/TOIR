"""Place the vehicles of every open GTK train along the locomotive's recent track, in GTK order, in real metres.

The locomotive's GPS fix is the head of the train. The vehicles stand one after another BEHIND it along the path the locomotive
has just travelled (its stored track), so a curve is a curve, not a straight line. Lengths are typical catalogue values: they make
the drawing the right size, they are not measurements of the individual car.
A locomotive with no recorded movement has no direction: the formation is laid out along a default heading and flagged.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_models import AssetModel
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.identity import User
from app.models.position_history import AssetPositionHistory
from app.models.wialon_units import WialonUnitRecord
from app.repositories.asset_map import LOCOMOTIVE_TYPES
from app.schemas import train_formation as f

GAP_M = 1.2
DEFAULT_HEADING = 90.0  # east, when nothing is known
MOVING_KMH = 3.0
TRAIL_POINTS = 300
ONLINE_WINDOW = timedelta(minutes=15)
MIN_STEP_M = 3.0

# (length m, width m): typical values of the fleet's vehicle types
SIZES = {
    "electric": (21.0, 3.1), "motor": (21.0, 3.1), "diesel": (17.5, 3.1), "loco": (20.0, 3.1),
    "dump": (14.5, 3.2), "tank": (12.0, 3.0), "platform": (13.8, 3.1),
}
_ELECTRIC = re.compile(r"(^|\W)(м?пэ|эл|тяговый агрегат)", re.IGNORECASE)
_TWO_SECTION_DIESEL = re.compile(r"^2т", re.IGNORECASE)


def loco_kind(asset_type: str | None, model: str | None) -> str:
    """electric (a tractive unit: locomotive + motor car) | diesel | loco (anything else self-propelled)."""
    if asset_type == "diesel":
        return "diesel"
    if model and _ELECTRIC.search(model):
        return "electric"
    return "electric" if asset_type == "locomotive" else "loco"


def wagon_kind(asset_type: str | None) -> str:
    return {"tank_car": "tank", "platform": "platform"}.get(asset_type or "", "dump")


# ───────────────────────── geometry (pure) ─────────────────────────
def to_xy(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """Metres east / north of the reference point (equirectangular: exact enough over a few hundred metres)."""
    return (math.radians(lon - lon0) * 6_371_000 * math.cos(math.radians(lat0)), math.radians(lat - lat0) * 6_371_000)


def from_xy(lat0: float, lon0: float, x: float, y: float) -> tuple[float, float]:
    return lat0 + math.degrees(y / 6_371_000), lon0 + math.degrees(x / (6_371_000 * math.cos(math.radians(lat0))))


def bearing(dx: float, dy: float) -> float:
    return (math.degrees(math.atan2(dx, dy)) + 360) % 360


def build_path(trail: list[tuple[float, float]], lat0: float, lon0: float) -> list[tuple[float, float]]:
    """Trail points (newest first, lat/lon) -> metres, without consecutive duplicates (< MIN_STEP_M apart)."""
    path: list[tuple[float, float]] = []
    for lat, lon in trail:
        p = to_xy(lat0, lon0, lat, lon)
        if not path or math.hypot(p[0] - path[-1][0], p[1] - path[-1][1]) >= MIN_STEP_M:
            path.append(p)
    return path


def place_along(path: list[tuple[float, float]], distances: list[float], fallback_heading: float) -> list[tuple[float, float, float]]:
    """(x, y, heading) at each distance behind the head of `path` (path[0] = newest).

    heading = the direction of travel at that spot (from the older point towards the newer). Past the end of the path the last
    segment is extended backwards; a single-point path uses the fallback heading.
    """
    if not path:
        return []
    segs: list[tuple[float, float, float, float, float, float]] = []  # (start distance, length, x, y of the newer end, unit vector towards the older end)
    total = 0.0
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        segs.append((total, length, x1, y1, (x2 - x1) / length, (y2 - y1) / length))
        total += length
    out: list[tuple[float, float, float]] = []
    if not segs:
        ux, uy = -math.sin(math.radians(fallback_heading)), -math.cos(math.radians(fallback_heading))  # backwards from the heading
        return [(path[0][0] + ux * d, path[0][1] + uy * d, fallback_heading) for d in distances]
    for d in distances:
        seg = next((s for s in segs if d <= s[0] + s[1]), segs[-1])  # past the end: the last segment, extended
        start, _length, x1, y1, ux, uy = seg
        along = d - start
        out.append((x1 + ux * along, y1 + uy * along, bearing(-ux, -uy)))
    return out


@dataclass(frozen=True)
class Spec:
    role: str
    kind: str
    length: float
    width: float


def formation_specs(kind: str, model: str | None, wagon_kinds: list[str]) -> list[Spec]:
    """The vehicle sequence: the locomotive (a tractive unit adds its motor car), then the cars in GTK order."""
    specs: list[Spec] = []
    length, width = SIZES[kind]
    if kind == "diesel" and model and _TWO_SECTION_DIESEL.search(model):
        specs += [Spec("loco", "diesel", 18.0, width), Spec("motor", "diesel", 18.0, width)]  # a two-section diesel
    else:
        specs.append(Spec("loco", kind, length, width))
        if kind == "electric":
            specs.append(Spec("motor", "motor", *SIZES["motor"]))
    for w in wagon_kinds:
        specs.append(Spec("wagon", w, *SIZES[w]))
    return specs


def centre_distances(specs: list[Spec]) -> list[float]:
    """Distance of every vehicle's centre behind the head (the locomotive's GPS point is the centre of the first section)."""
    distances = [0.0]
    for prev, nxt in zip(specs, specs[1:]):
        distances.append(distances[-1] + prev.length / 2 + GAP_M + nxt.length / 2)
    return distances


def build_formation(
    *, trail: list[tuple[float, float]], lat: float, lon: float, kind: str, model: str | None, wagon_kinds: list[str],
) -> tuple[list[tuple[Spec, float, float, float]], float, bool]:
    """-> ([(spec, lat, lon, heading)], train heading, heading_known). `trail` is newest first and ends at/near (lat, lon)."""
    specs = formation_specs(kind, model, wagon_kinds)
    path = build_path([(lat, lon), *trail], lat, lon)
    known = len(path) >= 2
    placed = place_along(path, centre_distances(specs), DEFAULT_HEADING)
    out = []
    for spec, (x, y, heading) in zip(specs, placed):
        vlat, vlon = from_xy(lat, lon, x, y)
        out.append((spec, vlat, vlon, heading))
    return out, out[0][3], known


# ───────────────────────── database ─────────────────────────
def _scope(user: User):
    if user.role != "master":
        return None
    if user.section_id is None:
        raise HTTPException(status_code=403, detail="Master user must be assigned to a section")
    return user.section_id


async def live_trains(db: AsyncSession, user: User) -> f.LiveTrains:
    scope = _scope(user)
    now = datetime.now(timezone.utc)
    trains = (await db.execute(select(GtkTrain).where(GtkTrain.is_open))).scalars().all()
    ids = [t.gtk_id for t in trains]
    if not ids:
        return f.LiveTrains(generated_at=now, trains=[])
    members = (await db.execute(select(GtkTrainMember).where(GtkTrainMember.train_gtk_id.in_(ids), GtkTrainMember.observed_to.is_(None)))).scalars().all()
    main_loco: dict[int, int] = {}
    cars: dict[int, list[GtkTrainMember]] = defaultdict(list)
    for m in members:
        if m.kind == "locomotive" and m.is_main:
            main_loco[m.train_gtk_id] = m.object_gtk_id
        elif m.kind == "carriage":
            cars[m.train_gtk_id].append(m)

    # locomotives: GTK loco -> asset -> Wialon unit
    gtk_locos = {g.gtk_id: g for g in (await db.execute(select(GtkLocomotive).where(GtkLocomotive.gtk_id.in_(set(main_loco.values()))))).scalars().all()} if main_loco else {}
    link_rows = (
        await db.execute(
            select(AssetSourceLink.source, AssetSourceLink.external_id, AssetSourceLink.asset_id, FixedAsset.asset_type, FixedAsset.inv_number, FixedAsset.section_id, AssetModel.name)
            .join(FixedAsset, FixedAsset.id == AssetSourceLink.asset_id).outerjoin(AssetModel, AssetModel.id == FixedAsset.model_id)
            .where(AssetSourceLink.status == "active", AssetSourceLink.source.in_(("gtk", "wialon")))
        )
    ).all()
    loco_asset: dict[int, tuple] = {}
    car_asset: dict[int, tuple] = {}
    wialon_unit: dict[UUID, str] = {}
    for source, ext, asset, atype, inv, section, model in link_rows:
        if source == "wialon":
            wialon_unit[asset] = ext
        elif str(ext).isdigit():
            (loco_asset if atype in LOCOMOTIVE_TYPES else car_asset)[int(ext)] = (asset, atype, inv, section, model)
    units = {u.unit_id: u for u in (await db.execute(select(WialonUnitRecord).where(WialonUnitRecord.unit_id.in_(set(wialon_unit.values()))))).scalars().all()} if wialon_unit else {}
    car_ids = {c.object_gtk_id for lst in cars.values() for c in lst}
    gtk_cars = {c.gtk_id: c for c in (await db.execute(select(GtkCarriage).where(GtkCarriage.gtk_id.in_(car_ids)))).scalars().all()} if car_ids else {}

    # the recent track of each locomotive (newest first)
    loco_assets = {loco_asset[g][0] for g in main_loco.values() if g in loco_asset}
    trails: dict[UUID, list[tuple[float, float]]] = defaultdict(list)
    if loco_assets:
        ranked = (
            select(AssetPositionHistory.asset_id, AssetPositionHistory.lat, AssetPositionHistory.lon,
                   func.row_number().over(partition_by=AssetPositionHistory.asset_id, order_by=AssetPositionHistory.at.desc()).label("rn"))
            .where(AssetPositionHistory.asset_id.in_(loco_assets), AssetPositionHistory.source == "wialon").subquery()
        )
        for asset, lat, lon, _rn in (await db.execute(select(ranked.c.asset_id, ranked.c.lat, ranked.c.lon, ranked.c.rn).where(ranked.c.rn <= TRAIL_POINTS).order_by(ranked.c.asset_id, ranked.c.rn))).all():
            trails[asset].append((float(lat), float(lon)))

    out: list[f.LiveTrain] = []
    for t in trains:
        gid = main_loco.get(t.gtk_id)
        if gid is None or gid not in loco_asset:
            continue
        asset, atype, inv, section, model = loco_asset[gid]
        unit = units.get(wialon_unit.get(asset, ""))
        if unit is None or unit.lat is None or unit.lon is None or (float(unit.lat) == 0 and float(unit.lon) == 0):
            continue
        ordered = sorted(cars.get(t.gtk_id, []), key=lambda m: m.ord)
        kinds, infos = [], []
        for m in ordered:
            info = car_asset.get(m.object_gtk_id)
            kinds.append(wagon_kind(info[1] if info else None))
            infos.append((m, info, gtk_cars.get(m.object_gtk_id)))
        gtk_model = gtk_locos[gid].model_name if gid in gtk_locos else None
        model_name = model or gtk_model
        kind = loco_kind(atype, model_name)
        built, heading, known = build_formation(trail=trails.get(asset, []), lat=float(unit.lat), lon=float(unit.lon), kind=kind, model=model_name, wagon_kinds=kinds)
        in_scope = scope is None or section == scope
        if scope is not None and not in_scope and not any(i[1] and i[1][3] == scope for i in infos):
            continue
        vehicles: list[f.FormationVehicle] = []
        car_iter = iter(infos)
        for spec, vlat, vlon, vheading in built:
            if spec.role == "wagon":
                m, info, carriage = next(car_iter)
                visible = scope is None or (info is not None and info[3] == scope)
                vehicles.append(f.FormationVehicle(
                    role="wagon", kind=spec.kind, ord=m.ord, asset_id=info[0] if info and visible else None, carriage_gtk_id=m.object_gtk_id if visible else None,
                    label=(info[2] if info else (carriage.inventory_number or carriage.name if carriage else None)) if visible else None, lat=vlat, lon=vlon,
                    heading=vheading, length_m=spec.length, width_m=spec.width, is_loaded=carriage.is_loaded if carriage else None, hidden=not visible,
                ))
            else:
                vehicles.append(f.FormationVehicle(
                    role=spec.role, kind=spec.kind, ord=0 if spec.role == "loco" else -1, asset_id=asset if in_scope else None, carriage_gtk_id=None,
                    label=inv if in_scope else None, lat=vlat, lon=vlon, heading=vheading, length_m=spec.length, width_m=spec.width, hidden=not in_scope,
                ))
        speed = float(unit.speed) if unit.speed is not None else None
        length = round(sum(v.length_m for v in vehicles) + GAP_M * (len(vehicles) - 1), 1)
        out.append(f.LiveTrain(
            gtk_train_id=t.gtk_id, number=t.number, title=t.title, loco_asset_id=asset if in_scope else None, loco_inv_number=inv if in_scope else None,
            loco_name=(gtk_locos[gid].name if gid in gtk_locos else None) if in_scope else None, loco_model=model_name, loco_kind=kind if kind in ("electric", "diesel") else "loco",
            lat=float(unit.lat), lon=float(unit.lon), speed=speed, online=bool(unit.last_message_at and now - unit.last_message_at <= ONLINE_WINDOW) if unit.last_message_at else None,
            position_at=unit.position_at, heading=round(heading, 1), heading_known=known, moving=speed is not None and speed >= MOVING_KMH,
            wagons_count=len(ordered), length_m=length, vehicles=vehicles,
        ))
    out.sort(key=lambda x: -x.wagons_count)
    return f.LiveTrains(generated_at=now, trains=out)
