// Analytics layer of the GPS pages: causes of a daily difference, tracker health, confidence, wagon labels, and the URL <-> filter state.
// Pure functions, no React. Tests: lib/gps-analytics.test.ts (npm run test:unit).

import {
  DISTANCE_LABEL, DISTANCE_ORDER, POSITION_LABEL, POSITION_ORDER, TONE_COLOR, dayShort, kmText,
  type ApiParams, type CauseCode, type Confidence, type DistanceVerdict, type GpsDayRow, type GpsHealth, type HealthClass, type PositionVerdict, type Tone,
  type WagonBasis, type WagonFlag,
} from "./gps-view.ts"

const NBSP = " "

// ---- causes of a daily difference ------------------------------------------------------------------------------------
export const CAUSE_ORDER: CauseCode[] = [
  "gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse", "wialon_gaps", "both_gaps", "method", "day_open", "not_collected", "idle", "no_data", "ok",
]
export const CAUSE_LABEL: Record<CauseCode, string> = {
  ok: "Совпало", method: "Метод", day_open: "День не закрыт", gtk_dead: "GTK мёртв", gtk_no_day: "GTK не писал", gtk_gaps: "GTK: провалы",
  gtk_sparse: "GTK: редкие точки", wialon_gaps: "Wialon: провалы", both_gaps: "Провалы у обоих", not_collected: "GTK не собран", idle: "Стоял", no_data: "Нет данных",
}
export const CAUSE_HINT: Record<CauseCode, string> = {
  ok: "Оба трекера записали день и согласны.",
  method: "Трекеры без провалов, но пробеги отличаются немного: разный шумоподавитель и способ подсчёта.",
  day_open: "Сутки ещё не закончились: цифра может вырасти.",
  gtk_dead: "GTK не присылает точки неделями или вообще никогда: трекер не работает или юнит не привязан.",
  gtk_no_day: "В этот день GTK не прислал ни одной точки, а Wialon писал.",
  gtk_gaps: "GTK молчал два часа и больше, Wialon писал непрерывно.",
  gtk_sparse: "Длинных провалов нет, но GTK присылает слишком мало точек при движении.",
  wialon_gaps: "Wialon молчал два часа и больше, GTK писал непрерывно.",
  both_gaps: "Провалы у обоих трекеров: путь известен не полностью.",
  not_collected: "День до начала сбора GTK: сравнивать не с чем.",
  idle: "В обоих источниках меньше 1 км: локомотив почти не двигался.",
  no_data: "Нет ни точек, ни пробега ни в одном источнике.",
}
export const CAUSE_TONE: Record<CauseCode, Tone> = {
  ok: "ok", method: "info", day_open: "info", gtk_dead: "bad", gtk_no_day: "bad", gtk_gaps: "warn", gtk_sparse: "warn", wialon_gaps: "bad", both_gaps: "bad",
  not_collected: "info", idle: "mute", no_data: "mute",
}
/** The causes that mean «GTK lost data» (one click from the KPI «потеряно GTK»). */
export const GTK_LOSS_CAUSES: CauseCode[] = ["gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse"]
const CAUSE_WEIGHT: Record<string, number> = { gtk_dead: 6, both_gaps: 6, wialon_gaps: 5, gtk_no_day: 5, gtk_gaps: 4, gtk_sparse: 3, method: 2 }

export const isCause = (v: unknown): v is CauseCode => typeof v === "string" && v in CAUSE_LABEL
export const causeLabel = (v: string | null | undefined): string => (v && isCause(v) ? CAUSE_LABEL[v] : v || "—")
export const causeTone = (v: string | null | undefined): Tone => (v && isCause(v) ? CAUSE_TONE[v] : "mute")
export const causeColor = (v: string | null | undefined): string => TONE_COLOR[causeTone(v)]

/** The day of a window that deserves the attention first (the worst cause, then the newest); null when nothing is wrong. */
export function worstDay(days: GpsDayRow[]): GpsDayRow | null {
  let best: GpsDayRow | null = null
  let weight = 0
  for (const d of days) {
    const w = CAUSE_WEIGHT[d.cause ?? ""] ?? 0
    if (w > weight || (w === weight && w > 0 && best && d.day > best.day)) { best = d; weight = w }
  }
  return best
}

// ---- tracker health ----------------------------------------------------------------------------------------------------
export const HEALTH_ORDER: HealthClass[] = ["dead", "frozen", "intermittent", "ok", "no_gtk"]
export const HEALTH_LABEL: Record<HealthClass, string> = { ok: "Исправен", intermittent: "Нестабильный", dead: "Мёртвый", frozen: "Замёрз", no_gtk: "Нет GTK" }
export const HEALTH_HINT: Record<HealthClass, string> = {
  ok: "GTK записывает почти все дни, пробеги совпадают с Wialon.",
  intermittent: "GTK то пишет, то пропадает: часть дней потеряна.",
  dead: "GTK не пишет почти никогда: проверьте трекер или привязку юнита.",
  frozen: "GTK присылает свежее время, но координата не меняется: трекер завис.",
  no_gtk: "У локомотива нет юнита GTK.",
}
export const HEALTH_TONE: Record<HealthClass, Tone> = { ok: "ok", intermittent: "warn", dead: "bad", frozen: "bad", no_gtk: "mute" }
export const isHealth = (v: unknown): v is HealthClass => typeof v === "string" && v in HEALTH_LABEL
export const healthLabel = (v: string | null | undefined): string => (v && isHealth(v) ? HEALTH_LABEL[v] : v || "—")
export const healthTone = (v: string | null | undefined): Tone => (v && isHealth(v) ? HEALTH_TONE[v] : "mute")
export const healthColor = (v: string | null | undefined): string => TONE_COLOR[healthTone(v)]

/** «12 из 30 дн. (40%)». */
export function okShareText(h: GpsHealth | null | undefined): string {
  if (!h || h.active_days <= 0) return "—"
  return `${h.ok_days} из ${h.active_days} дн. (${Math.round((h.ok_share ?? h.ok_days / h.active_days) * 100)}%)`
}

// ---- confidence ----------------------------------------------------------------------------------------------------------
/** A 0..1 day confidence (backend `confidence`) -> «высокая 94%». */
export function confidenceText(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  return `${value >= 0.9 ? "высокая" : value >= 0.7 ? "средняя" : "низкая"} ${Math.round(value * 100)}%`
}
export const confidenceTone = (value: number | null | undefined): Tone =>
  value === null || value === undefined || !Number.isFinite(value) ? "mute" : value >= 0.9 ? "ok" : value >= 0.7 ? "warn" : "bad"

/** «34,9 км ± 1,2 км»: the unified distance and the part of it that is only a straight bridge over silence. */
export function fusedText(fusedM: number | null | undefined, gapM: number | null | undefined): string {
  if (fusedM === null || fusedM === undefined || !Number.isFinite(fusedM)) return "—"
  return gapM && gapM > 0 ? `${kmText(fusedM)} ± ${kmText(gapM)}` : kmText(fusedM)
}
export const sumGap = (days: GpsDayRow[]): number => days.reduce((a, d) => a + (d.unknown_gap_m ?? 0), 0)
/** Hours of coverage: «18,5 ч». */
export const hoursText = (h: number | null | undefined): string => (h === null || h === undefined || !Number.isFinite(h) ? "—" : `${h.toFixed(1).replace(".", ",")}${NBSP}ч`)

// ---- wagons -----------------------------------------------------------------------------------------------------------------
export const CONFIDENCE_ORDER: Confidence[] = ["high", "medium", "low", "none"]
export const CONFIDENCE_LABEL: Record<Confidence, string> = { high: "Высокая", medium: "Средняя", low: "Низкая", none: "Нет" }
export const CONFIDENCE_HINT: Record<Confidence, string> = {
  high: "Локомотив подтверждён обоими трекерами, состав свежий.",
  medium: "Локомотив виден одним трекером.",
  low: "Фикс локомотива устарел или трекеры расходятся.",
  none: "Вагон не в составе или у локомотива нет координат.",
}
export const CONFIDENCE_TONE: Record<Confidence, Tone> = { high: "ok", medium: "info", low: "warn", none: "mute" }
export const CONFIDENCE_COLOR: Record<Confidence, string> = { high: TONE_COLOR.ok, medium: TONE_COLOR.info, low: TONE_COLOR.warn, none: TONE_COLOR.mute }
export const isConfidence = (v: unknown): v is Confidence => typeof v === "string" && v in CONFIDENCE_LABEL
export const confidenceLabel = (v: string | null | undefined): string => (v && isConfidence(v) ? CONFIDENCE_LABEL[v] : v || "—")
export const confidenceColor = (v: string | null | undefined): string => (v && isConfidence(v) ? CONFIDENCE_COLOR[v] : TONE_COLOR.mute)

export const FLAG_ORDER: WagonFlag[] = ["two_trains", "stale_membership", "loco_silent", "no_loco", "no_history"]
export const FLAG_LABEL: Record<WagonFlag, string> = {
  two_trains: "В двух составах", stale_membership: "Состав устарел", loco_silent: "Локомотив молчит", no_loco: "Нет локомотива", no_history: "Нет истории",
}
export const FLAG_HINT: Record<WagonFlag, string> = {
  two_trains: "Вагон одновременно числится в двух составах: одна из записей GTK неверна.",
  stale_membership: "Состав не подтверждался GTK больше суток: вагон мог уже уйти.",
  loco_silent: "Оба трекера локомотива давно молчат: положение вагона неизвестно.",
  no_loco: "В составе нет локомотива с привязкой к ОС.",
  no_history: "Время до начала истории состава GTK: вагон нельзя привязать к локомотиву.",
}
export const FLAG_TONE: Record<WagonFlag, Tone> = { two_trains: "bad", stale_membership: "warn", loco_silent: "warn", no_loco: "warn", no_history: "mute" }
export const isFlag = (v: unknown): v is WagonFlag => typeof v === "string" && v in FLAG_LABEL
export const flagLabel = (v: string): string => (isFlag(v) ? FLAG_LABEL[v] : v)
export const flagTone = (v: string): Tone => (isFlag(v) ? FLAG_TONE[v] : "mute")
export const flagHint = (v: string): string => (isFlag(v) ? FLAG_HINT[v] : "")

export const BASIS_LABEL: Record<WagonBasis, string> = {
  fused_track: "Единый трек", track: "Трек", odometer: "Одометр", conflict: "Конфликт источников", single_source: "Один источник", held: "Не посчитано",
}
export const BASIS_HINT: Record<WagonBasis, string> = {
  fused_track: "Единый трек покрывает ≥90% периода: берётся он.",
  track: "Единого трека мало; трек Wialon и одометр согласны (≤10%): берётся трек.",
  odometer: "Берётся приращение одометра локомотива.",
  conflict: "Одометр и трек расходятся больше чем на 10%: взят источник с большим покрытием, значение приблизительное.",
  single_source: "Есть только один источник: значение приблизительное.",
  held: "Ни один источник не покрывает период: пробег не посчитан.",
}
export const BASIS_TONE: Record<WagonBasis, Tone> = { fused_track: "ok", track: "ok", odometer: "info", conflict: "warn", single_source: "warn", held: "bad" }
export const basisLabel = (v: string): string => (v in BASIS_LABEL ? BASIS_LABEL[v as WagonBasis] : v)
export const basisTone = (v: string): Tone => (v in BASIS_TONE ? BASIS_TONE[v as WagonBasis] : "mute")
export const isBasis = (v: unknown): v is WagonBasis => typeof v === "string" && v in BASIS_LABEL
export const basisHint = (v: string): string => (v in BASIS_HINT ? BASIS_HINT[v as WagonBasis] : "")

/** A km figure of a wagon segment (already in km, not metres): «12,4 км». */
export function segKm(km: number | null | undefined): string {
  return km === null || km === undefined || !Number.isFinite(km) ? "—" : kmText(km * 1000)
}

// ---- map bounds filter ---------------------------------------------------------------------------------------------------------
/** [[south, west], [north, east]] -> «minLat,minLon,maxLat,maxLon» (the API's `bbox`). */
export function bboxText(b: [[number, number], [number, number]]): string {
  const f = (n: number) => n.toFixed(5)
  return `${f(b[0][0])},${f(b[0][1])},${f(b[1][0])},${f(b[1][1])}`
}
export function pointInBbox(p: { lat: number; lon: number }, bbox: string): boolean {
  const [s, w, n, e] = bbox.split(",").map(Number)
  return [s, w, n, e].every(Number.isFinite) && p.lat >= s && p.lat <= n && p.lon >= w && p.lon <= e
}

// ---- local dates and presets ------------------------------------------------------------------------------------------------------
const pad2 = (n: number) => String(n).padStart(2, "0")
/** The local calendar day «YYYY-MM-DD» of an instant in a zone `offsetHours` from UTC (GTK days are UTC+5). */
export function localDay(nowMs: number, offsetHours: number): string {
  const d = new Date(nowMs + offsetHours * 3_600_000)
  return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`
}
export function addDays(day: string, delta: number): string {
  const [y, m, d] = day.split("-").map(Number)
  const t = new Date(Date.UTC(y, m - 1, d + delta))
  return `${t.getUTCFullYear()}-${pad2(t.getUTCMonth() + 1)}-${pad2(t.getUTCDate())}`
}
export type DatePreset = "today" | "yesterday" | "7" | "14" | "30"
export const DATE_PRESETS: { id: DatePreset; label: string }[] = [
  { id: "today", label: "Сегодня" }, { id: "yesterday", label: "Вчера" }, { id: "7", label: "7 дн." }, { id: "14", label: "14 дн." }, { id: "30", label: "30 дн." },
]
export function datePreset(preset: DatePreset, nowMs: number, offsetHours = 5): { date_from: string; date_to: string } {
  const today = localDay(nowMs, offsetHours)
  switch (preset) {
    case "today": return { date_from: today, date_to: today }
    case "yesterday": { const y = addDays(today, -1); return { date_from: y, date_to: y } }
    default: return { date_from: addDays(today, -(Number(preset) - 1)), date_to: today }
  }
}
export const isIsoDay = (v: string): boolean => /^\d{4}-\d{2}-\d{2}$/.test(v)
export function daysBetween(from: string, to: string): number {
  const f = Date.parse(`${from}T00:00:00Z`), t = Date.parse(`${to}T00:00:00Z`)
  return Number.isFinite(f) && Number.isFinite(t) ? Math.round((t - f) / 86_400_000) + 1 : 0
}
export const MAX_WINDOW_DAYS = 31

// ---- URL <-> filter state: the overview page ---------------------------------------------------------------------------------------------
export const OVERVIEW_SORTS = [
  "severity", "inv_number", "diff_m", "gtk_age", "wialon_age", "week_wialon_m", "week_gtk_m", "week_fused_m", "ratio", "cause", "confidence",
] as const
export type OverviewSort = (typeof OVERVIEW_SORTS)[number]
export const LINKS = ["both", "wialon_only", "gtk_only", "none"] as const
export const LINK_LABEL: Record<(typeof LINKS)[number], string> = { both: "Оба трекера", wialon_only: "Только Wialon", gtk_only: "Только GTK", none: "Нет ни одного" }
export const SEVERITIES = ["ok", "warn", "bad"] as const
export const SEVERITY_LABEL: Record<(typeof SEVERITIES)[number], string> = { ok: "Норма", warn: "Внимание", bad: "Проблема" }
export const PAGE_SIZE = 50
export const DAY_CHOICES = [1, 2, 3, 5, 7, 10, 14, 21, 31]

export type GpsFilters = {
  q: string; section_id: string; asset_type: string[]; verdict: string[]; distance_verdict: string[]; cause: string[]; severity: string[]
  link: string; health: string[]; min_diff_m: string; min_silence_h: string; moving: boolean; min_km: string; max_km: string
  only_issues: boolean; follow: boolean; days: number; date_from: string; date_to: string; sort_by: OverviewSort; sort_dir: "asc" | "desc"; page: number
}
export const DEFAULT_FILTERS: GpsFilters = {
  q: "", section_id: "", asset_type: [], verdict: [], distance_verdict: [], cause: [], severity: [], link: "", health: [], min_diff_m: "", min_silence_h: "",
  moving: false, min_km: "", max_km: "", only_issues: false, follow: false, days: 7, date_from: "", date_to: "", sort_by: "severity", sort_dir: "desc", page: 0,
}

const list = (raw: string | null, allowed?: readonly string[]): string[] =>
  (raw ?? "").split(",").map((x) => x.trim()).filter((x) => x !== "" && (!allowed || allowed.includes(x)))
const num = (raw: string | null): string => (raw !== null && raw !== "" && Number.isFinite(Number(raw)) && Number(raw) >= 0 ? String(Number(raw)) : "")
const flag = (raw: string | null): boolean => raw === "1" || raw === "true"
export type SearchLike = string | URLSearchParams | { get(name: string): string | null }
const asParams = (search: SearchLike): { get(name: string): string | null } => (typeof search === "string" ? new URLSearchParams(search.replace(/^\?/, "")) : search)

/** Read the filter state from a query string; anything unknown or malformed falls back to the default. */
export function parseGpsFilters(search: SearchLike): GpsFilters {
  const p = asParams(search)
  const from = p.get("date_from") ?? "", to = p.get("date_to") ?? ""
  const dated = isIsoDay(from) && isIsoDay(to) && daysBetween(from, to) >= 1 && daysBetween(from, to) <= MAX_WINDOW_DAYS
  const days = Number(p.get("days"))
  const sort = p.get("sort_by") ?? ""
  const page = Number(p.get("page"))
  const sortBy = (OVERVIEW_SORTS as readonly string[]).includes(sort) ? (sort as OverviewSort) : DEFAULT_FILTERS.sort_by
  return {
    q: p.get("q") ?? "", section_id: p.get("section_id") ?? "", asset_type: list(p.get("asset_type")),
    verdict: list(p.get("verdict"), POSITION_ORDER), distance_verdict: list(p.get("distance_verdict"), DISTANCE_ORDER),
    cause: list(p.get("cause"), CAUSE_ORDER), severity: list(p.get("severity"), SEVERITIES),
    link: (LINKS as readonly string[]).includes(p.get("link") ?? "") ? (p.get("link") as string) : "", health: list(p.get("health"), HEALTH_ORDER),
    min_diff_m: num(p.get("min_diff_m")), min_silence_h: num(p.get("min_silence_h")), moving: flag(p.get("moving")),
    min_km: num(p.get("min_km")), max_km: num(p.get("max_km")), only_issues: flag(p.get("only_issues")), follow: flag(p.get("follow")),
    days: Number.isInteger(days) && days >= 1 && days <= MAX_WINDOW_DAYS ? days : DEFAULT_FILTERS.days,
    date_from: dated ? from : "", date_to: dated ? to : "",
    sort_by: sortBy,
    sort_dir: p.get("sort_dir") === "asc" ? "asc" : p.get("sort_dir") === "desc" ? "desc" : sortBy === "inv_number" ? "asc" : DEFAULT_FILTERS.sort_dir,
    page: Number.isInteger(page) && page > 0 ? page : 0,
  }
}

/** The shortest query string that reproduces the state (defaults are omitted; key order is stable). */
export function serializeGpsFilters(f: GpsFilters): string {
  const d = DEFAULT_FILTERS
  const p = new URLSearchParams()
  const put = (k: string, v: string) => { if (v !== "") p.set(k, v) }
  put("q", f.q.trim()); put("section_id", f.section_id)
  for (const k of ["asset_type", "verdict", "distance_verdict", "cause", "severity", "health"] as const) put(k, f[k].join(","))
  put("link", f.link); put("min_diff_m", f.min_diff_m); put("min_silence_h", f.min_silence_h); put("min_km", f.min_km); put("max_km", f.max_km)
  if (f.moving) p.set("moving", "1")
  if (f.only_issues) p.set("only_issues", "1")
  if (f.follow) p.set("follow", "1")
  if (f.date_from && f.date_to) { p.set("date_from", f.date_from); p.set("date_to", f.date_to) } else if (f.days !== d.days) p.set("days", String(f.days))
  if (f.sort_by !== d.sort_by) p.set("sort_by", f.sort_by)
  if (f.sort_dir !== (f.sort_by === "inv_number" ? "asc" : d.sort_dir)) p.set("sort_dir", f.sort_dir)
  if (f.page > 0) p.set("page", String(f.page))
  return p.toString()
}

/** The API parameters of a filter state. `bbox` (the map viewport) is passed separately: it is not part of the shareable state. */
export function gpsApiParams(f: GpsFilters, opts: { limit: number; offset: number; facets?: boolean; bbox?: string | null; withSort?: boolean }): ApiParams {
  const out: ApiParams = { limit: opts.limit, offset: opts.offset }
  if (f.date_from && f.date_to) { out.date_from = f.date_from; out.date_to = f.date_to } else out.days = f.days
  if (f.q.trim()) out.q = f.q.trim()
  if (f.section_id) out.section_id = f.section_id
  for (const k of ["asset_type", "verdict", "distance_verdict", "cause", "severity", "health"] as const) if (f[k].length) out[k] = f[k]
  if (f.link) out.link = f.link
  if (f.min_diff_m) out.min_diff_m = Number(f.min_diff_m)
  if (f.min_silence_h) out.min_silence_h = Number(f.min_silence_h)
  if (f.min_km) out.min_km = Number(f.min_km)
  if (f.max_km) out.max_km = Number(f.max_km)
  if (f.moving) out.moving = true
  if (f.only_issues) out.only_issues = true
  if (opts.facets) out.facets = true
  if (opts.bbox) out.bbox = opts.bbox
  if (opts.withSort !== false) { out.sort_by = f.sort_by; out.sort_dir = f.sort_dir }
  return out
}

export const isDefaultFilters = (f: GpsFilters): boolean =>
  serializeGpsFilters({ ...f, sort_by: DEFAULT_FILTERS.sort_by, sort_dir: DEFAULT_FILTERS.sort_dir, page: 0, follow: false }) === ""

/** The window of a state as text: «7 дн.» / «17.11 – 18.11». */
export function windowText(f: Pick<GpsFilters, "days" | "date_from" | "date_to">): string {
  if (f.date_from && f.date_to) return f.date_from === f.date_to ? dayShort(f.date_from) : `${dayShort(f.date_from)} – ${dayShort(f.date_to)}`
  return f.days === 1 ? "сегодня" : `${f.days} дн.`
}

export type FilterChip<F> = { id: string; label: string; patch: Partial<F> }
const without = (values: string[], v: string) => values.filter((x) => x !== v)

/** One removable chip per active filter value; `patch` removes it. */
export function gpsFilterChips(f: GpsFilters, sectionName?: (id: string) => string | undefined): FilterChip<GpsFilters>[] {
  const out: FilterChip<GpsFilters>[] = []
  if (f.q.trim()) out.push({ id: "q", label: `Поиск: ${f.q.trim()}`, patch: { q: "", page: 0 } })
  if (f.section_id) out.push({ id: "section", label: `Участок: ${sectionName?.(f.section_id) ?? "…"}`, patch: { section_id: "", page: 0 } })
  for (const v of f.asset_type) out.push({ id: `type:${v}`, label: `Тип: ${v}`, patch: { asset_type: without(f.asset_type, v), page: 0 } })
  for (const v of f.verdict) out.push({ id: `verdict:${v}`, label: `Положение: ${POSITION_LABEL[v as PositionVerdict] ?? v}`, patch: { verdict: without(f.verdict, v), page: 0 } })
  for (const v of f.distance_verdict) out.push({ id: `dist:${v}`, label: `Пробег: ${DISTANCE_LABEL[v as DistanceVerdict] ?? v}`, patch: { distance_verdict: without(f.distance_verdict, v), page: 0 } })
  for (const v of f.cause) out.push({ id: `cause:${v}`, label: `Причина: ${causeLabel(v)}`, patch: { cause: without(f.cause, v), page: 0 } })
  for (const v of f.severity) out.push({ id: `sev:${v}`, label: `Статус: ${SEVERITY_LABEL[v as (typeof SEVERITIES)[number]] ?? v}`, patch: { severity: without(f.severity, v), page: 0 } })
  if (f.link) out.push({ id: "link", label: `Трекеры: ${LINK_LABEL[f.link as (typeof LINKS)[number]] ?? f.link}`, patch: { link: "", page: 0 } })
  for (const v of f.health) out.push({ id: `health:${v}`, label: `GTK: ${healthLabel(v)}`, patch: { health: without(f.health, v), page: 0 } })
  if (f.min_diff_m) out.push({ id: "diff", label: `Между точками > ${f.min_diff_m} м`, patch: { min_diff_m: "", page: 0 } })
  if (f.min_silence_h) out.push({ id: "silence", label: `Молчит > ${f.min_silence_h} ч`, patch: { min_silence_h: "", page: 0 } })
  if (f.moving) out.push({ id: "moving", label: "Едут сейчас", patch: { moving: false, page: 0 } })
  if (f.min_km) out.push({ id: "minkm", label: `Км от ${f.min_km}`, patch: { min_km: "", page: 0 } })
  if (f.max_km) out.push({ id: "maxkm", label: `Км до ${f.max_km}`, patch: { max_km: "", page: 0 } })
  if (f.only_issues) out.push({ id: "issues", label: "Только проблемные", patch: { only_issues: false, page: 0 } })
  if (f.date_from && f.date_to) out.push({ id: "dates", label: `Даты: ${windowText(f)}`, patch: { date_from: "", date_to: "", page: 0 } })
  return out
}

/** Toggle a value inside a multi-select filter. */
export const toggleValue = (values: string[], v: string): string[] => (values.includes(v) ? without(values, v) : [...values, v])

/** Does the state already apply this KPI patch (so the tile can be drawn active)? */
export function patchActive<F extends object>(f: F, patch: Partial<F>): boolean {
  const keys = Object.keys(patch) as (keyof F)[]
  if (keys.length === 0) return false
  return keys.every((k) => {
    const want = patch[k], have = f[k]
    if (Array.isArray(want) && Array.isArray(have)) return want.length === have.length && want.every((x) => have.includes(x))
    return want === have
  })
}

// ---- URL <-> filter state: the wagons page ------------------------------------------------------------------------------------------------
export const WAGON_SORTS = ["inv_number", "km_period", "confidence", "since", "train_number"] as const
export type WagonSort = (typeof WAGON_SORTS)[number]
export type WagonFilters = {
  q: string; section_id: string; train: string; loco: string; confidence: string[]; flag: string[]; in_train: "" | "1" | "0"; asset_type: string
  days: number; sort_by: WagonSort; sort_dir: "asc" | "desc"; page: number
}
export const DEFAULT_WAGON_FILTERS: WagonFilters = {
  q: "", section_id: "", train: "", loco: "", confidence: [], flag: [], in_train: "", asset_type: "", days: 14, sort_by: "inv_number", sort_dir: "asc", page: 0,
}
export function parseWagonFilters(search: SearchLike): WagonFilters {
  const p = asParams(search)
  const days = Number(p.get("days")), page = Number(p.get("page")), sort = p.get("sort_by") ?? ""
  const inTrain = p.get("in_train")
  return {
    q: p.get("q") ?? "", section_id: p.get("section_id") ?? "", train: p.get("train") ?? "", loco: p.get("loco") ?? "",
    confidence: list(p.get("confidence"), CONFIDENCE_ORDER), flag: list(p.get("flag"), FLAG_ORDER),
    in_train: inTrain === "1" || inTrain === "true" ? "1" : inTrain === "0" || inTrain === "false" ? "0" : "", asset_type: p.get("asset_type") ?? "",
    days: Number.isInteger(days) && days >= 1 && days <= MAX_WINDOW_DAYS ? days : DEFAULT_WAGON_FILTERS.days,
    sort_by: (WAGON_SORTS as readonly string[]).includes(sort) ? (sort as WagonSort) : DEFAULT_WAGON_FILTERS.sort_by,
    sort_dir: p.get("sort_dir") === "desc" ? "desc" : p.get("sort_dir") === "asc" ? "asc" : DEFAULT_WAGON_FILTERS.sort_dir,
    page: Number.isInteger(page) && page > 0 ? page : 0,
  }
}
export function serializeWagonFilters(f: WagonFilters): string {
  const d = DEFAULT_WAGON_FILTERS
  const p = new URLSearchParams()
  const put = (k: string, v: string) => { if (v !== "") p.set(k, v) }
  put("q", f.q.trim()); put("section_id", f.section_id); put("train", f.train.trim()); put("loco", f.loco.trim())
  put("confidence", f.confidence.join(",")); put("flag", f.flag.join(",")); put("in_train", f.in_train); put("asset_type", f.asset_type)
  if (f.days !== d.days) p.set("days", String(f.days))
  if (f.sort_by !== d.sort_by) p.set("sort_by", f.sort_by)
  if (f.sort_dir !== d.sort_dir) p.set("sort_dir", f.sort_dir)
  if (f.page > 0) p.set("page", String(f.page))
  return p.toString()
}
export function wagonApiParams(f: WagonFilters, opts: { limit: number; offset: number }): ApiParams {
  const out: ApiParams = { limit: opts.limit, offset: opts.offset, days: f.days, sort_by: f.sort_by, sort_dir: f.sort_dir }
  if (f.q.trim()) out.q = f.q.trim()
  if (f.section_id) out.section_id = f.section_id
  if (f.train.trim()) out.train = f.train.trim()
  if (f.loco.trim()) out.loco = f.loco.trim()
  if (f.confidence.length) out.confidence = f.confidence
  if (f.flag.length) out.flag = f.flag
  if (f.in_train) out.in_train = f.in_train === "1"
  if (f.asset_type) out.asset_type = f.asset_type
  return out
}
export function wagonFilterChips(f: WagonFilters, sectionName?: (id: string) => string | undefined): FilterChip<WagonFilters>[] {
  const out: FilterChip<WagonFilters>[] = []
  if (f.q.trim()) out.push({ id: "q", label: `Поиск: ${f.q.trim()}`, patch: { q: "", page: 0 } })
  if (f.section_id) out.push({ id: "section", label: `Участок: ${sectionName?.(f.section_id) ?? "…"}`, patch: { section_id: "", page: 0 } })
  if (f.train.trim()) out.push({ id: "train", label: `Состав: ${f.train.trim()}`, patch: { train: "", page: 0 } })
  if (f.loco.trim()) out.push({ id: "loco", label: `Локомотив: ${f.loco.trim()}`, patch: { loco: "", page: 0 } })
  for (const v of f.confidence) out.push({ id: `conf:${v}`, label: `Уверенность: ${confidenceLabel(v)}`, patch: { confidence: without(f.confidence, v), page: 0 } })
  for (const v of f.flag) out.push({ id: `flag:${v}`, label: `Признак: ${flagLabel(v)}`, patch: { flag: without(f.flag, v), page: 0 } })
  if (f.in_train) out.push({ id: "in_train", label: f.in_train === "1" ? "В составе" : "Не в составе", patch: { in_train: "", page: 0 } })
  if (f.asset_type) out.push({ id: "type", label: `Тип: ${f.asset_type}`, patch: { asset_type: "", page: 0 } })
  return out
}

// ---- saved views (browser storage; the caller wraps the I/O in try/catch) ------------------------------------------------------------------------
export type SavedView = { name: string; query: string }
export function addSavedView(views: SavedView[], name: string, query: string, max = 12): SavedView[] {
  const clean = name.trim().slice(0, 40)
  if (!clean) return views
  return [{ name: clean, query }, ...views.filter((v) => v.name !== clean)].slice(0, max)
}
export function parseSavedViews(raw: string | null): SavedView[] {
  if (!raw) return []
  try {
    const data: unknown = JSON.parse(raw)
    return Array.isArray(data) ? data.filter((v): v is SavedView => !!v && typeof v.name === "string" && typeof v.query === "string").slice(0, 12) : []
  } catch {
    return []
  }
}

// ---- track of one local day (the detail page selects a day on the three maps) -------------------------------------------------------------
/** The points of a track that fall inside the LOCAL day `day` (YYYY-MM-DD) of a zone `offsetHours` from UTC. */
export function filterTrackToDay<T extends { at: string }>(points: T[], day: string, offsetHours: number): T[] {
  const start = Date.parse(`${day}T00:00:00Z`) - offsetHours * 3_600_000
  if (!Number.isFinite(start)) return points
  const end = start + 86_400_000
  return points.filter((p) => {
    const t = Date.parse(p.at)
    return Number.isFinite(t) && t >= start && t < end
  })
}

// ---- timeline of wagon segments (hand-drawn SVG) ----------------------------------------------------------------------------------------------
export type TimelineBar = { index: number; x: number; w: number; fromMs: number; toMs: number }
/** Position every segment on a horizontal axis of `width` between the first start and the last end; a segment is at least `minW` wide. */
export function timelineBars(segments: { period_from: string; period_to: string }[], width: number, minW = 3): { bars: TimelineBar[]; fromMs: number; toMs: number } {
  const spans = segments.map((s) => [Date.parse(s.period_from), Date.parse(s.period_to)] as const).filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b))
  if (spans.length === 0) return { bars: [], fromMs: 0, toMs: 0 }
  const fromMs = Math.min(...spans.map(([a]) => a)), toMs = Math.max(...spans.map(([, b]) => b))
  const total = Math.max(1, toMs - fromMs)
  const bars = segments.flatMap((s, index) => {
    const a = Date.parse(s.period_from), b = Date.parse(s.period_to)
    if (!Number.isFinite(a) || !Number.isFinite(b)) return []
    const x = ((a - fromMs) / total) * width
    return [{ index, x, w: Math.max(minW, ((b - a) / total) * width), fromMs: a, toMs: b }]
  })
  return { bars, fromMs, toMs }
}
