import { fmtPercent } from "./format.ts"
// Pure helpers of the weighing-scale (Vesovoy) page: labels, tones, texts. No React.
// Run the tests with: npm run test:unit

export type MatchStatus = "pending" | "ok" | "no_loco" | "no_gtk_train" | "excluded"
export type Health = "ok" | "warn" | "alert" | "unknown"

export type PostStatus = {
  code: string
  name: string
  last_weighing_at: string | null
  last_pull_at: string | null
  silent_hours: number | null
  health: Health
  collector: "ok" | "stale" | "never"
  trains_24h: number
  tonnes_24h: number | string
  trains_7d: number
  match_rate_7d: number | null
  unmatched: number
}

export type ScalesStatus = {
  posts: PostStatus[]
  trains_total: number
  unmatched_total: number
  before_gtk_history: number
  gtk_history_from: string | null
  first_train_at: string | null
  last_train_at: string | null
}

export type ScaleTrain = {
  id: string
  post_code: string
  src_id: number
  started_at: string | null
  finished_at: string | null
  loco_number: string | null
  loco_asset_id: string | null
  loco_inv_number: string | null
  gtk_train_id: number | null
  declared_wagons: number | null
  wagon_rows: number
  dump_count: number
  traction_count: number
  carriages_total: number
  carriages_linked: number
  reported_weight_t: number | string | null
  net_total_t: number | string | null
  net_source: string | null
  cargo_name: string | null
  excavator: number | null
  match_status: MatchStatus
  match_method: string | null
  flags: string[]
}

export type LocoCandidate = {
  loco_gtk_id: number
  garage_number: string | null
  name: string | null
  asset_id: string | null
  asset_inv_number: string | null
  overlap_min: number
}

export type UnmatchedTrain = ScaleTrain & { candidates: LocoCandidate[] }
export type Page<T> = { items: T[]; total: number; limit: number; offset: number }

export type Correction = {
  id: string
  kind: "loco_alias" | "train_exclude" | "train_gtk"
  loco_number: string | null
  train_id: string | null
  asset_id: string | null
  asset_inv_number?: string | null
  gtk_train_id: number | null
  note: string | null
  is_active: boolean
  created_at: string
}

export const STATUS_LABEL: Record<MatchStatus, string> = {
  ok: "Распознан",
  pending: "В обработке",
  no_loco: "Локомотив не определён",
  no_gtk_train: "Нет состава GTK",
  excluded: "Исключён",
}

export const STATUS_TONE: Record<MatchStatus, string> = {
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  pending: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  no_loco: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  no_gtk_train: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  excluded: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
}

export const FLAG_LABEL: Record<string, string> = {
  count_mismatch: "Число вагонов не совпало с GTK",
  default_tare: "Тара по умолчанию (не взвешена)",
  overload: "Перегруз выше грузоподъёмности",
  negative_net: "Отрицательная масса",
  no_wagon_rows: "Нет строк по вагонам",
  partial_wagon_rows: "Строки вагонов неполные",
  estimated_net: "Масса оценена по весу состава",
}

export const flagLabel = (flag: string): string => FLAG_LABEL[flag] ?? flag

export const HEALTH_TONE: Record<Health, string> = {
  ok: "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900",
  warn: "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900",
  alert: "bg-red-50 text-red-800 ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-900",
  unknown: "bg-gray-50 text-gray-700 ring-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-800",
}

export function silentText(hours: number | null): string {
  if (hours === null) return "нет данных"
  if (hours < 1) return `${Math.max(0, Math.round(hours * 60))} мин назад`
  if (hours < 48) return `${Math.round(hours)} ч назад`
  return `${Math.round(hours / 24)} сут назад`
}

export function healthText(post: Pick<PostStatus, "health" | "silent_hours">): string {
  if (post.health === "unknown") return "Данных ещё нет"
  if (post.health === "ok") return `Работает: последний вагон ${silentText(post.silent_hours)}`
  return `Давно нет взвешиваний: ${silentText(post.silent_hours)}`
}

export function collectorText(state: PostStatus["collector"]): string {
  return state === "ok" ? "сборщик на связи" : state === "stale" ? "сборщик не отвечает более 10 мин" : "сборщик ещё не подключался"
}

export const num = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined || value === "") return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function tonnesText(value: number | string | null | undefined, estimated = false): string {
  const n = num(value)
  if (n === null) return "—"
  return `${estimated ? "≈ " : ""}${n.toLocaleString("ru-RU", { maximumFractionDigits: 0 })} т`
}

export const netText = (train: Pick<ScaleTrain, "net_total_t" | "net_source">): string =>
  tonnesText(train.net_total_t, train.net_source === "estimated")

export function percentText(value: number | null): string {
  return value === null ? "—" : fmtPercent(value * 100)
}

export function wagonsText(t: Pick<ScaleTrain, "dump_count" | "carriages_total" | "carriages_linked" | "match_status">): string {
  if (t.match_status !== "ok") return `${t.dump_count} вагонов на весах`
  return `${t.dump_count} на весах, ${t.carriages_total} в GTK, связано с ОС: ${t.carriages_linked}`
}

export function candidateText(c: LocoCandidate): string {
  const name = c.name ?? `GTK ${c.loco_gtk_id}`
  const asset = c.asset_inv_number ? `ОС ${c.asset_inv_number}` : "не связан с ОС"
  return `${name} (${asset}), совпадение ${Math.round(c.overlap_min)} мин`
}

export function correctionText(c: Correction): string {
  if (c.kind === "loco_alias") return `Номер «${c.loco_number}» = локомотив ${c.asset_inv_number ?? c.asset_id}`
  if (c.kind === "train_exclude") return "Состав исключён из учёта"
  return `Состав привязан к составу GTK ${c.gtk_train_id}`
}

export function dateTimeText(value: string | null): string {
  if (!value) return "—"
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
}

export type TripBasis = "own" | "train_avg" | "estimated" | "unknown"

export type WagonTrip = {
  train_id: string
  started_at: string | null
  post_code: string
  asset_id: string | null
  inv_number: string | null
  carriage_gtk_id: number
  gtk_name: string | null
  gtk_inventory_number: string | null
  position: number | null
  tonnes: number | string | null
  basis: TripBasis
  loco_number: string | null
  loco_asset_id: string | null
  loco_inv_number: string | null
  cargo_name: string | null
  excavator: number | null
  train_total_t: number | string | null
}

export type WagonTotal = {
  asset_id: string | null
  inv_number: string | null
  carriage_gtk_id: number
  gtk_name: string | null
  gtk_inventory_number: string | null
  trips: number
  tonnes: number | string
  avg_tonnes: number | string | null
  own_trips: number
  last_at: string | null
}

export type WagonTripPage = Page<WagonTrip> & { wagons_total: number; tonnes_total: number | string }
export type WagonTotalPage = Page<WagonTotal> & { trips_total: number; tonnes_total: number | string }

export const BASIS_LABEL: Record<TripBasis, string> = {
  own: "взвешивание вагона",
  train_avg: "доля состава",
  estimated: "оценка по весу состава",
  unknown: "неизвестно",
}

/** The wagon as people know it: the TOIR inventory number, else what GTK calls the carriage. */
export function wagonLabel(w: { inv_number: string | null; gtk_inventory_number: string | null; gtk_name: string | null; carriage_gtk_id: number }): string {
  return w.inv_number ?? w.gtk_inventory_number ?? w.gtk_name ?? `GTK ${w.carriage_gtk_id}`
}

export const isLinked = (w: { asset_id: string | null }): boolean => w.asset_id !== null

/** Tonnes of one trip; «≈» when it is a share/estimate rather than the car's own weighing. */
export function tripTonnes(t: Pick<WagonTrip, "tonnes" | "basis">): string {
  if (t.basis === "unknown") return "—"
  return `${t.basis === "own" ? "" : "≈ "}${(num(t.tonnes) ?? 0).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} т`
}

export function ownShareText(w: Pick<WagonTotal, "trips" | "own_trips">): string {
  return w.trips ? `${fmtPercent((w.own_trips / w.trips) * 100)} по собственному взвешиванию` : "—"
}
