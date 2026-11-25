import { fmtPercent } from "./format.ts"
// Pure helpers of the GPS comparison pages (Wialon vs GTK): contract types, Russian labels, colours, formatting and chart geometry. No React.
// Run the tests with: npm run test:unit

import type { MapPoint } from "./map-view.ts"

// ---- contract (backend/app/schemas/gps.py, services/gps_compare.py) ------------------------------------------------
export type PositionVerdict =
  | "confirmed" | "diverged" | "gtk_stale" | "wialon_stale" | "both_stale_agree" | "both_stale_apart" | "wialon_only" | "gtk_only" | "no_position"
export type DistanceVerdict = "match" | "minor_diff" | "gtk_gap" | "wialon_gap" | "idle" | "no_data" | "not_collected"

export type GpsFix = { lat: number; lon: number; at?: string | null; speed?: number | null; age_min?: number | null; fresh: boolean }
export type GpsPositionCheck = { verdict: PositionVerdict; diff_m?: number | null; lag_s?: number | null; tolerance_m?: number | null; best?: "wialon" | "gtk" | null }

export type CauseCode =
  | "ok" | "method" | "day_open" | "gtk_dead" | "gtk_no_day" | "gtk_gaps" | "gtk_sparse" | "wialon_gaps" | "both_gaps" | "not_collected" | "idle" | "no_data"
export type HealthClass = "ok" | "intermittent" | "dead" | "frozen" | "no_gtk"
export type Confidence = "high" | "medium" | "low" | "none"
export type WagonFlag = "two_trains" | "stale_membership" | "loco_silent" | "no_loco" | "no_history"
export type WagonBasis = "fused_track" | "track" | "odometer" | "conflict" | "single_source" | "held"

export type GpsDayRow = {
  day: string; wialon_m?: number | null; wialon_points: number; gtk_m?: number | null; gtk_points: number; gtk_raw_points: number; gtk_final: boolean
  verdict: DistanceVerdict; ratio?: number | null; diff_m?: number | null; unified_m?: number | null; idle_events?: number | null; odo_m?: number | null; odo_agrees?: boolean | null
  cause?: CauseCode | string; fused_m?: number | null; unknown_gap_m?: number | null; wialon_cov_h?: number | null; gtk_cov_h?: number | null
  confidence?: number | null; explanation?: string | null
}
export type GpsHealth = {
  health_class: HealthClass; window_days: number; active_days: number; ok_days: number; partial_days: number; none_days: number
  last_gtk_fix_age_h?: number | null; km_lost_m: number; ok_share?: number | null
}
export type GpsAssetRow = {
  asset_id: string; inv_number: string; name: string; asset_type: string; asset_type_name?: string | null; model_name?: string | null
  section_id?: string | null; section_name?: string | null; wialon_linked: boolean; gtk_linked: boolean
  wialon: GpsFix | null; gtk: GpsFix | null; position: GpsPositionCheck; days: GpsDayRow[]
  week_wialon_m: number; week_gtk_m: number; week_unified_m: number; distance_issues: number; severity: number; status: "ok" | "warn" | "bad"
  health?: GpsHealth | null; top_cause?: CauseCode | string | null; week_fused_m?: number; week_confidence?: number | null; moving?: boolean
  section_name_short?: string | null; model_id?: string | null; explanation?: string | null
}
export type GpsSummary = {
  assets: number; both_sources: number; position_verdicts: Record<string, number>; distance_verdicts: Record<string, number>
  week_wialon_m: number; week_gtk_m: number; week_unified_m: number; ok: number; warn: number; bad: number
  cause_counts?: Record<string, number>; health_counts?: Record<string, number>; week_fused_m?: number; km_lost_m?: number
}
export type GpsFeedHealth = {
  gtk_enabled: boolean; gtk_last_run_at?: string | null; gtk_last_status?: string | null; gtk_last_error?: string | null; gtk_running?: boolean
  gtk_units: number; gtk_tracks_failed: number; gtk_units_synced_at?: string | null; wialon_units_synced_at?: string | null
  gtk_track_points: number; wialon_track_points: number; gtk_track_from?: string | null; wialon_track_from?: string | null; utc_offset_hours: number
}
export type GpsOverview = {
  items: GpsAssetRow[]; total: number; limit: number; offset: number; summary: GpsSummary; feed: GpsFeedHealth
  days: number; date_from: string; date_to: string; facets?: Record<string, Record<string, number>>
}
export type GpsTrackPoint = { at: string; lat: number; lon: number; speed?: number | null }
export type GpsAssetDetail = { row: GpsAssetRow; wialon_track: GpsTrackPoint[]; gtk_track: GpsTrackPoint[]; track_from: string; track_to: string; feed: GpsFeedHealth }

export type GpsHealthRow = {
  asset_id: string; inv_number: string; name: string; asset_type_name?: string | null; model_name?: string | null; section_id?: string | null
  section_name?: string | null; gtk_linked: boolean; gtk_id?: number | null; health: GpsHealth; last_gtk_fix_at?: string | null
  anomaly?: "frozen" | "silent" | string | null; explanation?: string | null
}
export type GpsHealthPage = { items: GpsHealthRow[]; total: number; limit: number; offset: number; counts: Record<string, number> }

export type WagonSegment = {
  train_gtk_id: number; train_number?: string | null; loco_asset_id?: string | null; loco_inv_number?: string | null
  period_from: string; period_to: string; open: boolean
  km_odometer?: number | null; km_wialon?: number | null; km_gtk?: number | null; km_fused?: number | null; selected_km?: number | null
  basis: WagonBasis; confidence: Confidence; coverage?: number | null; flags: string[]
}
export type GpsWagonRow = {
  asset_id?: string | null; carriage_gtk_id: number; inv_number?: string | null; name: string; asset_type?: string | null; asset_type_name?: string | null
  section_id?: string | null; section_name?: string | null; in_train: boolean; train_gtk_id?: number | null; train_number?: string | null; since?: string | null
  loco_asset_id?: string | null; loco_inv_number?: string | null; loco_name?: string | null
  position?: GpsFix | null; position_source?: "wialon" | "gtk_gps" | string | null; position_verdict?: PositionVerdict | string | null
  confidence: Confidence; flags: string[]; km_period: number; segments_n: number; basis_counts: Record<string, number>
}
export type GpsWagonSummary = {
  wagons: number; in_train: number; confidence_counts: Record<string, number>; flag_counts: Record<string, number>; km_period: number; history_from?: string | null
}
export type GpsWagonPage = { items: GpsWagonRow[]; total: number; limit: number; offset: number; summary: GpsWagonSummary; days: number }
export type GpsWagonDetail = { row: GpsWagonRow; segments: WagonSegment[]; explanation?: string | null }

/** Query parameters as the API client accepts them (arrays become repeated keys). */
export type ApiParams = Record<string, string | number | boolean | string[] | undefined>

// ---- thresholds the backend uses (shown to the user in the explanation strip) ---------------------------------------
export const FRESH_MIN = 30
export const BASE_TOLERANCE_M = 200
export const SAME_SPOT_M = 150
export const IDLE_M = 1000
export const MATCH_RANGE: [number, number] = [0.85, 1.15]
export const MINOR_RANGE: [number, number] = [0.6, 1.6]

// ---- tones ----------------------------------------------------------------------------------------------------------
export type Tone = "ok" | "info" | "warn" | "bad" | "mute"

export const POSITION_ORDER: PositionVerdict[] = [
  "confirmed", "both_stale_agree", "wialon_only", "gtk_only", "wialon_stale", "gtk_stale", "both_stale_apart", "diverged", "no_position",
]
export const POSITION_LABEL: Record<PositionVerdict, string> = {
  confirmed: "Подтверждено",
  diverged: "Расхождение",
  gtk_stale: "GTK молчит",
  wialon_stale: "Wialon молчит",
  both_stale_agree: "Оба молчат, место совпало",
  both_stale_apart: "Оба молчат, места разные",
  wialon_only: "Только Wialon",
  gtk_only: "Только GTK",
  no_position: "Нет позиции",
}
export const POSITION_HINT: Record<PositionVerdict, string> = {
  confirmed: "Оба трекера свежие и показывают одно место: расстояние между точками не больше допуска на разницу во времени и скорость.",
  diverged: "Оба трекера свежие, но точки далеко друг от друга. Один из них ошибается: проверьте трекеры на локомотиве и привязку юнитов.",
  gtk_stale: "GTK давно не присылает позицию, а Wialon свежий. Положение берём из Wialon; проблему стоит передать диспетчеру GTK.",
  wialon_stale: "Wialon давно не присылает позицию, а GTK свежий. Положение берём из GTK; проверьте трекер Wialon.",
  both_stale_agree: "Оба трекера давно молчат, но последние точки в одном месте: техника, вероятно, стоит там.",
  both_stale_apart: "Оба трекера давно молчат и их последние точки в разных местах: достоверного положения нет.",
  wialon_only: "У локомотива есть только Wialon (нет юнита GTK или у него нет координат): подтвердить положение нечем.",
  gtk_only: "У локомотива есть только GTK (нет привязки Wialon или у юнита нет координат): подтвердить положение нечем.",
  no_position: "Ни один из трекеров не дал корректных координат.",
}
export const POSITION_TONE: Record<PositionVerdict, Tone> = {
  confirmed: "ok", both_stale_agree: "mute", wialon_only: "info", gtk_only: "info", wialon_stale: "warn", gtk_stale: "warn", both_stale_apart: "bad", diverged: "bad", no_position: "mute",
}

export const DISTANCE_ORDER: DistanceVerdict[] = ["match", "idle", "minor_diff", "gtk_gap", "wialon_gap", "not_collected", "no_data"]
export const DISTANCE_LABEL: Record<DistanceVerdict, string> = {
  match: "Совпало", minor_diff: "Небольшая разница", gtk_gap: "Провал GTK", wialon_gap: "Провал Wialon", idle: "Стоял", no_data: "Нет данных", not_collected: "GTK не собран",
}
export const DISTANCE_HINT: Record<DistanceVerdict, string> = {
  match: "Пробег GTK составляет 85–115% длины трека Wialon: трекеры согласны.",
  minor_diff: "Пробеги отличаются на 15–40%: возможны пропуски точек или разный шумоподавитель. Берётся больший.",
  gtk_gap: "GTK записал меньше 60% пути Wialon или вообще не писал: у GTK провал. В единый пробег идёт Wialon.",
  wialon_gap: "Wialon записал меньше пути, чем GTK (или не писал): у Wialon провал или нашей синхронизации. В единый пробег идёт GTK.",
  idle: "В обоих источниках меньше 1 км: локомотив почти не двигался.",
  no_data: "В этот день нет ни точек, ни пробега ни в одном источнике.",
  not_collected: "День до начала сбора GTK: сравнивать не с чем, единый пробег — по Wialon.",
}
export const DISTANCE_TONE: Record<DistanceVerdict, Tone> = {
  match: "ok", idle: "mute", minor_diff: "warn", gtk_gap: "bad", wialon_gap: "bad", no_data: "mute", not_collected: "info",
}
export const TONE_COLOR: Record<Tone, string> = { ok: "#16a34a", info: "#2563eb", warn: "#d97706", bad: "#dc2626", mute: "#94a3b8" }
export const toneColor = (tone: Tone): string => TONE_COLOR[tone]
export const positionColor = (v: PositionVerdict | string | null | undefined): string => (v && v in POSITION_TONE ? TONE_COLOR[POSITION_TONE[v as PositionVerdict]] : TONE_COLOR.mute)
export const distanceColor = (v: DistanceVerdict | string | null | undefined): string => (v && v in DISTANCE_TONE ? TONE_COLOR[DISTANCE_TONE[v as DistanceVerdict]] : TONE_COLOR.mute)

export const TONE_CHIP: Record<Tone, string> = {
  ok: "bg-emerald-100 text-emerald-800 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-900",
  info: "bg-blue-100 text-blue-800 ring-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:ring-blue-900",
  warn: "bg-amber-100 text-amber-900 ring-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:ring-amber-900",
  bad: "bg-rose-100 text-rose-800 ring-rose-200 dark:bg-rose-950 dark:text-rose-300 dark:ring-rose-900",
  mute: "bg-gray-100 text-gray-700 ring-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700",
}

/** Backend `severity` (0 ok, 1 one source/minor, 2 a source is silent or has gaps, 3 diverged) -> a tone. */
export function severityTone(severity: number): Tone {
  return severity <= 0 ? "ok" : severity === 1 ? "info" : severity === 2 ? "warn" : "bad"
}
/** Backend `status` -> a tone. */
export const statusTone = (status: string): Tone => (status === "ok" ? "ok" : status === "warn" ? "warn" : status === "bad" ? "bad" : "mute")

// ---- map filter groups (the map page folds nine verdicts into five chips) ----------------------------------------------
export type VerdictGroup = "confirmed" | "diverged" | "gtk_stale" | "wialon_stale" | "single"
export const GROUP_ORDER: VerdictGroup[] = ["confirmed", "diverged", "gtk_stale", "wialon_stale", "single"]
export const GROUP_LABEL: Record<VerdictGroup, string> = {
  confirmed: "Подтверждено", diverged: "Расхождение", gtk_stale: "GTK молчит", wialon_stale: "Wialon молчит", single: "Один источник",
}
export const GROUP_COLOR: Record<VerdictGroup, string> = { confirmed: TONE_COLOR.ok, diverged: TONE_COLOR.bad, gtk_stale: TONE_COLOR.warn, wialon_stale: "#ea580c", single: TONE_COLOR.info }

export function verdictGroup(verdict: string | null | undefined): VerdictGroup | null {
  switch (verdict) {
    case "confirmed": case "both_stale_agree": return "confirmed"
    case "diverged": case "both_stale_apart": return "diverged"
    case "gtk_stale": return "gtk_stale"
    case "wialon_stale": return "wialon_stale"
    case "wialon_only": case "gtk_only": return "single"
    default: return null
  }
}
export function groupCounts(verdicts: Record<string, number> | null | undefined): Record<VerdictGroup, number> {
  const out: Record<VerdictGroup, number> = { confirmed: 0, diverged: 0, gtk_stale: 0, wialon_stale: 0, single: 0 }
  for (const [verdict, count] of Object.entries(verdicts ?? {})) {
    const group = verdictGroup(verdict)
    if (group) out[group] += count
  }
  return out
}

// ---- formatting -----------------------------------------------------------------------------------------------------
const NBSP = " "
function group(integer: string): string {
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP)
}

/** 12345 m -> «12,3 км»; null -> «—». Big numbers are grouped: «33 608 км». */
export function kmText(metres: number | null | undefined, withUnit = true): string {
  if (metres === null || metres === undefined || !Number.isFinite(metres)) return "—"
  const km = metres / 1000
  const body = Math.abs(km) >= 100 ? group(String(Math.round(km))) : km.toFixed(1).replace(".", ",")
  return withUnit ? `${body}${NBSP}км` : body
}

/** 250 -> «250 м»; 1240 -> «1,2 км». */
export function distText(metres: number | null | undefined): string {
  if (metres === null || metres === undefined || !Number.isFinite(metres)) return "—"
  return Math.abs(metres) < 1000 ? `${Math.round(metres)}${NBSP}м` : kmText(metres)
}

/** A signed difference: «+1,2 км» / «−350 м» / «0». */
export function signedDistText(metres: number | null | undefined): string {
  if (metres === null || metres === undefined || !Number.isFinite(metres)) return "—"
  if (Math.round(metres) === 0) return "0"
  return `${metres > 0 ? "+" : "−"}${distText(Math.abs(metres))}`
}

/** Age in minutes: «сейчас», «2 мин», «3 ч», «5 сут». */
export function ageMinText(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return "нет данных"
  if (minutes < 1) return "сейчас"
  if (minutes < 60) return `${Math.round(minutes)}${NBSP}мин`
  if (minutes < 60 * 48) return `${Math.round(minutes / 60)}${NBSP}ч`
  return `${Math.round(minutes / 1440)}${NBSP}сут`
}

/** GTK / Wialon as a percentage: 0.943 -> «94%». */
export function ratioText(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) return "—"
  return fmtPercent(ratio * 100)
}

/** A lag in seconds: «45 с», «2 мин». */
export function lagText(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—"
  return seconds < 90 ? `${Math.round(seconds)}${NBSP}с` : `${Math.round(seconds / 60)}${NBSP}мин`
}

/** The local day «2026-11-17» -> «17.11». */
export function dayShort(day: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(day)
  return m ? `${m[2]}.${m[1]}` : day
}

/** «17.11.2026 22:38» in the browser's time; «—» for a missing/invalid moment. */
export function timeText(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return "—"
  const p = (n: number) => String(n).padStart(2, "0")
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export const speedText = (speed: number | null | undefined): string => (speed === null || speed === undefined || !Number.isFinite(speed) ? "—" : `${Math.round(speed)}${NBSP}км/ч`)

/** The state of the last GTK synchronisation run. */
export function runStatusText(status: string | null | undefined): string {
  return status === "success" ? "успешно" : status === "partial" ? "частично" : status === "failed" ? "сбой" : status ? status : "запусков не было"
}
export const runStatusTone = (status: string | null | undefined): Tone => (status === "success" ? "ok" : status === "partial" ? "warn" : status === "failed" ? "bad" : "mute")

/** A sync is stale when its last run is older than `limitMin` minutes. */
export function isStale(iso: string | null | undefined, limitMin: number, now: Date = new Date()): boolean {
  if (!iso) return true
  const t = new Date(iso).getTime()
  return !Number.isFinite(t) || now.getTime() - t > limitMin * 60_000
}

/** The sentence that says how the two live fixes were judged. */
export function positionSentence(check: GpsPositionCheck, wialon: GpsFix | null, gtk: GpsFix | null): string {
  const parts: string[] = [POSITION_HINT[check.verdict]]
  if (check.diff_m !== null && check.diff_m !== undefined) {
    let line = `Между точками ${distText(check.diff_m)}`
    if (check.tolerance_m !== null && check.tolerance_m !== undefined) line += ` при допуске ${distText(check.tolerance_m)}`
    if (check.lag_s !== null && check.lag_s !== undefined) line += `, фиксы сняты с разницей ${lagText(check.lag_s)}`
    parts.push(`${line}.`)
  }
  if (wialon?.age_min !== undefined && gtk?.age_min !== undefined) parts.push(`Возраст: Wialon ${ageMinText(wialon.age_min)}, GTK ${ageMinText(gtk.age_min)}.`)
  return parts.join(" ")
}

// ---- filtering of the overview rows (client side, for the maps and the tables that already hold the rows) --------------
export function matchesQuery(row: Pick<GpsAssetRow, "inv_number" | "name" | "section_name" | "model_name">, q: string): boolean {
  const needle = q.trim().toLowerCase()
  return !needle || `${row.inv_number} ${row.name} ${row.section_name ?? ""} ${row.model_name ?? ""}`.toLowerCase().includes(needle)
}

// ---- chart geometry (hand-drawn SVG) ---------------------------------------------------------------------------------
/** A "nice" axis maximum above `value` (1, 2, 5 x 10^k). */
export function niceMax(value: number): number {
  if (!(value > 0)) return 1
  const exp = Math.pow(10, Math.floor(Math.log10(value)))
  const f = value / exp
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * exp
}

export type Segment = { key: string; value: number; x: number; w: number; pct: number }
/** Cut a width into proportional segments (a stacked bar). Zero values get no segment. */
export function stackSegments<K extends string>(order: K[], counts: Record<string, number>, width: number): (Segment & { key: K })[] {
  const total = order.reduce((s, k) => s + (counts[k] ?? 0), 0)
  if (total <= 0) return []
  let x = 0
  const out: (Segment & { key: K })[] = []
  for (const key of order) {
    const value = counts[key] ?? 0
    if (value <= 0) continue
    const w = (value / total) * width
    out.push({ key, value, x, w, pct: (value / total) * 100 })
    x += w
  }
  return out
}

export type GroupedBar = { day: string; a: { x: number; y: number; w: number; h: number; v: number }; b: { x: number; y: number; w: number; h: number; v: number } }
/** Pair of bars per day (a = Wialon, b = GTK) inside a plot of `width` x `height`; the tallest bar reaches `niceMax`. */
export function groupedBars(rows: { day: string; a: number | null | undefined; b: number | null | undefined }[], width: number, height: number): { bars: GroupedBar[]; max: number } {
  const peak = Math.max(0, ...rows.flatMap((r) => [r.a ?? 0, r.b ?? 0]))
  const max = niceMax(peak)
  const slot = rows.length > 0 ? width / rows.length : width
  const bw = Math.min(26, (slot * 0.8) / 2)
  const bars = rows.map((r, i) => {
    const cx = i * slot + slot / 2
    const mk = (v: number | null | undefined, x: number) => {
      const value = v ?? 0
      const h = max > 0 ? (value / max) * height : 0
      return { x, y: height - h, w: bw, h, v: value }
    }
    return { day: r.day, a: mk(r.a, cx - bw - 0.5), b: mk(r.b, cx + 0.5) }
  })
  return { bars, max }
}

/** Heights (0..1) for a mini bar chart; the common maximum keeps both series comparable. */
export function miniBarHeights(a: (number | null | undefined)[], b: (number | null | undefined)[]): { a: number[]; b: number[] } {
  const peak = Math.max(0, ...a.map((v) => v ?? 0), ...b.map((v) => v ?? 0))
  const scale = (v: number | null | undefined) => (peak > 0 ? Math.max(0, (v ?? 0) / peak) : 0)
  return { a: a.map(scale), b: b.map(scale) }
}

/** The bounds of several point lists as [[south, west], [north, east]], or null. */
export function boundsOfLists(lists: { lat: number; lon: number }[][]): [[number, number], [number, number]] | null {
  let south = 90, north = -90, west = 180, east = -180, n = 0
  for (const list of lists) for (const p of list) {
    n++
    south = Math.min(south, p.lat); north = Math.max(north, p.lat); west = Math.min(west, p.lon); east = Math.max(east, p.lon)
  }
  return n === 0 ? null : [[south, west], [north, east]]
}

// ---- the map point of a locomotive that has both trackers -------------------------------------------------------------
export type GpsPointLines = {
  verdict: PositionVerdict; verdictLabel: string; drawn: string; other: string | null; diff: string | null; hint: string; ghost: boolean
}

/** What the map says about BOTH fixes of a locomotive: the drawn one (source, age, speed), the other tracker, and the distance between them. */
export function gpsPointLines(p: Pick<MapPoint, "source" | "speed" | "gps_verdict" | "gps_diff_m" | "gps_wialon_age_min" | "gps_gtk_age_min" | "alt_source" | "alt_lat" | "alt_lon">): GpsPointLines | null {
  if (!p.gps_verdict || !(p.gps_verdict in POSITION_LABEL)) return null
  const verdict = p.gps_verdict as PositionVerdict
  const gtkDrawn = p.source === "gtk_gps"
  const speed = p.speed === null || p.speed === undefined || p.speed === "" ? null : Number(p.speed)
  const drawnAge = gtkDrawn ? p.gps_gtk_age_min : p.gps_wialon_age_min
  const otherAge = gtkDrawn ? p.gps_wialon_age_min : p.gps_gtk_age_min
  const name = (gtk: boolean) => (gtk ? "GTK GPS" : "Wialon")
  const drawn = `${name(gtkDrawn)}: ${ageMinText(drawnAge)}${speed !== null && Number.isFinite(speed) ? ` · ${speedText(speed)}` : ""}`
  const other = p.alt_source ? `${name(p.alt_source === "gtk_gps")}: ${ageMinText(otherAge)}` : verdict === "wialon_only" || verdict === "gtk_only" ? null : `${name(!gtkDrawn)}: ${ageMinText(otherAge)}`
  const diff = p.gps_diff_m === null || p.gps_diff_m === undefined ? null : distText(p.gps_diff_m)
  const ghost = p.alt_lat !== null && p.alt_lat !== undefined && p.alt_lon !== null && p.alt_lon !== undefined && p.alt_source !== null && p.alt_source !== undefined
  return { verdict, verdictLabel: POSITION_LABEL[verdict], drawn, other, diff, hint: POSITION_HINT[verdict], ghost }
}
