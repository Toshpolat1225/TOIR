// Pure helpers of the map command center and the asset history page. No React.
// Run the tests with: npm run test:unit

import { isTracked, type MapPoint } from "./map-view.ts"
import type { AssetIdentity, GtkCarriageInfo, GtkLocoInfo, Num } from "./scales-insights.ts"

export type HistoryPoint = { at: string; lat: number; lon: number; speed: number | null; source: "own" | "loco"; label: string | null }
export type WagonRef = { carriage_gtk_id: number; asset_id: string | null; label: string }
export type HistorySegment = {
  from_at: string; to_at: string | null; is_open: boolean; train_gtk_id: number; train_title: string | null
  loco_asset_id: string | null; loco_inv_number: string | null; loco_label: string | null; cars: number; km: number | null
  max_speed: number | null; points: number; activity: "moving" | "standing" | "unknown"; trips: number; tonnes: Num; wagons: WagonRef[]
}
export type HistoryTrip = {
  train_id: string; started_at: string | null; post_code: string; tonnes: Num | null; basis: string | null
  loco_number: string | null; cargo_name: string | null; cars: number | null
}
export type LocoShare = { loco_asset_id: string | null; label: string; hours: number; segments: number }
export type HistoryCurrent = { lat: number; lon: number; at: string; source: "own" | "loco"; in_train: boolean; loco_label: string | null; speed: number | null }
export type HistoryStats = { segments: number; coupled_hours: number; km: number; distinct_partners: number; trips: number; tonnes: Num; last_move_at: string | null }
export type AssetHistory = {
  kind: "wagon" | "locomotive"; asset: AssetIdentity | null; gtk_carriage: GtkCarriageInfo | null; gtk_loco: GtkLocoInfo | null
  date_from: string; date_to: string; days: number; gtk_history_from: string | null; track_from: string | null
  current: HistoryCurrent | null; segments: HistorySegment[]; trips: HistoryTrip[]; track: HistoryPoint[]; by_loco: LocoShare[]; stats: HistoryStats
}

export const LOCOMOTIVE_TYPES = ["locomotive", "diesel", "special_self_propelled"]
export const isLocomotive = (assetType: string): boolean => LOCOMOTIVE_TYPES.includes(assetType)
export const MOVING_KMH = 3

// ── history page ──
export function hoursText(hours: number): string {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} мин`
  if (hours < 48) return `${hours.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} ч`
  return `${(hours / 24).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} сут`
}

export const kmText = (km: number | null | undefined): string => (km === null || km === undefined ? "—" : `${km.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} км`)

export const ACTIVITY_LABEL: Record<HistorySegment["activity"], string> = {
  moving: "двигался", standing: "стоял", unknown: "положение не записано",
}

export function segmentHours(s: Pick<HistorySegment, "from_at" | "to_at">, now = Date.now()): number {
  const end = s.to_at ? new Date(s.to_at).getTime() : now
  return Math.max(0, (end - new Date(s.from_at).getTime()) / 3_600_000)
}

/** One plain sentence about a stretch of the timeline: with whom, for how long, what it did. */
export function segmentSentence(kind: "wagon" | "locomotive", s: HistorySegment, now = Date.now()): string {
  const duration = hoursText(segmentHours(s, now))
  const what = s.activity === "moving" ? `за это время прошёл ${kmText(s.km)}${s.max_speed ? `, максимум ${Math.round(s.max_speed)} км/ч` : ""}` : s.activity === "standing" ? "стоял на месте" : "положение за это время не записано"
  if (kind === "wagon") {
    const loco = s.loco_label ? `за локомотивом ${s.loco_label}` : "локомотив не определён"
    return `${s.is_open ? "Сейчас" : "Был"} в составе (${s.cars} ваг.) ${loco}, ${duration}: ${what}.`
  }
  return `${s.is_open ? "Сейчас тянет" : "Тянул"} состав из ${s.cars} вагонов, ${duration}: ${what}.`
}

/** The track point at or just before a moment: «where was it at 14:35?». */
export function pointAt(track: HistoryPoint[], when: number): HistoryPoint | null {
  let found: HistoryPoint | null = null
  for (const p of track) {
    if (new Date(p.at).getTime() <= when) found = p
    else break
  }
  return found ?? track[0] ?? null
}

/** The segment a moment falls into, if any. */
export function segmentAt(segments: HistorySegment[], when: number, now = Date.now()): HistorySegment | null {
  return segments.find((s) => new Date(s.from_at).getTime() <= when && when <= (s.to_at ? new Date(s.to_at).getTime() : now)) ?? null
}

export function historyBounds(track: HistoryPoint[]): [[number, number], [number, number]] | null {
  if (track.length === 0) return null
  const lats = track.map((p) => p.lat)
  const lons = track.map((p) => p.lon)
  return [[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]]
}

export const SEGMENT_COLORS = ["#2563eb", "#f59e0b", "#10b981", "#a855f7", "#ef4444", "#0ea5e9", "#84cc16", "#ec4899"]
export const segmentColor = (index: number): string => SEGMENT_COLORS[index % SEGMENT_COLORS.length]

export function historyNote(h: Pick<AssetHistory, "gtk_history_from" | "track_from" | "days">): string[] {
  const notes: string[] = []
  const d = (iso: string) => new Date(iso).toLocaleDateString("ru-RU")
  if (h.gtk_history_from) notes.push(`Состав (с каким локомотивом стоял вагон) известен с ${d(h.gtk_history_from)}: GTK до этого не передавал историю.`)
  if (h.track_from) notes.push(`Положение на карте записано с ${d(h.track_from)}.`)
  else notes.push("Позиции пока не записывались: трек появится после ближайших обновлений Wialon (каждые 2 минуты).")
  return notes
}

export function historyHref(p: { asset_id: string | null; carriage_gtk_id?: number | null }): string {
  return `/dashboard/map/history/${p.asset_id ?? `gtk-${p.carriage_gtk_id}`}`
}

// ── the map command center ──
export type TrainOnLine = {
  key: string; locoId: string | null; locoName: string; locoInv: string | null; locoPoint: MapPoint | null
  wagons: MapPoint[]; speed: number | null; moving: boolean; lat: number; lon: number; positionAt: string | null; online: boolean | null
}

const speedOf = (p: Pick<MapPoint, "speed">): number | null => (p.speed === null || p.speed === undefined || p.speed === "" ? null : Number(p.speed))

/** Group the wagons drawn at a locomotive (source «train») into trains, joined with the locomotive's own point when it is on the map. */
export function buildTrains(points: MapPoint[]): TrainOnLine[] {
  const locos = new Map(points.filter((p) => isLocomotive(p.asset_type) && isTracked(p.source)).map((p) => [p.asset_id, p]))
  const groups = new Map<string, MapPoint[]>()
  for (const p of points) {
    if (p.source !== "train" || !p.locomotive_asset_id) continue
    const list = groups.get(p.locomotive_asset_id) ?? []
    list.push(p)
    groups.set(p.locomotive_asset_id, list)
  }
  const trains: TrainOnLine[] = []
  for (const [locoId, wagons] of groups) {
    const loco = locos.get(locoId) ?? null
    const first = wagons[0]
    const speed = loco ? speedOf(loco) : null
    trains.push({
      key: locoId, locoId, locoName: loco?.name ?? first.locomotive_name ?? "Локомотив", locoInv: loco?.inv_number ?? first.locomotive_inv_number ?? null, locoPoint: loco,
      wagons: wagons.sort((a, b) => a.inv_number.localeCompare(b.inv_number)), speed, moving: speed !== null && speed >= MOVING_KMH,
      lat: loco?.lat ?? first.lat, lon: loco?.lon ?? first.lon, positionAt: loco?.position_at ?? first.position_at ?? null, online: loco?.online ?? null,
    })
  }
  return trains.sort((a, b) => b.wagons.length - a.wagons.length)
}

export type FleetStats = {
  placed: number; online: number; moving: number; silent24h: number; trains: number; wagonsInTrains: number
  byType: { key: string; label: string; count: number }[]; bySection: { key: string; label: string; count: number }[]
}

export function fleetStats(points: MapPoint[], now = Date.now()): FleetStats {
  let online = 0, moving = 0, silent = 0
  const types = new Map<string, { label: string; count: number }>()
  const sections = new Map<string, number>()
  for (const p of points) {
    if (isTracked(p.source)) {
      if (p.online) online++
      const s = speedOf(p)
      if (s !== null && s >= MOVING_KMH) moving++
      if (p.position_at && now - new Date(p.position_at).getTime() > 24 * 3_600_000) silent++
    }
    const t = types.get(p.asset_type) ?? { label: p.asset_type_name ?? p.asset_type, count: 0 }
    t.count++
    types.set(p.asset_type, t)
    const section = p.section_name ?? "Без участка"
    sections.set(section, (sections.get(section) ?? 0) + 1)
  }
  const trains = buildTrains(points)
  return {
    placed: points.length, online, moving, silent24h: silent, trains: trains.length, wagonsInTrains: trains.reduce((n, t) => n + t.wagons.length, 0),
    byType: [...types.entries()].map(([key, v]) => ({ key, ...v })).sort((a, b) => b.count - a.count),
    bySection: [...sections.entries()].map(([key, count]) => ({ key, label: key, count })).sort((a, b) => b.count - a.count),
  }
}

export function movementText(p: Pick<MapPoint, "source" | "speed" | "online">): string {
  if (p.source === "gtk") return "положение по GTK"
  if (p.source === "train") return "едет/стоит вместе с составом"
  const s = speedOf(p)
  if (!p.online) return "нет связи"
  return s !== null && s >= MOVING_KMH ? `едет, ${Math.round(s)} км/ч` : "стоит"
}
