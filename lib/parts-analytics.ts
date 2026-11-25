// Pure helpers for the spare-parts analytics cards (status, hints, conclusion lines).
// Run tests with: npm run test:unit
import { fmtInt, fmtMoney, fmtNumber, fmtPercent } from "./format.ts"
import type { PartsConsumption, PartsHorizon, RepairForecast, StockCoverage, StockRiskItem, StockStatus } from "./api.ts"

export const HORIZONS: { value: PartsHorizon; label: string; days: number }[] = [
  { value: "quarter", label: "Квартал", days: 90 },
  { value: "half", label: "Полгода", days: 180 },
  { value: "year", label: "Год", days: 365 },
]

export const STOCK_STATUS: Record<StockStatus, { label: string; badge: string; rank: number }> = {
  critical: { label: "Критично", badge: "bg-red-100 text-red-700 dark:bg-red-900/60 dark:text-red-200", rank: 0 },
  order_now: { label: "Заказать сейчас", badge: "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200", rank: 1 },
  ok: { label: "В норме", badge: "bg-green-100 text-green-700 dark:bg-green-900/60 dark:text-green-200", rank: 2 },
  no_data: { label: "Нет остатков", badge: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300", rank: 3 },
}

export const ASSET_TYPE_LABEL: Record<string, string> = { locomotive: "Электровозы", diesel: "Тепловозы", wagon: "Вагоны" }
export const COHORT_LABEL: Record<string, string> = { new: "Новые", middle: "Средние", old: "Старые", unknown: "Возраст неизвестен" }

/** Russian hint for a failed request (403 / 404 / other). */
export function partsErrorHint(status: number | undefined, fallback?: string): string {
  if (status === 403) return "Нет прав на просмотр этой аналитики."
  if (status === 404) return "Участок не найден или недоступен для вашей роли."
  if (status === 401) return "Сессия истекла. Войдите заново."
  return fallback ? `Не удалось загрузить данные: ${fallback}` : "Не удалось загрузить данные. Попробуйте обновить."
}

/** "5 дн." / "сегодня" / "—". Negative means already overdue. */
export function daysText(days: number | null | undefined, empty = "—"): string {
  if (days === null || days === undefined || !Number.isFinite(days)) return empty
  if (days < 0) return `просрочено ${fmtInt(-days)} дн.`
  if (days === 0) return "сегодня"
  return `${fmtInt(days)} дн.`
}

export function orderArrivalText(item: Pick<StockRiskItem, "order_arrives_in_days">): string {
  if (item.order_arrives_in_days === null || item.order_arrives_in_days === undefined) return "заказа нет"
  return `через ${fmtInt(item.order_arrives_in_days)} дн.`
}

/** Short text for a coverage chip: "хватает" or "не хватает 90 шт · 378,000 тыс". */
export function coverageText(c: StockCoverage | undefined, unit: string | null): string {
  if (!c || c.covers === undefined) return "нет данных"
  if (c.covers) return "хватает"
  const qty = c.shortfall_qty === undefined ? "" : `${fmtNumber(c.shortfall_qty)} ${unit ?? ""}`.trim()
  const money = c.shortfall_cost === undefined ? "" : fmtMoney(c.shortfall_cost)
  return `не хватает ${[qty, money].filter(Boolean).join(" · ")}`.trim()
}

export function stockCounts(items: { status: StockStatus }[]): Record<StockStatus, number> {
  const out: Record<StockStatus, number> = { critical: 0, order_now: 0, ok: 0, no_data: 0 }
  for (const i of items) out[i.status] += 1
  return out
}

/** Only when real stock exists (not no_data) and demand is known. */
export function stockCoverDays(item: Pick<StockRiskItem, "status" | "runs_out_in_days">): number | null {
  if (item.status === "no_data") return null
  return item.runs_out_in_days ?? null
}

export function trendView(trend: "up" | "down" | "flat" | null, pct: number | null): { arrow: string; cls: string; text: string } {
  if (trend === null || pct === null) return { arrow: "", cls: "text-gray-400", text: "нет тренда" }
  if (trend === "up") return { arrow: "▲", cls: "text-red-600 dark:text-red-400", text: fmtPercent(pct, true) }
  if (trend === "down") return { arrow: "▼", cls: "text-green-600 dark:text-green-400", text: fmtPercent(pct, true) }
  return { arrow: "►", cls: "text-gray-500", text: fmtPercent(pct, true) }
}

export function forecastConclusion(f: RepairForecast, horizonLabel: string): string {
  const s = f.summary
  if (s.total === 0) return `На горизонте «${horizonLabel}» ремонтов не ожидается.`
  const loco = s.by_asset_type.locomotive + s.by_asset_type.diesel
  const parts = [
    `За «${horizonLabel}» ожидается ${fmtInt(s.total)} ремонтов: ${fmtInt(s.planned)} по плану и ${fmtInt(s.projected)} расчётных`,
    `локомотивы ${fmtInt(loco)}, вагоны ${fmtInt(s.by_asset_type.wagon)}`,
  ]
  const old = s.by_age.old
  if (old > 0) parts.push(`на старую технику приходится ${fmtInt(old)} (${fmtPercent((old / s.total) * 100)})`)
  const tail = s.overdue > 0 ? ` Просрочено уже сейчас: ${fmtInt(s.overdue)}.` : ""
  return `${parts.join("; ")}.${tail}`
}

export function savingConclusion(c: PartsConsumption): string {
  const top = c.saving_potential[0]
  if (c.totals.overuse_cost <= 0 || !top) return "Расход выше нормы не обнаружен."
  const share = c.totals.cost > 0 ? (c.totals.overuse_cost / c.totals.cost) * 100 : 0
  return `Перерасход сверх норм за ${fmtInt(c.months)} мес.: ${fmtMoney(c.totals.overuse_cost)} сум (${fmtPercent(share)} от расхода ${fmtMoney(c.totals.cost)} сум). Больше всего: «${top.name}» ${fmtNumber(top.over_qty)} ${top.unit ?? ""} на ${fmtMoney(top.over_cost)} сум. Проверьте списания по этим позициям.`
}

export function stockConclusion(s: { critical: number; order_now: number; shortfall_cost_quarter: number }): string {
  if (s.critical === 0 && s.order_now === 0) return "Срочных закупок не требуется."
  return `Критично ${fmtInt(s.critical)}, заказать сейчас ${fmtInt(s.order_now)} позиций. Дефицит на квартал: ${fmtMoney(s.shortfall_cost_quarter)} сум.`
}
