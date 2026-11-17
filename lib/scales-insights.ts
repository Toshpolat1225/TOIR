// Types and pure helpers of the weighing-scale command center (overview, train / wagon / locomotive cards). No React.
// Run the tests with: npm run test:unit

import type { TripBasis } from "./scales-view.ts"

export type Num = number | string

export type Kpi = {
  trains: number
  wagon_trips: number
  tonnes: Num
  avg_train_t: Num | null
  avg_car_t: Num | null
  overload_share: number | null
  matched_share: number | null
  estimated_share: number | null
  active_wagons: number
  active_locos: number
}
export type DayPoint = { day: string; post_code: string; trains: number; tonnes: Num }
export type HourPoint = { hour: number; post_code: string; trains: number; tonnes: Num }
export type NamedTotal = { key: string; label: string; trains: number; tonnes: Num }
export type LocoTop = {
  asset_id: string | null; loco_number: string | null; inv_number: string | null; model_name: string | null
  trains: number; tonnes: Num; avg_train_t: Num | null
}
export type WagonTop = { asset_id: string | null; carriage_gtk_id: number; label: string; trips: number; tonnes: Num }
export type LaneTrain = {
  id: string; post_code: string; started_at: string | null; finished_at: string | null; tonnes: Num | null
  match_status: string; loco_number: string | null
}
export type Quality = { by_status: Record<string, number>; flags: Record<string, number>; before_gtk_history: number }
export type Overview = {
  date_from: string; date_to: string; days: number; kpi: Kpi; previous: Kpi; daily: DayPoint[]; hourly: HourPoint[]
  by_cargo: NamedTotal[]; by_excavator: NamedTotal[]; top_locomotives: LocoTop[]; top_wagons: WagonTop[]; today: LaneTrain[]; quality: Quality
}

export type AssetIdentity = {
  asset_id: string; inv_number: string; name: string | null; asset_type: string; asset_type_name: string | null; status: string
  status_name: string | null; section_id: string | null; section_name: string | null; model_name: string | null; owner: string | null
  year_built: number | null; mileage: Num | null; last_maint_date: string | null; next_maint_date: string | null
}
export type PlanItem = { plan_id: string; interval_code: string; interval_name: string; status: string; scheduled_date: string | null; trigger_mileage: Num | null }
export type WorkOrderItem = { id: string; number: string; status: string; order_kind: string; description: string; date_start: string | null; closed_at: string | null }
export type Maintenance = {
  last_service_at: string | null; last_service_source: string | null; trips_since: number; tonnes_since: Num
  plans: PlanItem[]; work_orders: WorkOrderItem[]; work_orders_total: number
}
export type Split = { key: string; label: string; trips: number; tonnes: Num }
export type Totals = {
  trips: number; tonnes: Num; avg_tonnes: Num | null; own_trips: number; overload_trips: number; first_at: string | null; last_at: string | null
}
export type WorkDayPoint = { day: string; trips: number; tonnes: Num }
export type WagonTripBrief = {
  train_id: string; started_at: string | null; post_code: string; tonnes: Num | null; basis: TripBasis; position: number | null
  loco_number: string | null; cargo_name: string | null
}
export type GtkCarriageInfo = {
  carriage_gtk_id: number; name: string | null; reg_number: string | null; inventory_number: string | null; model_name: string | null
  is_active: boolean | null; is_loaded: boolean | null; lat: Num | null; lon: Num | null
}
export type WagonCard = {
  asset: AssetIdentity | null; gtk: GtkCarriageInfo | null; date_from: string; date_to: string; period: Totals; all_time: Totals
  daily: WorkDayPoint[]; by_cargo: Split[]; by_loco: Split[]; by_excavator: Split[]; recent: WagonTripBrief[]; maintenance: Maintenance | null
}
export type WialonInfo = { unit_id: string; name: string; last_message_at: string | null; speed: Num | null; lat: Num | null; lon: Num | null }
export type GtkLocoInfo = { gtk_id: number; name: string | null; garage_number: string | null; model_name: string | null; is_active: boolean | null }
export type TrainBrief = {
  id: string; started_at: string | null; post_code: string; tonnes: Num | null; net_source: string | null; cars: number
  cargo_name: string | null; match_status: string; flags: string[]
}
export type LocoCard = {
  asset: AssetIdentity; gtk: GtkLocoInfo | null; wialon: WialonInfo | null; numbers_used: string[]; date_from: string; date_to: string
  period: Totals; all_time: Totals; avg_cars: Num | null; daily: WorkDayPoint[]; by_cargo: Split[]; by_excavator: Split[]
  top_wagons: WagonTop[]; recent: TrainBrief[]; maintenance: Maintenance
}
export type UnitRow = {
  position: number | null; kind: "traction" | "dump"; gross_t: Num | null; tare_t: Num | null; net_t: Num | null; capacity_t: Num | null
  overload_t: Num | null; speed_kmh: Num | null; axles: number | null; weighed_at: string | null; carriage_gtk_id: number | null
  carriage_name: string | null; asset_id: string | null; inv_number: string | null
}
export type CarriageRow = {
  ord: number; carriage_gtk_id: number; gtk_name: string | null; model_name: string | null; asset_id: string | null; inv_number: string | null
  unit_position: number | null; net_t: Num | null
}
export type TrainGtkInfo = { gtk_train_id: number; number: string | null; title: string | null; begin_time: string | null; is_open: boolean | null }
export type CorrectionBrief = { id: string; kind: string; loco_number: string | null; note: string | null; created_at: string }
export type TrainCard = {
  id: string; post_code: string; post_name: string; src_id: number; started_at: string | null; finished_at: string | null
  registered_on: string | null; loco_number: string | null; cargo_name: string | null; excavator: number | null; operator_code: number | null
  declared_wagons: number | null; wagon_rows: number; dump_count: number; traction_count: number; reported_weight_t: Num | null
  doc_weight_t: Num | null; net_total_t: Num | null; net_source: string | null; offset_t: Num | null; avg_car_t: Num | null
  match_status: string; match_method: string | null; flags: string[]; loco: AssetIdentity | null; gtk_loco: GtkLocoInfo | null
  gtk_train: TrainGtkInfo | null; units: UnitRow[]; carriages: CarriageRow[]; prev_id: string | null; next_id: string | null
  corrections: CorrectionBrief[]
}

// ── numbers ──
export const n = (value: Num | null | undefined): number => {
  const x = Number(value)
  return value === null || value === undefined || value === "" || !Number.isFinite(x) ? 0 : x
}

export const fmt = (value: Num | null | undefined, digits = 0): string =>
  value === null || value === undefined ? "—" : n(value).toLocaleString("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: 0 })

/** Big tonnage compactly: 12 400 → «12,4 тыс. т», 1 250 000 → «1,25 млн т». */
export function tonnesCompact(value: Num | null | undefined): string {
  if (value === null || value === undefined) return "—"
  const x = n(value)
  if (Math.abs(x) >= 1_000_000) return `${(x / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} млн т`
  if (Math.abs(x) >= 10_000) return `${(x / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} тыс. т`
  return `${fmt(x, 0)} т`
}

export const percent = (share: number | null | undefined): string => (share === null || share === undefined ? "—" : `${Math.round(share * 100)}%`)

/** Change against the previous period in percent; null when there is nothing to compare with. */
export function deltaPercent(current: Num, previous: Num): number | null {
  const prev = n(previous)
  if (prev <= 0) return null
  return ((n(current) - prev) / prev) * 100
}

export function deltaText(delta: number | null): string {
  if (delta === null) return "нет базы сравнения"
  const rounded = Math.round(delta)
  return `${rounded > 0 ? "+" : ""}${rounded}% к прошлому периоду`
}

export const deltaTone = (delta: number | null): "up" | "down" | "flat" => (delta === null || Math.abs(delta) < 1 ? "flat" : delta > 0 ? "up" : "down")

// ── identity / links ──
export function wagonKey(w: { asset_id: string | null; carriage_gtk_id: number }): string {
  return w.asset_id ?? `gtk-${w.carriage_gtk_id}`
}
export const wagonHref = (w: { asset_id: string | null; carriage_gtk_id: number }): string => `/dashboard/scales/wagon/${wagonKey(w)}`
export const locoHref = (assetId: string): string => `/dashboard/scales/loco/${assetId}`
export const trainHref = (id: string): string => `/dashboard/scales/train/${id}`

export function parseWagonKey(key: string): { asset_id?: string; carriage_gtk_id?: number } {
  const gtk = /^gtk-(\d+)$/.exec(key)
  return gtk ? { carriage_gtk_id: Number(gtk[1]) } : { asset_id: key }
}

// ── colours / geometry shared by the charts ──
export const POST_COLORS = ["#2563eb", "#f59e0b", "#10b981", "#a855f7", "#ef4444"]
export const postColor = (code: string, codes: string[]): string => POST_COLORS[Math.max(0, codes.indexOf(code)) % POST_COLORS.length]

/** Fill of a car (0…1+) against its capacity; over 1 means overload. */
export const fillRatio = (net: Num | null | undefined, capacity: Num | null | undefined = 105): number => {
  const cap = n(capacity) || 105
  return Math.max(0, n(net) / cap)
}

/** Where a time sits on a 24 h lane, 0…1 (local clock of the browser, which is the operators' clock). */
export function dayFraction(iso: string | null): number | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return (d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60) / 1440
}

export function durationMinutes(start: string | null, end: string | null): number | null {
  if (!start || !end) return null
  const a = new Date(start).getTime()
  const b = new Date(end).getTime()
  return Number.isFinite(a) && Number.isFinite(b) && b >= a ? Math.round((b - a) / 60000) : null
}

export const dayLabel = (iso: string): string => {
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })
}

/** Evenly thinned labels so a long axis stays readable. */
export function axisTicks<T>(items: T[], max = 8): T[] {
  if (items.length <= max) return items
  const step = Math.ceil(items.length / max)
  return items.filter((_, i) => i % step === 0)
}

export const SERVICE_STATUS_LABEL: Record<string, string> = {
  scheduled: "Запланировано", in_progress: "В работе", blocked: "Заблокировано", completed: "Выполнено", pending: "Ожидает", cancelled: "Отменён",
}

export function sinceServiceText(m: Pick<Maintenance, "last_service_at" | "trips_since" | "tonnes_since">): string {
  if (!m.last_service_at) return "Дата последнего ТО неизвестна: введите «последнее ТО» в плане обслуживания, и здесь появится наработка с него."
  return `С последнего ТО (${new Date(m.last_service_at).toLocaleDateString("ru-RU")}): ${m.trips_since} рейсов, ${tonnesCompact(m.tonnes_since)}`
}
