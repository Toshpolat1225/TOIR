// Pure helpers for the "create work order" form: defaults that save typing and never break business rules.

export type WorkTypeLike = { id: string; unit_type: "locomotive" | "wagon"; duration_hours?: number | string | null }

/** `datetime-local` value (local time, minute precision). */
export function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function addHoursLocal(start: string, hours: number): string {
  const base = new Date(start)
  if (Number.isNaN(base.getTime())) return ""
  return toLocalInput(new Date(base.getTime() + Math.round(hours * 60) * 60000))
}

/** Which work types fit this asset: locomotives/diesels get "locomotive" types, wagons "wagon"; unknown kinds see all. */
export function unitTypeForAsset(assetType: string | null | undefined): "locomotive" | "wagon" | null {
  if (assetType === "locomotive" || assetType === "diesel") return "locomotive"
  if (assetType === "wagon") return "wagon"
  return null
}

export function workTypesForAsset<T extends WorkTypeLike>(types: T[], assetType: string | null | undefined): T[] {
  const unit = unitTypeForAsset(assetType)
  return unit ? types.filter((t) => t.unit_type === unit) : types
}

/** Sum of standard hours of the chosen types; `missing` lists ids without a duration (then no automatic end is set). */
export function totalHours(types: WorkTypeLike[], chosenIds: string[]): { hours: number; missing: string[] } {
  let hours = 0
  const missing: string[] = []
  for (const id of new Set(chosenIds)) {
    const value = Number(types.find((t) => t.id === id)?.duration_hours)
    if (Number.isFinite(value) && value > 0) hours += value
    else missing.push(id)
  }
  return { hours, missing }
}

export function formatHours(value: number | string | null | undefined): string {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return "—"
  if (n < 24) return `${Number.isInteger(n) ? n : n.toFixed(1).replace(".", ",")} ч`
  const days = Math.floor(n / 24)
  const rest = Math.round(n - days * 24)
  return rest ? `${days} дн. ${rest} ч` : `${days} дн.`
}

type PersonLike = { id: string; full_name: string; section_id: string | null; is_active: boolean }

function nameTokens(name: string): string[] {
  return name
    .toLocaleLowerCase("ru")
    .replace(/ё/g, "е")
    .replace(/[.,]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
}

/** Same person if surnames are equal and every following name part is equal or one side is just an initial. */
export function sameName(a: string, b: string): boolean {
  const x = nameTokens(a)
  const y = nameTokens(b)
  if (x.length === 0 || y.length === 0 || x[0] !== y[0]) return false
  const parts = Math.min(x.length, y.length)
  for (let i = 1; i < parts; i++) {
    if (x[i] === y[i]) continue
    if ((x[i].length === 1 || y[i].length === 1) && x[i][0] === y[i][0]) continue
    return false
  }
  return true
}

/**
 * The signed-in person as an employee: unique match by name among active staff (the user's own section first,
 * then everyone). There is no hard user↔employee link in the database, so ambiguity means "unknown".
 */
export function findMyEmployee<T extends PersonLike>(
  employees: T[],
  fullName: string | null | undefined,
  userSectionId: string | null | undefined
): T | null {
  if (!fullName?.trim()) return null
  const matches = employees.filter((e) => e.is_active && sameName(e.full_name, fullName))
  if (matches.length === 1) return matches[0]
  if (matches.length > 1 && userSectionId) {
    const inSection = matches.filter((e) => e.section_id === userSectionId)
    if (inSection.length === 1) return inSection[0]
  }
  return null
}

/** Executor default: the signed-in person if he is an employee of the chosen section (or no section chosen yet). */
export function defaultExecutorId(
  employees: PersonLike[],
  fullName: string | null | undefined,
  sectionId: string,
  userSectionId?: string | null
): string {
  const pool = sectionId ? employees.filter((e) => e.section_id === sectionId) : employees
  return findMyEmployee(pool, fullName, userSectionId)?.id ?? ""
}

/** Section default: the user's own section, otherwise the section of his employee card. */
export function defaultSectionId(
  employees: PersonLike[],
  fullName: string | null | undefined,
  userSectionId: string | null | undefined
): string {
  return userSectionId || findMyEmployee(employees, fullName, userSectionId)?.section_id || ""
}

/** Planned vs actual: positive = later than planned. Returns hours or null. */
export function lateHours(planned: string | null | undefined, actual: string | null | undefined): number | null {
  if (!planned || !actual) return null
  const diff = (new Date(actual).getTime() - new Date(planned).getTime()) / 3600000
  return Number.isFinite(diff) ? diff : null
}
