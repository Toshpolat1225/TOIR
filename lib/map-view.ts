// Pure helpers of the asset map page (no React, no Google): labels, colours, links, filtering, bounds.
// Run the tests with: npm run test:unit

// "train" = a wagon has no GPS: it is drawn where the locomotive of its open GTK train is
export type MapSource = "wialon" | "gtk" | "train"

export type MapPoint = {
  asset_id: string
  inv_number: string
  name: string
  asset_type: string
  asset_type_name?: string | null
  status: string
  status_name?: string | null
  section_id?: string | null
  section_name?: string | null
  model_name?: string | null
  lat: number
  lon: number
  source: MapSource
  position_at?: string | null
  speed?: number | string | null
  online?: boolean | null
  train_number?: string | null
  locomotive_asset_id?: string | null
  locomotive_inv_number?: string | null
  locomotive_name?: string | null
}

export const SOURCE_LABEL: Record<MapSource, string> = { wialon: "Wialon (GPS)", gtk: "GTK", train: "Состав (по локомотиву)" }

export const UNPLACED_LABEL: Record<string, string> = {
  no_link: "нет привязки к Wialon/GTK",
  no_position: "привязан, но координат нет",
}

/** Marker colours: Wialon online = green, Wialon silent = grey, GTK = blue, wagon in a train = orange. */
export function markerColor(point: Pick<MapPoint, "source" | "online">): string {
  if (point.source === "gtk") return "#2563eb"
  if (point.source === "train") return "#d97706"
  return point.online ? "#16a34a" : "#6b7280"
}

/** A keyless link that opens the point in Google Maps. */
export function googleMapsLink(lat: number, lon: number): string {
  return `https://www.google.com/maps?q=${lat.toFixed(6)},${lon.toFixed(6)}`
}

/** A keyless Google Maps embed (one point), usable in an iframe without an API key. */
export function googleEmbedUrl(lat: number, lon: number, zoom = 14): string {
  return `https://www.google.com/maps?q=${lat.toFixed(6)},${lon.toFixed(6)}&z=${zoom}&output=embed`
}

/** "В составе № T-1 · локомотив 37017" for a wagon drawn at its locomotive, otherwise null. */
export function trainText(p: Pick<MapPoint, "source" | "train_number" | "locomotive_inv_number" | "locomotive_name">): string | null {
  if (p.source !== "train") return null
  const train = p.train_number ? ` № ${p.train_number}` : ""
  const loco = p.locomotive_inv_number ? ` · локомотив ${p.locomotive_inv_number}${p.locomotive_name ? ` (${p.locomotive_name})` : ""}` : ""
  return `В составе${train}${loco}`
}

export function filterPoints(points: MapPoint[], opts: { q?: string; type?: string; source?: MapSource | "" }): MapPoint[] {
  const needle = (opts.q ?? "").trim().toLowerCase()
  return points.filter((p) => {
    if (opts.type && p.asset_type !== opts.type) return false
    if (opts.source && p.source !== opts.source) return false
    if (needle && !`${p.inv_number} ${p.name} ${p.section_name ?? ""} ${p.train_number ?? ""} ${p.locomotive_inv_number ?? ""}`.toLowerCase().includes(needle)) return false
    return true
  })
}

export type Bounds = { south: number; west: number; north: number; east: number }

/** The box around the points, or null when there are none. Wagons parked abroad stretch it: callers may fit it. */
export function boundsOf(points: Pick<MapPoint, "lat" | "lon">[]): Bounds | null {
  if (points.length === 0) return null
  let south = 90, north = -90, west = 180, east = -180
  for (const p of points) {
    south = Math.min(south, p.lat)
    north = Math.max(north, p.lat)
    west = Math.min(west, p.lon)
    east = Math.max(east, p.lon)
  }
  return { south, west, north, east }
}

/** "5 мин назад" / "3 ч назад" / "2 дн назад" for the age of a position. */
export function ageText(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "время неизвестно"
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return "время неизвестно"
  const minutes = Math.max(0, Math.round((now.getTime() - then) / 60000))
  if (minutes < 1) return "только что"
  if (minutes < 60) return `${minutes} мин назад`
  if (minutes < 60 * 48) return `${Math.round(minutes / 60)} ч назад`
  return `${Math.round(minutes / 1440)} дн назад`
}

export function typeOptions(points: MapPoint[]): { value: string; label: string; count: number }[] {
  const byType = new Map<string, { label: string; count: number }>()
  for (const p of points) {
    const entry = byType.get(p.asset_type) ?? { label: p.asset_type_name || p.asset_type, count: 0 }
    entry.count += 1
    byType.set(p.asset_type, entry)
  }
  return [...byType.entries()].map(([value, e]) => ({ value, label: e.label, count: e.count })).sort((a, b) => b.count - a.count)
}
