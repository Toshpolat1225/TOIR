// One place for number display rules (used by the main site and the demo alike):
//   percent -> 2 digits after the decimal point; money -> 3 digits (compact: тыс / млн / млрд); any other number -> 1 digit.
const nf = (digits: number) => new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits })
const NF1 = nf(1)
const NF2 = nf(2)
const NF3 = nf(3)
const NF0 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 })

function finite(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value)
}

/** Plain value (km, hours, count with fraction, ratio): 1 digit. */
export function fmtNumber(value: number | null | undefined, empty = "—"): string {
  return finite(value) ? NF1.format(value) : empty
}

/** Whole count (orders, assets): no fraction. */
export function fmtInt(value: number | null | undefined, empty = "—"): string {
  return finite(value) ? NF0.format(value) : empty
}

/** Percent: 2 digits. `signed` adds a plus for positive values. */
export function fmtPercent(value: number | null | undefined, signed = false, empty = "—"): string {
  if (!finite(value)) return empty
  return `${signed && value > 0 ? "+" : ""}${NF2.format(value)}%`
}

/** Money (UZS): 3 digits, compact. 2 794 916 150 -> "2,795 млрд". */
export function fmtMoney(value: number | null | undefined, empty = "—"): string {
  if (!finite(value)) return empty
  const abs = Math.abs(value)
  if (abs >= 1e9) return `${NF3.format(value / 1e9)} млрд`
  if (abs >= 1e6) return `${NF3.format(value / 1e6)} млн`
  if (abs >= 1e3) return `${NF3.format(value / 1e3)} тыс`
  return NF0.format(value)
}
