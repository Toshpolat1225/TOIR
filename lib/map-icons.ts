// Icons and true-scale geometry of the map: pictograms per vehicle type, and the corners of a vehicle drawn in metres. No React.
// Run the tests with: npm run test:unit

import type { MapPoint } from "./map-view.ts"

export type IconKind = "electric" | "diesel" | "loco" | "dump" | "tank" | "platform" | "other"
export type FormationVehicle = {
  role: "loco" | "motor" | "wagon"; kind: "electric" | "diesel" | "loco" | "motor" | "dump" | "tank" | "platform"; ord: number
  asset_id: string | null; carriage_gtk_id: number | null; label: string | null; lat: number; lon: number; heading: number
  length_m: number; width_m: number; is_loaded: boolean | null; hidden: boolean
}
export type LiveTrain = {
  gtk_train_id: number; number: string | null; title: string | null; loco_asset_id: string | null; loco_inv_number: string | null
  loco_name: string | null; loco_model: string | null; loco_kind: "electric" | "diesel" | "loco"; lat: number; lon: number
  speed: number | null; online: boolean | null; position_at: string | null; heading: number; heading_known: boolean; moving: boolean
  wagons_count: number; length_m: number; vehicles: FormationVehicle[]
}
export type LiveTrains = { generated_at: string; trains: LiveTrain[] }

/** From this zoom level a train is drawn to scale (every vehicle in metres); below it the train is one pictogram with a car count. */
export const TRUE_SCALE_ZOOM = 16

export function iconKind(p: Pick<MapPoint, "asset_type" | "model_name">): IconKind {
  if (p.asset_type === "diesel") return "diesel"
  if (p.asset_type === "locomotive") return "electric"
  if (p.asset_type === "special_self_propelled") return /(^|\W)(м?пэ|эл)/i.test(p.model_name ?? "") ? "electric" : "loco"
  if (p.asset_type === "tank_car") return "tank"
  if (p.asset_type === "platform") return "platform"
  if (p.asset_type === "wagon") return "dump"
  return "other"
}

export const KIND_LABEL: Record<IconKind, string> = {
  electric: "Электровоз (тяговый агрегат)", diesel: "Тепловоз", loco: "Спецтехника на ходу", dump: "Вагон-самосвал", tank: "Цистерна", platform: "Платформа", other: "Прочее",
}
export const KIND_COLOR: Record<IconKind, string> = {
  electric: "#2563eb", diesel: "#d97706", loco: "#7c3aed", dump: "#92400e", tank: "#0e7490", platform: "#64748b", other: "#475569",
}

export type Status = "online" | "offline" | "gtk" | "train"
export const STATUS_COLOR: Record<Status, string> = { online: "#16a34a", offline: "#9ca3af", gtk: "#3b82f6", train: "#f59e0b" }

export function statusOf(p: Pick<MapPoint, "source" | "online">): Status {
  if (p.source === "gtk") return "gtk"
  if (p.source === "train") return "train"
  return p.online ? "online" : "offline"
}

const WHEELS = '<circle cx="10" cy="20.5" r="2.3" fill="#0f172a"/><circle cx="30" cy="20.5" r="2.3" fill="#0f172a"/>'
const STROKE = 'stroke="#0f172a" stroke-width="1.2"'

/** Side-view pictogram, 40x24. `status` is the small dot at the corner (green online, grey offline, blue GTK, amber with a train). */
export function iconSvg(kind: IconKind, status: Status, width = 36, selected = false, verdictColor: string | null = null): string {
  const c = KIND_COLOR[kind]
  const body: Record<IconKind, string> = {
    electric: `<rect x="3" y="7" width="34" height="11" rx="3" fill="${c}" ${STROKE}/><rect x="6" y="9" width="6" height="4" rx="1" fill="#bfdbfe"/><rect x="28" y="9" width="6" height="4" rx="1" fill="#bfdbfe"/><path d="M15 7 L20 1.5 L25 7" fill="none" stroke="#0f172a" stroke-width="1.5"/><path d="M17.5 1.5h5" stroke="#0f172a" stroke-width="1.5"/><path d="M21 9.5 l-3 4 h3 l-1 4 4-5 h-3z" fill="#fde047"/>${WHEELS}`,
    diesel: `<rect x="3" y="8" width="34" height="10" rx="2" fill="${c}" ${STROKE}/><rect x="3" y="4.5" width="12" height="6" rx="1.5" fill="${c}" ${STROKE}/><rect x="5.5" y="6" width="6" height="3" rx=".8" fill="#fef3c7"/><rect x="25" y="3.5" width="3.2" height="5" fill="#0f172a"/><path d="M21 10.5c2.4 3 3.5 4.4 3.5 5.8a3.5 3.5 0 0 1-7 0c0-1.4 1.1-2.8 3.5-5.8z" fill="#fde68a"/>${WHEELS}`,
    loco: `<rect x="3" y="7" width="34" height="11" rx="3" fill="${c}" ${STROKE}/><rect x="6" y="9" width="7" height="4" rx="1" fill="#e9d5ff"/><path d="M20 10h12M20 14h12" stroke="#fff" stroke-width="1.6"/>${WHEELS}`,
    dump: `<path d="M4 5.5 H36 L32 17 H8 Z" fill="${c}" ${STROKE}/><path d="M13 6 L15 17M20 6 V17M27 6 L25 17" stroke="#fde68a" stroke-width="1.1" opacity=".8"/><rect x="2" y="17" width="36" height="2" fill="#0f172a"/>${WHEELS}`,
    tank: `<rect x="4" y="6.5" width="32" height="11" rx="5.5" fill="${c}" ${STROKE}/><rect x="17" y="3.5" width="6" height="3.5" rx="1" fill="${c}" ${STROKE}/><rect x="2" y="17.5" width="36" height="1.8" fill="#0f172a"/>${WHEELS}`,
    platform: `<rect x="3" y="13" width="34" height="4" fill="${c}" ${STROKE}/><path d="M6 13V8M14 13V8M26 13V8M34 13V8" stroke="${c}" stroke-width="2"/><rect x="2" y="17" width="36" height="1.8" fill="#0f172a"/>${WHEELS}`,
    other: `<rect x="8" y="5" width="24" height="14" rx="3" fill="${c}" ${STROKE}/>`,
  }
  const ring = selected ? '<rect x="0.5" y="0.5" width="39" height="23" rx="5" fill="none" stroke="#ef4444" stroke-width="2"/>' : ""
  // locomotives with two trackers: a coloured ring at the opposite corner = the verdict of comparing Wialon and GTK GPS
  const verdict = verdictColor ? `<circle cx="5" cy="4.5" r="3.4" fill="#fff" stroke="${verdictColor}" stroke-width="2.2"/>` : ""
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 24" width="${width}" height="${Math.round((width * 24) / 40)}">${body[kind]}${ring}${verdict}<circle cx="35" cy="4.5" r="3.6" fill="${STATUS_COLOR[status]}" stroke="#fff" stroke-width="1.2"/></svg>`
}

/** Icon width in pixels for a zoom level: small on the country view, larger when the viewer is close. */
export const iconWidth = (zoom: number, kind: IconKind): number => {
  const loco = kind === "electric" || kind === "diesel" || kind === "loco"
  const base = zoom <= 7 ? 24 : zoom <= 11 ? 30 : 38
  return loco ? base + 6 : base
}

// ── metres on the ground ──
const R = 6_371_000
export const metersPerPixel = (lat: number, zoom: number): number => (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom

/** The point `east`/`north` metres from (lat, lon). */
export function offset(lat: number, lon: number, east: number, north: number): [number, number] {
  return [lat + (north / R) * (180 / Math.PI), lon + (east / (R * Math.cos((lat * Math.PI) / 180))) * (180 / Math.PI)]
}

type Frame = { f: [number, number]; r: [number, number] }
const frame = (heading: number): Frame => {
  const h = (heading * Math.PI) / 180
  return { f: [Math.sin(h), Math.cos(h)], r: [Math.cos(h), -Math.sin(h)] } // forward and right as (east, north)
}
const at = (lat: number, lon: number, fr: Frame, along: number, across: number): [number, number] =>
  offset(lat, lon, fr.f[0] * along + fr.r[0] * across, fr.f[1] * along + fr.r[1] * across)

/** Rectangle of a vehicle: rear-left, rear-right, front-right, front-left (heading = direction of travel, front is ahead). */
export function vehicleCorners(lat: number, lon: number, heading: number, length: number, width: number): [number, number][] {
  const fr = frame(heading), l = length / 2, w = width / 2
  return [at(lat, lon, fr, -l, -w), at(lat, lon, fr, -l, w), at(lat, lon, fr, l, w), at(lat, lon, fr, l, -w)]
}

/** A locomotive outline: a rectangle with a chamfered nose, so the direction of travel is visible. */
export function locoOutline(lat: number, lon: number, heading: number, length: number, width: number): [number, number][] {
  const fr = frame(heading), l = length / 2, w = width / 2, cut = Math.min(2, length * 0.1)
  return [at(lat, lon, fr, -l, -w), at(lat, lon, fr, -l, w), at(lat, lon, fr, l - cut, w), at(lat, lon, fr, l, 0), at(lat, lon, fr, l - cut, -w)]
}

/** A strip across the vehicle (a window, a rib, an arm of the pantograph): from `a` to `b` metres along, `across` metres wide on each side. */
export function strip(lat: number, lon: number, heading: number, a: number, b: number, across: number): [number, number][] {
  const fr = frame(heading)
  return [at(lat, lon, fr, a, -across), at(lat, lon, fr, a, across), at(lat, lon, fr, b, across), at(lat, lon, fr, b, -across)]
}

export function vehicleFill(kind: FormationVehicle["kind"], loaded: boolean | null): string {
  if (kind === "dump") return loaded ? "#78350f" : "#b45309"
  return { electric: "#2563eb", diesel: "#d97706", loco: "#7c3aed", motor: "#475569", tank: "#0e7490", platform: "#64748b" }[kind]
}

export function trainBounds(train: LiveTrain): [[number, number], [number, number]] {
  const lats = train.vehicles.flatMap((v) => [v.lat]), lons = train.vehicles.flatMap((v) => [v.lon])
  const pad = 0.0002
  return [[Math.min(...lats) - pad, Math.min(...lons) - pad], [Math.max(...lats) + pad, Math.max(...lons) + pad]]
}

export const trainCaption = (t: LiveTrain): string =>
  `${t.loco_inv_number ?? "локомотив"}${t.loco_name ? ` ${t.loco_name}` : ""} · ${t.wagons_count} вагонов · ${Math.round(t.length_m)} м${t.moving ? ` · едет ${Math.round(t.speed ?? 0)} км/ч` : " · стоит"}`
