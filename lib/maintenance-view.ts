// Pure view logic of the maintenance page (no React, no runtime imports) so it can be unit-tested
// with `node --test`. Only type imports are allowed here: they are erased at runtime.
import type { MaintenanceScheduleItem } from "./api"

export type ScheduleItem = MaintenanceScheduleItem
export type Status = ScheduleItem["status"]
export type SortKey = "mileage" | "remaining" | "progress" | "date" | "unit" | "status" | "urgency"
export type SortDir = "asc" | "desc"
export type RecLevel = "critical" | "warning" | "info" | "ok"
export type Recommendation = { level: RecLevel; text: string }

export type Enriched = {
  item: ScheduleItem
  mileage: number | null
  remaining: number | null
  threshold: number | null
  intervalKm: number | null
  /** % of the CURRENT interval already driven (0 = just serviced, 100 = threshold reached). */
  progress: number | null
  daysLeft: number | null
  rec: Recommendation
}

/** One physical unit (asset) with all of its maintenance intervals. */
export type UnitGroup = {
  key: string
  lead: Enriched // the interval that needs attention first
  entries: Enriched[] // every interval of the unit, nearest first
  level: RecLevel // the worst recommendation level among the entries
}

/** From this share of the interval the unit counts as "close to maintenance". */
export const NEAR_THRESHOLD_PCT = 90
export const PLAN_AHEAD_PCT = 70
/** Select value of the "no section" option of the section filter. */
export const NO_DEPOT = "__none__"

export const STATUS_RANK: Record<Status, number> = { overdue: 0, in_progress: 1, upcoming: 2, completed: 3 }
export const URGENCY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }
const LEVEL_RANK: Record<RecLevel, number> = { critical: 0, warning: 1, info: 2, ok: 3 }

export const toNum = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "") return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export const fmtNum = (n: number): string => n.toLocaleString("ru-RU", { maximumFractionDigits: 1 })

/** ISO `YYYY-MM-DD…` -> `DD.MM.YYYY`. */
export function formatDate(isoDate: string): string {
  if (!isoDate) return ""
  const [y, m, d] = isoDate.split("T")[0].split("-")
  return [d, m, y].join(".")
}

export function parseDate(value: string): Date {
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) return new Date(`${value.slice(0, 10)}T00:00:00`)
  const [day, month, year] = value.split(".").map(Number)
  return new Date(year, month - 1, day)
}

export const isTestInterval = (item: ScheduleItem): boolean => item.type.trim().toLowerCase().startsWith("test")

export const inventoryNumberOf = (item: ScheduleItem): string => item.unit.split(" · ").pop() ?? item.unit

/**
 * Progress inside the current interval. The threshold is the next multiple of the interval, so a
 * mileage/threshold ratio would show 73 % for 7300 km on a 5000 km interval (real: 46 %).
 */
export function progressPct(
  mileage: number | null,
  threshold: number | null,
  intervalKm: number | null,
  remaining: number | null,
): number | null {
  if (intervalKm !== null && intervalKm > 0 && remaining !== null) {
    return Math.max(0, (1 - remaining / intervalKm) * 100)
  }
  if (mileage !== null && threshold !== null && threshold > 0) return (mileage / threshold) * 100
  return null
}

export function recommend(
  item: ScheduleItem,
  mileage: number | null,
  remaining: number | null,
  progress: number | null,
  daysLeft: number | null,
): Recommendation {
  if (item.entity_type === "work_order") {
    if (item.status === "completed") return { level: "ok", text: "Работы выполнены" }
    if (item.status === "overdue") return { level: "critical", text: "Наряд просрочен: уточните ход работ у исполнителя" }
    if (item.status === "in_progress") return { level: "info", text: "Наряд выполняется" }
    return { level: "info", text: "Наряд создан, ожидает начала работ" }
  }
  if (item.status === "in_progress") return { level: "info", text: "ТО выполняется" }
  if (item.status === "completed") return { level: "ok", text: "ТО выполнено" }
  if (mileage === null) {
    return { level: "warning", text: "Нет данных о пробеге: проверьте привязку к Wialon и ГТК" }
  }
  if (remaining === null) {
    return item.status === "overdue"
      ? { level: "critical", text: "Срок ТО прошёл: создайте наряд" }
      : { level: "info", text: `ТО по сроку, плановая дата ${formatDate(item.startDate)}` }
  }
  const days = daysLeft !== null ? ` (≈ ${daysLeft} дн.)` : ""
  if (remaining <= 0) {
    return { level: "critical", text: `Порог превышен на ${fmtNum(Math.abs(remaining))} км: срочно создайте наряд` }
  }
  if (progress !== null && progress >= NEAR_THRESHOLD_PCT) {
    return { level: "warning", text: `До ТО ${fmtNum(remaining)} км${days}: подготовьте наряд и запчасти` }
  }
  if (progress !== null && progress >= PLAN_AHEAD_PCT) {
    return { level: "info", text: `Запланируйте ТО: осталось ${fmtNum(remaining)} км${days}` }
  }
  return { level: "ok", text: `Плановая эксплуатация, до порога ${fmtNum(remaining)} км${days}` }
}

export function enrich(item: ScheduleItem, dailyKm: number | null): Enriched {
  const mileage = toNum(item.mileage)
  const remaining = toNum(item.remainingKm)
  const threshold = toNum(item.nextThreshold)
  const intervalKm = toNum(item.intervalKm)
  const progress = progressPct(mileage, threshold, intervalKm, remaining)
  const daysLeft =
    remaining !== null && remaining > 0 && dailyKm !== null && dailyKm > 0 ? Math.ceil(remaining / dailyKm) : null
  return {
    item, mileage, remaining, threshold, intervalKm, progress, daysLeft,
    rec: recommend(item, mileage, remaining, progress, daysLeft),
  }
}

/** Overdue work is never hidden by the month the Gantt is currently showing. */
export function isInRange(item: ScheduleItem, rangeStart: Date, rangeEnd: Date, durationDays: number): boolean {
  if (!item.startDate) return false
  if (item.status === "overdue") return true
  const start = parseDate(item.startDate)
  const end = new Date(start)
  end.setDate(end.getDate() + durationDays)
  return start <= rangeEnd && end >= rangeStart
}

export function sortValue(e: Enriched, key: SortKey): number | string | null {
  switch (key) {
    case "mileage": return e.mileage
    case "remaining": return e.remaining
    case "progress": return e.progress
    case "unit": return e.item.unit
    case "status": return STATUS_RANK[e.item.status]
    case "urgency": return e.item.urgency ? URGENCY_RANK[e.item.urgency] : null
    case "date": {
      const time = parseDate(e.item.startDate).getTime()
      return Number.isNaN(time) ? null : time
    }
  }
}

/** Empty values go last in BOTH directions, so a missing mileage never tops the list. */
export function compareNullsLast(a: number | string | null, b: number | string | null, dir: SortDir): number {
  if (a === null && b === null) return 0
  if (a === null) return 1
  if (b === null) return -1
  const cmp = typeof a === "string" ? a.localeCompare(String(b), "ru") : a - (b as number)
  return dir === "asc" ? cmp : -cmp
}

export function compareEnriched(a: Enriched, b: Enriched, key: SortKey, dir: SortDir): number {
  return (
    compareNullsLast(sortValue(a, key), sortValue(b, key), dir) ||
    compareNullsLast(a.remaining, b.remaining, "asc") ||
    a.item.unit.localeCompare(b.item.unit, "ru") ||
    a.item.type.localeCompare(b.item.type, "ru")
  )
}

export const defaultSortDir = (key: SortKey): SortDir => (key === "mileage" || key === "progress" ? "desc" : "asc")

/** The interval that needs attention first: worst level, then least km left, then type. */
function compareLead(a: Enriched, b: Enriched): number {
  return (
    LEVEL_RANK[a.rec.level] - LEVEL_RANK[b.rec.level] ||
    compareNullsLast(a.remaining, b.remaining, "asc") ||
    a.item.type.localeCompare(b.item.type, "ru")
  )
}

/** One group per asset, groups ordered by the chosen key evaluated on each group's lead interval. */
export function groupByUnit(entries: Enriched[], key: SortKey, dir: SortDir): UnitGroup[] {
  const byAsset = new Map<string, Enriched[]>()
  for (const entry of entries) {
    const list = byAsset.get(entry.item.asset_id)
    if (list) list.push(entry)
    else byAsset.set(entry.item.asset_id, [entry])
  }
  const groups: UnitGroup[] = []
  for (const [assetId, list] of byAsset) {
    const ordered = [...list].sort(
      (a, b) => compareNullsLast(a.remaining, b.remaining, "asc") || a.item.type.localeCompare(b.item.type, "ru"),
    )
    const lead = [...list].sort(compareLead)[0]
    const level = list.reduce<RecLevel>((worst, e) => (LEVEL_RANK[e.rec.level] < LEVEL_RANK[worst] ? e.rec.level : worst), "ok")
    groups.push({ key: assetId, lead, entries: ordered, level })
  }
  return groups.sort((a, b) => compareEnriched(a.lead, b.lead, key, dir))
}

// Same spreadsheet-formula guard as the backend CSV export.
export const csvCell = (value: string | number | null): string => {
  if (value === null) return ""
  const text = String(value)
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text
  return `"${safe.replace(/"/g, '""')}"`
}

export function buildCsv(header: string[], rows: (string | number | null)[][]): string {
  // BOM so Excel opens UTF-8 (Cyrillic) correctly; `;` is the Russian-locale separator.
  return "﻿" + [header.map(csvCell).join(";"), ...rows.map((row) => row.map(csvCell).join(";"))].join("\r\n")
}

// ── Equipment naming (joined names instead of codes) ─────────────────────────

export const LOCOMOTIVE_TYPES = new Set(["locomotive", "diesel"])

/** "МПЭ-2у №1": model and factory number; falls back gracefully when a part is missing. */
export function equipmentTitle(item: ScheduleItem): string {
  const model = item.asset_model?.trim()
  const serial = item.asset_serial?.trim()
  if (model && serial) return `${model} №${serial}`
  if (model) return model
  if (serial) return `${item.asset_type_name ?? item.asset_type ?? "Единица"} №${serial}`
  return item.unit
}

/** "Локомотив · Инв. № 38390". */
export function equipmentSubtitle(item: ScheduleItem): string {
  const parts = [item.asset_type_name ?? item.asset_type ?? ""]
  parts.push(`Инв. № ${item.asset_inv_number ?? inventoryNumberOf(item)}`)
  return parts.filter(Boolean).join(" · ")
}

/** "ТО-1 — ТО-1" -> "ТО-1". */
export function intervalCode(type: string): string {
  return type.split(" — ")[0].trim()
}

const INTERVAL_TITLES: Record<string, string> = {
  "ТО-1": "Техническое обслуживание №1",
  "ТО-2": "Техническое обслуживание №2",
  "ТО-3": "Техническое обслуживание №3",
  "ТР-1": "Текущий ремонт №1",
  "ТР-2": "Текущий ремонт №2",
  "ТР-3": "Текущий ремонт №3",
  "СР": "Средний ремонт",
  "КР": "Капитальный ремонт",
}

/** Full name of a maintenance interval; unknown codes are shown as they are. */
export function intervalTitle(type: string): string {
  const code = intervalCode(type)
  if (code.toLowerCase().startsWith("test")) return "Тестовый интервал"
  return INTERVAL_TITLES[code] ?? type
}

/** Which family a code belongs to; drives the icon of the interval chip. */
export function intervalKind(type: string): "to" | "tr" | "sr" | "kr" | "other" {
  const code = intervalCode(type)
  if (code.startsWith("ТО")) return "to"
  if (code.startsWith("ТР")) return "tr"
  if (code === "СР") return "sr"
  if (code === "КР") return "kr"
  return "other"
}

// ── Manual rescheduling (drag and drop on the Gantt chart) ───────────────────

export const MAX_RESCHEDULE_DAYS = 366 // same limit as the API

const MS_PER_DAY = 86_400_000

/** `YYYY-MM-DD` -> UTC midnight, so day arithmetic never trips over daylight-saving changes. */
function utcDay(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number)
  return Date.UTC(y, m - 1, d)
}

export function diffDaysIso(fromIso: string, toIso: string): number {
  return Math.round((utcDay(toIso) - utcDay(fromIso)) / MS_PER_DAY)
}

export function shiftDate(iso: string, days: number): string {
  return new Date(utcDay(iso) + days * MS_PER_DAY).toISOString().slice(0, 10)
}

/** Local calendar date of a JS Date as `YYYY-MM-DD` (toISOString would use UTC and be a day off at night). */
export function toIsoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${date.getFullYear()}-${month}-${day}`
}

/** Whole days for a horizontal pointer movement. */
export function shiftFromPixels(deltaPx: number, dayWidthPx: number): number {
  if (!Number.isFinite(deltaPx) || !Number.isFinite(dayWidthPx) || dayWidthPx <= 0) return 0
  return Math.round(deltaPx / dayWidthPx)
}

/** Keep `base + shift` between `minIso` and `maxIso` (inclusive); returns the allowed shift. */
export function clampShift(baseIso: string, shift: number, minIso: string, maxIso: string): number {
  const lowest = diffDaysIso(baseIso, minIso)
  const highest = diffDaysIso(baseIso, maxIso)
  // A bar already outside the window (e.g. overdue, before "today") may only move inside it.
  return Math.min(Math.max(shift, lowest), Math.max(highest, lowest))
}

/** Only unfinished, system-planned work can be moved: scheduled plans and forecasts, never work orders. */
export function isReschedulable(item: ScheduleItem, canUpdate: boolean): boolean {
  if (!canUpdate) return false
  if (item.entity_type === "forecast") return !!item.interval_id
  if (item.entity_type === "maintenance_plan") {
    return !!item.plan_id && (item.status === "upcoming" || item.status === "overdue")
  }
  return false
}

export function validateRescheduleDate(newIso: string, todayIso: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(newIso)) return "Укажите дату"
  if (diffDaysIso(todayIso, newIso) < 0) return "Нельзя перенести на прошедшую дату"
  if (diffDaysIso(todayIso, newIso) > MAX_RESCHEDULE_DAYS) return `Нельзя переносить дальше, чем на ${MAX_RESCHEDULE_DAYS} дн.`
  return null
}

export type RescheduleImpact = {
  fromIso: string
  toIso: string
  shiftDays: number // vs the date the bar has now
  recommendedIso: string // what the system recommends
  vsRecommendedDays: number // > 0: later than recommended, < 0: earlier
  remainingAtNewKm: number | null // km left to the threshold on the new date (can be negative)
  overrunKm: number // > 0 when the threshold would be exceeded by then
  level: "ok" | "info" | "danger"
}

/**
 * What a move means in kilometres. `remainingKm` is the distance to the threshold today; the unit keeps
 * running `dailyKm` per day until the new date, so a later date can overrun the threshold.
 */
export function rescheduleImpact(
  item: ScheduleItem,
  toIso: string,
  todayIso: string,
  dailyKm: number | null,
): RescheduleImpact {
  const fromIso = item.startDate.slice(0, 10)
  const recommendedIso = (item.dateManual && item.recommendedDate ? item.recommendedDate : item.startDate).slice(0, 10)
  const remaining = toNum(item.remainingKm)
  const daysFromToday = Math.max(0, diffDaysIso(todayIso, toIso))
  const remainingAtNewKm =
    remaining !== null && dailyKm !== null && dailyKm > 0 ? remaining - dailyKm * daysFromToday : null
  const vsRecommendedDays = diffDaysIso(recommendedIso, toIso)
  const rawOverrunKm = remainingAtNewKm !== null && remainingAtNewKm < 0 ? Math.abs(remainingAtNewKm) : 0
  // The recommended day is the day the threshold is reached (rounded up), so it is never an overrun by itself.
  // A threshold that is ALREADY exceeded today stays an overrun whatever date is chosen.
  const forgiven = remaining !== null && remaining > 0 && vsRecommendedDays <= 0
  const overrunKm = forgiven ? 0 : rawOverrunKm
  return {
    fromIso,
    toIso,
    shiftDays: diffDaysIso(fromIso, toIso),
    recommendedIso,
    vsRecommendedDays,
    remainingAtNewKm,
    overrunKm,
    level: overrunKm > 0 ? "danger" : vsRecommendedDays < 0 ? "info" : "ok",
  }
}

const PALETTE = [
  { color: "#14b8a6", bar: "bg-teal-500", text: "text-teal-700 dark:text-teal-300", border: "border-teal-400" },
  { color: "#06b6d4", bar: "bg-cyan-500", text: "text-cyan-700 dark:text-cyan-300", border: "border-cyan-400" },
  { color: "#84cc16", bar: "bg-lime-500", text: "text-lime-700 dark:text-lime-300", border: "border-lime-400" },
  { color: "#ec4899", bar: "bg-pink-500", text: "text-pink-700 dark:text-pink-300", border: "border-pink-400" },
  { color: "#6366f1", bar: "bg-indigo-500", text: "text-indigo-700 dark:text-indigo-300", border: "border-indigo-400" },
  { color: "#0ea5e9", bar: "bg-sky-500", text: "text-sky-700 dark:text-sky-300", border: "border-sky-400" },
] as const

export type CodeStyle = { color: string; bar: string; text: string; border: string }

/** Stable colour for a work-type code that has no hand-picked colour (new codes added to the directory). */
export function paletteForCode(code: string): CodeStyle {
  let hash = 0
  for (const char of code) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return PALETTE[hash % PALETTE.length]
}
