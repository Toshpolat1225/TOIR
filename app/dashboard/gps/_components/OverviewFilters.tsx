"use client"

import { useEffect, useState } from "react"
import {
  CAUSE_HINT, CAUSE_LABEL, CAUSE_ORDER, DATE_PRESETS, DAY_CHOICES, HEALTH_HINT, HEALTH_LABEL, HEALTH_ORDER, LINKS, LINK_LABEL, MAX_WINDOW_DAYS, SEVERITIES, SEVERITY_LABEL,
  daysBetween, datePreset, isIsoDay, toggleValue, windowText, type DatePreset, type FilterChip, type GpsFilters,
} from "@/lib/gps-analytics"
import { DISTANCE_HINT, DISTANCE_LABEL, DISTANCE_ORDER, POSITION_HINT, POSITION_LABEL, POSITION_ORDER } from "@/lib/gps-view"
import { ChipGroup, FilterChips, SavedViewsMenu, chipBtn, field } from "./ui"

export type SectionOption = { id: string; name: string }
const TYPE_LABEL: Record<string, string> = { locomotive: "Электровоз / агрегат", diesel: "Тепловоз", special_self_propelled: "Самоходная спецтехника" }

type Props = {
  filters: GpsFilters
  set: (patch: Partial<GpsFilters>, options?: { replace?: boolean }) => void
  facets: Record<string, Record<string, number>> | null
  sections: SectionOption[]
  qText: string
  onQText: (value: string) => void
  chips: FilterChip<GpsFilters>[]
  onReset: () => void
  total: number
  shown: number
  query: string
  onApplyView: (query: string) => void
  onExport: (format: "csv" | "xlsx") => void
  exporting: boolean
  offsetHours: number
}

export function OverviewFilters({ filters: f, set, facets, sections, qText, onQText, chips, onReset, total, shown, query, onApplyView, onExport, exporting, offsetHours }: Props) {
  const [advanced, setAdvanced] = useState(false)
  const [from, setFrom] = useState(f.date_from)
  const [to, setTo] = useState(f.date_to)
  const [dateError, setDateError] = useState<string | null>(null)
  useEffect(() => { setFrom(f.date_from); setTo(f.date_to) }, [f.date_from, f.date_to])

  const applyDates = (a: string, b: string) => {
    if (!isIsoDay(a) || !isIsoDay(b)) return
    const n = daysBetween(a, b)
    if (n < 1) return setDateError("Конец периода раньше начала")
    if (n > MAX_WINDOW_DAYS) return setDateError(`Не больше ${MAX_WINDOW_DAYS} дней`)
    setDateError(null)
    set({ date_from: a, date_to: b, page: 0 })
  }
  const presetOn = (id: DatePreset): boolean => {
    if (id === "7" || id === "14" || id === "30") {
      if (!f.date_from) return f.days === Number(id)
    }
    const p = datePreset(id, Date.now(), offsetHours)
    return f.date_from === p.date_from && f.date_to === p.date_to
  }
  const pickPreset = (id: DatePreset) => {
    if (id === "7" || id === "14" || id === "30") set({ days: Number(id), date_from: "", date_to: "", page: 0 })
    else set({ ...datePreset(id, Date.now(), offsetHours), page: 0 })
  }
  const types = Object.keys(facets?.asset_type ?? {}).sort()
  const typeOptions = (types.length ? types : f.asset_type).map((v) => ({ value: v, label: TYPE_LABEL[v] ?? v }))
  const sectionCount = (s: SectionOption): number | null => (facets?.section ? facets.section[s.id] ?? facets.section[s.name] ?? 0 : null)
  const multi = (key: "verdict" | "distance_verdict" | "cause" | "severity" | "health" | "asset_type") => (v: string) => set({ [key]: toggleValue(f[key], v), page: 0 } as Partial<GpsFilters>)
  const num = (key: "min_diff_m" | "min_silence_h" | "min_km" | "max_km") => (e: React.ChangeEvent<HTMLInputElement>) =>
    set({ [key]: e.target.value === "" || Number(e.target.value) < 0 ? "" : String(Number(e.target.value)), page: 0 } as Partial<GpsFilters>, { replace: true })
  const advancedCount = f.verdict.length + f.distance_verdict.length + f.cause.length + f.severity.length + f.health.length + f.asset_type.length + (f.link ? 1 : 0)
    + (f.min_diff_m ? 1 : 0) + (f.min_silence_h ? 1 : 0) + (f.min_km ? 1 : 0) + (f.max_km ? 1 : 0)

  return (
    <section className="space-y-3 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900" data-testid="gps-filter-bar" aria-label="Фильтры">
      <div className="flex flex-wrap items-center gap-2">
        <input type="search" value={qText} onChange={(e) => onQText(e.target.value)} placeholder="Инв. номер, название, модель, участок" aria-label="Поиск" className={`${field} w-full sm:w-72`} data-testid="gps-search" />
        <select value={f.section_id} onChange={(e) => set({ section_id: e.target.value, page: 0 })} aria-label="Участок" className={field} data-testid="gps-section">
          <option value="">Все участки</option>
          {sections.map((s) => { const n = sectionCount(s); return <option key={s.id} value={s.id}>{n === null ? s.name : `${s.name} (${n})`}</option> })}
        </select>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Период">
          {DATE_PRESETS.map((p) => <button key={p.id} type="button" aria-pressed={presetOn(p.id)} className={chipBtn(presetOn(p.id))} onClick={() => pickPreset(p.id)} data-testid={`gps-preset-${p.id}`}>{p.label}</button>)}
          <select value={f.date_from ? "" : String(f.days)} onChange={(e) => set({ days: Number(e.target.value), date_from: "", date_to: "", page: 0 })} aria-label="Период, дней" className={field}>
            {f.date_from && <option value="">{windowText(f)}</option>}
            {DAY_CHOICES.map((d) => <option key={d} value={d}>{d === 1 ? "сегодня" : `${d} дн.`}</option>)}
          </select>
        </div>
        <button type="button" className={chipBtn(f.only_issues)} aria-pressed={f.only_issues} onClick={() => set({ only_issues: !f.only_issues, page: 0 })} data-testid="gps-only-issues">Только проблемные</button>
        <button type="button" className={chipBtn(f.moving)} aria-pressed={f.moving} onClick={() => set({ moving: !f.moving, page: 0 })} data-testid="gps-moving">Едут сейчас</button>
        <button type="button" className={chipBtn(f.follow)} aria-pressed={f.follow} onClick={() => set({ follow: !f.follow, page: 0 })} data-testid="gps-follow-map" title="В таблице только то, что видно на карте TOIR">Список следует за картой</button>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400" data-testid="gps-count">Показано: <b>{shown}</b>{total !== shown ? ` из ${total}` : ""}</span>
          <SavedViewsMenu query={query} onApply={onApplyView} />
          <div className="inline-flex overflow-hidden rounded-full ring-1 ring-gray-200 dark:ring-gray-700" role="group" aria-label="Экспорт" data-testid="gps-export">
            <button type="button" disabled={exporting} onClick={() => onExport("csv")} className="bg-white px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50 dark:bg-gray-900 dark:hover:bg-gray-800" data-testid="gps-export-csv">{exporting ? "…" : "CSV"}</button>
            <button type="button" disabled={exporting} onClick={() => onExport("xlsx")} className="border-l border-gray-200 bg-white px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800" data-testid="gps-export-xlsx">XLSX</button>
          </div>
          <button type="button" className={chipBtn(advanced || advancedCount > 0)} aria-expanded={advanced} onClick={() => setAdvanced(!advanced)} data-testid="gps-advanced">Фильтры{advancedCount ? ` · ${advancedCount}` : ""}</button>
        </div>
      </div>

      {advanced && (
        <div className="space-y-3 border-t border-gray-100 pt-3 dark:border-gray-800" data-testid="gps-advanced-panel">
          <div className="grid gap-3 md:grid-cols-2">
            <ChipGroup label="Положение сейчас" testId="gps-f-verdict" value={f.verdict} counts={facets?.position_verdict} onToggle={multi("verdict")} options={POSITION_ORDER.map((v) => ({ value: v, label: POSITION_LABEL[v], hint: POSITION_HINT[v] }))} />
            <ChipGroup label="Пробег по дням (любой день окна)" testId="gps-f-dist" value={f.distance_verdict} counts={facets?.distance_verdict} onToggle={multi("distance_verdict")} options={DISTANCE_ORDER.map((v) => ({ value: v, label: DISTANCE_LABEL[v], hint: DISTANCE_HINT[v] }))} />
            <ChipGroup label="Причина расхождения" testId="gps-f-cause" value={f.cause} counts={facets?.cause} onToggle={multi("cause")} options={CAUSE_ORDER.filter((c) => c !== "ok").map((c) => ({ value: c, label: CAUSE_LABEL[c], hint: CAUSE_HINT[c] }))} />
            <ChipGroup label="Здоровье трекера GTK" testId="gps-f-health" value={f.health} counts={facets?.health} onToggle={multi("health")} options={HEALTH_ORDER.map((h) => ({ value: h, label: HEALTH_LABEL[h], hint: HEALTH_HINT[h] }))} />
            <ChipGroup label="Статус" testId="gps-f-severity" value={f.severity} counts={facets?.severity} onToggle={multi("severity")} options={SEVERITIES.map((s) => ({ value: s, label: SEVERITY_LABEL[s] }))} />
            <ChipGroup label="Какие трекеры привязаны" testId="gps-f-link" value={f.link ? [f.link] : []} counts={facets?.link} onToggle={(v) => set({ link: f.link === v ? "" : v, page: 0 })} options={LINKS.map((l) => ({ value: l, label: LINK_LABEL[l] }))} />
            {typeOptions.length > 0 && <ChipGroup label="Тип техники" testId="gps-f-type" value={f.asset_type} counts={facets?.asset_type} onToggle={multi("asset_type")} options={typeOptions} />}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-gray-600 dark:text-gray-300">Между точками, м, больше<input type="number" min={0} inputMode="numeric" value={f.min_diff_m} onChange={num("min_diff_m")} className={`${field} mt-1 block w-32`} data-testid="gps-min-diff" /></label>
            <label className="text-xs text-gray-600 dark:text-gray-300">Молчит дольше, ч<input type="number" min={0} inputMode="numeric" value={f.min_silence_h} onChange={num("min_silence_h")} className={`${field} mt-1 block w-32`} data-testid="gps-min-silence" /></label>
            <label className="text-xs text-gray-600 dark:text-gray-300">Км за период от<input type="number" min={0} inputMode="numeric" value={f.min_km} onChange={num("min_km")} className={`${field} mt-1 block w-28`} data-testid="gps-min-km" /></label>
            <label className="text-xs text-gray-600 dark:text-gray-300">до<input type="number" min={0} inputMode="numeric" value={f.max_km} onChange={num("max_km")} className={`${field} mt-1 block w-28`} data-testid="gps-max-km" /></label>
            <label className="text-xs text-gray-600 dark:text-gray-300">Даты с<input type="date" value={from} onChange={(e) => { setFrom(e.target.value); applyDates(e.target.value, to) }} className={`${field} mt-1 block`} data-testid="gps-date-from" /></label>
            <label className="text-xs text-gray-600 dark:text-gray-300">по<input type="date" value={to} onChange={(e) => { setTo(e.target.value); applyDates(from, e.target.value) }} className={`${field} mt-1 block`} data-testid="gps-date-to" /></label>
            {dateError && <span role="alert" className="pb-2 text-xs text-rose-600">{dateError}</span>}
          </div>
        </div>
      )}
      <FilterChips chips={chips} onRemove={(c) => set(c.patch)} onReset={onReset} />
    </section>
  )
}
