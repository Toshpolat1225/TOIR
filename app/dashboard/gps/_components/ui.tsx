"use client"

// Small shared pieces of the GPS pages: chip groups with facet counts, removable filter chips, pager, saved views, auto-refresh, file download.
import { useCallback, useEffect, useRef, useState } from "react"
import { addSavedView, parseSavedViews, type FilterChip, type SavedView } from "@/lib/gps-analytics"

export const field = "rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
export const chipBtn = (on: boolean) =>
  `rounded-full px-3 py-1 text-sm ring-1 transition ${on ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-gray-800 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-800"}`
export const smallChipBtn = (on: boolean, dim = false) =>
  `inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs ring-1 transition ${on ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-gray-800 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-700"} ${dim && !on ? "opacity-45" : ""}`

/** A multi-select group of chips (a single choice is a one-element value); `counts` are the facet counts under the other active filters. */
export function ChipGroup({
  label, options, value, onToggle, counts, testId,
}: {
  label: string
  options: { value: string; label: string; hint?: string }[]
  value: string[]
  onToggle: (v: string) => void
  counts?: Record<string, number> | null
  testId?: string
}) {
  return (
    <fieldset className="min-w-0" data-testid={testId}>
      <legend className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</legend>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={label}>
        {options.map((o) => {
          const on = value.includes(o.value)
          const n = counts ? counts[o.value] ?? 0 : null
          return (
            <button
              key={o.value} type="button" aria-pressed={on} title={o.hint} data-testid={testId ? `${testId}-${o.value}` : undefined}
              className={smallChipBtn(on, n === 0)} onClick={() => onToggle(o.value)}
            >
              {o.label}{n !== null && <span className={`tabular-nums ${on ? "text-white/80" : "text-gray-500 dark:text-gray-400"}`}>{n}</span>}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}

/** The row of removable chips for the active filters plus «Сбросить». */
export function FilterChips<F>({ chips, onRemove, onReset }: { chips: FilterChip<F>[]; onRemove: (c: FilterChip<F>) => void; onReset: () => void }) {
  if (chips.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="gps-filter-chips" aria-label="Активные фильтры">
      {chips.map((c) => (
        <button
          key={c.id} type="button" data-testid="gps-filter-chip" onClick={() => onRemove(c)} title="Убрать фильтр"
          className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-800 ring-1 ring-indigo-200 hover:bg-indigo-100 dark:bg-indigo-950/50 dark:text-indigo-200 dark:ring-indigo-900"
        >
          {c.label}<span aria-hidden className="text-indigo-500">×</span>
        </button>
      ))}
      <button type="button" onClick={onReset} data-testid="gps-filter-reset" className="rounded-full px-2.5 py-1 text-xs font-medium text-gray-600 underline hover:text-gray-900 dark:text-gray-300">Сбросить</button>
    </div>
  )
}

export function Pager({ total, limit, offset, onPage }: { total: number; limit: number; offset: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / limit))
  const page = Math.min(pages - 1, Math.floor(offset / limit))
  if (total <= limit) return null
  const btn = "rounded-lg px-3 py-1.5 text-sm ring-1 ring-gray-200 hover:bg-gray-50 disabled:opacity-40 dark:ring-gray-700 dark:hover:bg-gray-800"
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2" data-testid="gps-pager">
      <span className="text-xs text-gray-500 dark:text-gray-400">{`${offset + 1}–${Math.min(total, offset + limit)} из ${total}`}</span>
      <div className="flex items-center gap-2">
        <button type="button" className={btn} disabled={page <= 0} onClick={() => onPage(page - 1)} data-testid="gps-pager-prev">← Назад</button>
        <span className="text-sm tabular-nums text-gray-700 dark:text-gray-200">{`${page + 1} / ${pages}`}</span>
        <button type="button" className={btn} disabled={page >= pages - 1} onClick={() => onPage(page + 1)} data-testid="gps-pager-next">Дальше →</button>
      </div>
    </div>
  )
}

/** A sortable column header: the state lives in the URL; the server sorts. */
export function SortHeader({
  field: key, label, sortBy, sortDir, onSort, align = "left", testPrefix = "gps-sort",
}: {
  field: string; label: string; sortBy: string; sortDir: "asc" | "desc"; onSort: (field: string) => void; align?: "left" | "right"; testPrefix?: string
}) {
  const on = sortBy === key
  return (
    <th className={`px-2 py-2 ${align === "right" ? "text-right" : ""}`} aria-sort={on ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(key)} data-testid={`${testPrefix}-${key}`} className={`inline-flex items-center gap-1 uppercase tracking-wide hover:text-gray-900 dark:hover:text-white ${on ? "text-indigo-700 dark:text-indigo-300" : ""}`}>
        {label}<span aria-hidden className="text-[10px]">{on ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
      </button>
    </th>
  )
}

const VIEWS_KEY = "toir.gps.views"
/** Saved filter views kept in this browser only (every access is guarded: storage may be blocked). */
export function useSavedViews(storageKey: string = VIEWS_KEY) {
  const [views, setViews] = useState<SavedView[]>([])
  useEffect(() => {
    try { setViews(parseSavedViews(window.localStorage.getItem(storageKey))) } catch { setViews([]) }
  }, [storageKey])
  const persist = useCallback((next: SavedView[]) => {
    setViews(next)
    try { window.localStorage.setItem(storageKey, JSON.stringify(next)) } catch { /* private window / blocked storage: the list lives for this page only */ }
  }, [storageKey])
  const save = useCallback((name: string, query: string) => persist(addSavedView(views, name, query)), [persist, views])
  const remove = useCallback((name: string) => persist(views.filter((v) => v.name !== name)), [persist, views])
  return { views, save, remove }
}

export function SavedViewsMenu({ query, onApply, storageKey }: { query: string; onApply: (query: string) => void; storageKey?: string }) {
  const { views, save, remove } = useSavedViews(storageKey)
  const [name, setName] = useState("")
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} data-testid="gps-views" className={chipBtn(open)}>Виды{views.length ? ` (${views.length})` : ""}</button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-72 max-w-[85vw] rounded-xl border border-gray-200 bg-white p-3 shadow-xl dark:border-gray-700 dark:bg-gray-900">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) { save(name, query); setName("") } }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название вида" aria-label="Название вида" className={`${field} min-w-0 flex-1 py-1.5`} />
            <button type="submit" data-testid="gps-view-save" className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700">Сохранить</button>
          </form>
          <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto text-sm">
            {views.length === 0 && <li className="text-xs text-gray-500">Сохранённых видов пока нет. Текущие фильтры и сортировка сохранятся в этом браузере.</li>}
            {views.map((v) => (
              <li key={v.name} className="flex items-center justify-between gap-2">
                <button type="button" className="min-w-0 flex-1 truncate rounded px-2 py-1 text-left hover:bg-gray-100 dark:hover:bg-gray-800" onClick={() => { onApply(v.query); setOpen(false) }} data-testid="gps-view-apply">{v.name}</button>
                <button type="button" aria-label={`Удалить вид ${v.name}`} className="rounded px-2 py-1 text-gray-400 hover:text-rose-600" onClick={() => remove(v.name)}>✕</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Run `load` now and every `ms` (not while paused or the tab is hidden); the previous request is aborted when a newer one starts. */
export function useAutoRefresh(load: (silent: boolean, signal: AbortSignal) => Promise<void>, deps: unknown[], paused: boolean, ms = 60_000) {
  const controller = useRef<AbortController | null>(null)
  const loadRef = useRef(load)
  loadRef.current = load
  const run = useCallback(async (silent: boolean) => {
    controller.current?.abort()
    const next = new AbortController()
    controller.current = next
    try { await loadRef.current(silent, next.signal) } catch (error) { if (!(error instanceof DOMException && error.name === "AbortError")) throw error }
  }, [])
  useEffect(() => {
    void run(false)
    return () => controller.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => {
    if (paused) return
    const timer = window.setInterval(() => { if (document.visibilityState !== "hidden") void run(true) }, ms)
    return () => window.clearInterval(timer)
  }, [paused, ms, run])
  return { refresh: () => run(false) }
}

/** Save a Blob as a file through a temporary link. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
