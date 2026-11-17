// Pure helpers of the asset map page (no React, no Google): labels, colours, links, filtering, bounds.
// Run the tests with: npm run test:unit

// "train" = a wagon has no GPS: it is drawn where the locomotive of its open GTK train is
// "gtk_gps" = a locomotive drawn at GTK's OWN GPS fix (the newer of its two trackers)
export type MapSource = "wialon" | "gtk" | "gtk_gps" | "train"

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
  // locomotives that have BOTH trackers: the verdict of comparing Wialon and GTK GPS, and the OTHER tracker's fix
  gps_verdict?: string | null
  gps_diff_m?: number | null
  gps_wialon_age_min?: number | null
  gps_gtk_age_min?: number | null
  alt_source?: "wialon" | "gtk_gps" | null
  alt_lat?: number | null
  alt_lon?: number | null
  alt_position_at?: string | null
}

/** A point that comes from a GPS tracker of its own (not GTK's carriage state, not a train): it has a speed and an online state. */
export const isTracked = (source: MapSource): boolean => source === "wialon" || source === "gtk_gps"

export const SOURCE_LABEL: Record<MapSource, string> = { wialon: "Wialon (GPS)", gtk: "GTK", gtk_gps: "GTK GPS", train: "Состав (по локомотиву)" }

export const UNPLACED_LABEL: Record<string, string> = {
  no_link: "нет привязки к Wialon/GTK",
  no_position: "привязан, но координат нет",
}

/** Marker colours: Wialon online = green, Wialon silent = grey, GTK = blue, wagon in a train = orange. */
export function markerColor(point: Pick<MapPoint, "source" | "online">): string {
  if (point.source === "gtk") return "#2563eb"
  if (point.source === "train") return "#d97706"
  if (point.source === "gtk_gps") return point.online ? "#0d9488" : "#6b7280"
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

// ---- the "without coordinates" page: why an asset is not on the map -----------------------------------------
export type UnplacedDetail =
  | "no_link" | "wialon_unit_missing" | "wialon_no_fix" | "gtk_locomotive_only" | "gtk_carriage_missing" | "gtk_no_coords" | "train_no_gps"

export type GtkCandidate = {
  gtk_id: number
  name?: string | null
  reg_number?: string | null
  inventory_number?: string | null
  is_active: boolean
  has_coordinates: boolean
  match: "inv_and_reg" | "inv" | "reg"
  taken_by_inv_number?: string | null
}

export type UnplacedItem = {
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
  group: "no_link" | "no_position"
  reason: UnplacedDetail
  asset_created_at?: string | null
  wialon_external_id?: string | null
  wialon_unit_id?: string | null
  wialon_unit_name?: string | null
  wialon_linked_at?: string | null
  wialon_first_seen_at?: string | null
  wialon_last_message_at?: string | null
  wialon_last_synced_at?: string | null
  gtk_external_id?: string | null
  gtk_carriage_id?: number | null
  gtk_carriage_name?: string | null
  gtk_linked_at?: string | null
  gtk_first_seen_at?: string | null
  gtk_last_synced_at?: string | null
  gtk_is_active?: boolean | null
  train_number?: string | null
  train_has_locomotive?: boolean | null
  candidate?: GtkCandidate | null
}

export type UnplacedSummary = {
  total: number
  by_group: Record<string, number>
  by_reason: Record<string, number>
  by_type: { value: string; label: string; count: number }[]
  linkable: number
}

export type UnplacedPage = { items: UnplacedItem[]; total: number; limit: number; offset: number; summary: UnplacedSummary }

/** Short name of each reason (a column and a filter). */
export const DETAIL_LABEL: Record<UnplacedDetail, string> = {
  no_link: "Не привязан к Wialon/GTK",
  wialon_unit_missing: "Юнит Wialon не найден",
  wialon_no_fix: "Wialon не передаёт координаты",
  gtk_locomotive_only: "Только GTK: у локомотивов нет координат",
  gtk_carriage_missing: "Вагон не найден в GTK",
  gtk_no_coords: "GTK не передаёт координаты",
  train_no_gps: "В составе, у локомотива нет GPS",
}

export const DETAIL_ORDER: UnplacedDetail[] = [
  "no_link", "wialon_unit_missing", "wialon_no_fix", "gtk_locomotive_only", "gtk_carriage_missing", "gtk_no_coords", "train_no_gps",
]

/** "04.11.2026" or "" for a missing/invalid time. */
export function dateText(iso: string | null | undefined): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return ""
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`
}

/** "сегодня" / "8 дн." / "3 мес." / "1 г." since a moment. */
export function durationText(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return ""
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return ""
  const days = Math.max(0, Math.floor((now.getTime() - then) / 86_400_000))
  if (days < 1) return "сегодня"
  if (days < 60) return `${days} дн.`
  if (days < 730) return `${Math.round(days / 30)} мес.`
  return `${Math.round(days / 365)} г.`
}

function sinceDate(label: string, iso: string | null | undefined, now: Date): string {
  const date = dateText(iso)
  return date ? `${label} ${date} (${durationText(iso, now)})` : ""
}

/** WHY the asset is not on the map. */
export function reasonExplanation(item: UnplacedItem): string {
  switch (item.reason) {
    case "no_link":
      return item.asset_type === "locomotive" || item.asset_type === "diesel" || item.asset_type === "special_self_propelled"
        ? "Не привязан ни к Wialon, ни к GTK: системе неоткуда взять положение. Привяжите актив к юниту Wialon в карточке ОС."
        : item.candidate
          ? "Не привязан ни к Wialon, ни к GTK: системе неоткуда взять положение. Но в GTK есть похожий вагон (см. подсказку)."
          : "Не привязан ни к Wialon, ни к GTK, а в GTK нет вагона с таким инвентарным или регистрационным номером."
    case "wialon_unit_missing":
      return `Привязан к юниту Wialon ${item.wialon_external_id ?? ""}, но такого юнита нет в данных последней синхронизации Wialon (юнит удалён или не попал в выгрузку).`.replace("  ", " ")
    case "wialon_no_fix":
      return `Юнит Wialon «${item.wialon_unit_name ?? item.wialon_unit_id ?? ""}» найден, но корректной позиции от него нет (нет GPS-сигнала или координаты 0,0).`
    case "gtk_locomotive_only":
      return "Привязан только к GTK, а GTK не передаёт координаты локомотивов. Нужна привязка к юниту Wialon."
    case "gtk_carriage_missing":
      return `Привязан к вагону GTK ${item.gtk_external_id ?? ""}, но такого вагона нет в данных последней синхронизации GTK.`.replace("  ", " ")
    case "gtk_no_coords":
      return "Вагон есть в GTK, но GTK не передаёт для него координаты, и в составе с локомотивом он сейчас не числится."
    case "train_no_gps":
      return item.train_has_locomotive === false
        ? `Вагон числится в составе № ${item.train_number ?? ""}, в котором нет локомотива; собственных координат GTK тоже не передаёт.`
        : `Вагон числится в составе № ${item.train_number ?? ""}, но у локомотива состава нет GPS-позиции в Wialon; собственных координат GTK тоже не передаёт.`
  }
}

/** HOW LONG: since when the system (or the source) knows this asset. The history of positions is not stored. */
export function sinceText(item: UnplacedItem, now: Date = new Date()): string {
  const parts: string[] = []
  switch (item.reason) {
    case "no_link":
      parts.push(sinceDate("В системе с", item.asset_created_at, now) || "Время появления в системе неизвестно")
      parts.push("привязки не было")
      break
    case "wialon_unit_missing":
      parts.push(sinceDate("Привязан к Wialon с", item.wialon_linked_at, now) || "Время привязки неизвестно")
      break
    case "wialon_no_fix":
      parts.push(sinceDate("Юнит в Wialon виден с", item.wialon_first_seen_at, now) || "Время появления юнита неизвестно")
      parts.push(item.wialon_last_message_at ? `последнее сообщение ${ageText(item.wialon_last_message_at, now)}` : "сообщений от юнита не было")
      break
    case "gtk_locomotive_only":
    case "gtk_carriage_missing":
      parts.push(sinceDate("Привязан к GTK с", item.gtk_linked_at, now) || "Время привязки неизвестно")
      break
    case "gtk_no_coords":
    case "train_no_gps":
      parts.push(sinceDate("GTK видит вагон с", item.gtk_first_seen_at, now) || "Время появления вагона в GTK неизвестно")
      parts.push(item.gtk_last_synced_at ? `последняя синхронизация ${ageText(item.gtk_last_synced_at, now)}` : "синхронизации не было")
      break
  }
  return parts.join("; ")
}

/** FROM WHERE: the source records tied to the asset. */
export function sourceText(item: UnplacedItem): string {
  const parts: string[] = []
  if (item.wialon_external_id) parts.push(`Wialon: ${item.wialon_unit_name ? `«${item.wialon_unit_name}» ` : ""}(${item.wialon_unit_id ?? item.wialon_external_id}${item.wialon_unit_id ? "" : ", не найден"})`)
  if (item.gtk_external_id) parts.push(`GTK: ${item.gtk_carriage_name ? `«${item.gtk_carriage_name}» ` : ""}(${item.gtk_carriage_id ?? item.gtk_external_id}${item.gtk_carriage_id != null ? "" : ", не найден"})`)
  return parts.length ? parts.join("; ") : "нет привязок"
}

/** A hint for an unlinked wagon: the GTK carriage that probably is it. */
export function candidateText(c: GtkCandidate | null | undefined): string | null {
  if (!c) return null
  const match = c.match === "inv_and_reg" ? "совпали инв. и рег. номер" : c.match === "inv" ? "совпал инв. номер" : "совпал рег. номер"
  const label = `«${c.name ?? c.gtk_id}» (инв. ${c.inventory_number ?? "—"}, рег. ${c.reg_number ?? "—"})`
  const coords = c.has_coordinates ? "в GTK у него есть координаты" : "координат в GTK нет"
  if (c.taken_by_inv_number) return `Похож вагон GTK ${label}, но он уже привязан к активу ${c.taken_by_inv_number}: возможно, дубликат.`
  return `Возможно, это вагон GTK ${label}: ${match}; ${coords}.`
}
