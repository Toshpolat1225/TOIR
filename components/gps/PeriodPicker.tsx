"use client"

// «С [дата] по [дата]» + quick presets. Empty dates = «last N days» (the old behaviour); the server allows at most 31 days.
const MAX_DAYS = 31
const iso = (d: Date): string => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const shift = (day: string, delta: number): string => { const d = new Date(`${day}T12:00:00`); d.setDate(d.getDate() + delta); return iso(d) }
const spanOf = (from: string, to: string): number => Math.round((Date.parse(`${to}T12:00:00`) - Date.parse(`${from}T12:00:00`)) / 86_400_000) + 1

export function periodDates(days: number, from: string, to: string): { from: string; to: string } {
  const today = iso(new Date())
  if (from || to) { const end = to || today; return { from: from || shift(end, -13), to: end } }
  return { from: shift(today, -(days - 1)), to: today }
}

export function PeriodPicker({ days, dateFrom, dateTo, presets = [7, 14, 31], onChange, className = "" }: {
  days: number; dateFrom: string; dateTo: string; presets?: number[]; className?: string
  onChange: (next: { days: number; date_from: string; date_to: string }) => void
}) {
  const today = iso(new Date())
  const cur = periodDates(days, dateFrom, dateTo)
  const span = spanOf(cur.from, cur.to)
  const apply = (from: string, to: string) => {
    const t = to > today ? today : to
    let f = from > t ? t : from
    if (spanOf(f, t) > MAX_DAYS) f = shift(t, -(MAX_DAYS - 1))
    onChange({ days: spanOf(f, t), date_from: f, date_to: t })
  }
  const input = "rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
  return (
    <div className={`inline-flex flex-wrap items-center gap-2 text-sm text-gray-700 dark:text-gray-200 ${className}`} role="group" aria-label="Период">
      <label className="inline-flex items-center gap-1.5">С
        <input type="date" value={cur.from} max={cur.to} onChange={(e) => e.target.value && apply(e.target.value, cur.to)} aria-label="Период с" className={input} data-testid="period-from" />
      </label>
      <label className="inline-flex items-center gap-1.5">по
        <input type="date" value={cur.to} min={cur.from} max={today} onChange={(e) => e.target.value && apply(cur.from, e.target.value)} aria-label="Период по" className={input} data-testid="period-to" />
      </label>
      <span className="inline-flex overflow-hidden rounded-full ring-1 ring-gray-300 dark:ring-gray-700">
        {presets.map((d) => {
          const on = cur.to === today && span === d
          return (
            <button key={d} type="button" aria-pressed={on} onClick={() => onChange({ days: d, date_from: shift(today, -(d - 1)), date_to: today })}
              className={`px-2.5 py-1 ${on ? "bg-indigo-600 text-white" : "bg-white text-gray-800 dark:bg-gray-900 dark:text-gray-100"}`}>{d === 1 ? "сутки" : `${d} дн.`}</button>
          )
        })}
      </span>
    </div>
  )
}
