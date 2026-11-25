"use client"

import { useCallback, useEffect, useRef, useState, type ElementType, type ReactNode } from "react"
import { ApiHttpError } from "@/lib/api"
import { partsErrorHint } from "@/lib/parts-analytics"

export type Remote<T> = { data: T | null; loading: boolean; error: string | null; status?: number; reload: () => void }

/** Loads once `enabled` is true and again when `key` changes. Stale answers are dropped. */
export function useRemote<T>(key: string, fn: () => Promise<T>, enabled: boolean): Remote<T> {
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: string | null; status?: number }>({ data: null, loading: false, error: null })
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fnRef.current()
      .then((data) => { if (alive) setState({ data, loading: false, error: null }) })
      .catch((e: unknown) => {
        if (!alive) return
        const status = e instanceof ApiHttpError ? e.status : undefined
        setState({ data: null, loading: false, status, error: partsErrorHint(status, e instanceof Error ? e.message : undefined) })
      })
    return () => { alive = false }
  }, [key, enabled, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, reload }
}

export function Panel({ title, hint, icon: Icon, action, children }: {
  title: string
  hint?: string
  icon: ElementType
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="min-w-0 rounded-xl border border-violet-200/70 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-violet-900/60 dark:bg-gray-900/70">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="rounded-lg bg-violet-100 p-1.5 text-violet-600 dark:bg-violet-900/60 dark:text-violet-300"><Icon className="h-4 w-4" /></div>
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h4>
          {hint && <p className="text-[11px] text-gray-500 dark:text-gray-400">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

export function Conclusion({ children }: { children: ReactNode }) {
  return <p className="mt-3 rounded-lg bg-violet-50 px-3 py-2 text-xs leading-snug text-violet-900 dark:bg-violet-950/50 dark:text-violet-100">{children}</p>
}

/** Loading / error / empty wrapper for a card body. */
export function Body<T>({ remote, empty, children }: { remote: Remote<T>; empty?: (d: T) => boolean; children: (d: T) => ReactNode }) {
  if (remote.loading && !remote.data) {
    return <div className="space-y-2 animate-pulse">{[1, 2, 3].map((i) => <div key={i} className="h-10 rounded-lg bg-violet-100/70 dark:bg-violet-900/30" />)}</div>
  }
  if (remote.error) {
    return (
      <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        {remote.error}
        <button type="button" onClick={remote.reload} className="ml-2 font-semibold underline">Повторить</button>
      </div>
    )
  }
  if (!remote.data) return null
  if (empty?.(remote.data)) return <p className="py-6 text-center text-xs text-gray-400">Нет данных для отображения</p>
  return <div className={remote.loading ? "opacity-60 transition-opacity" : ""}>{children(remote.data)}</div>
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-violet-200 bg-white p-0.5 dark:border-violet-800 dark:bg-gray-900">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${o.value === value
            ? "bg-violet-600 text-white shadow"
            : "text-gray-600 hover:bg-violet-50 dark:text-gray-300 dark:hover:bg-violet-950"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Chip({ label, value, hot }: { label: string; value: string; hot?: boolean }) {
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[10px] ${hot
      ? "bg-red-50 font-semibold text-red-700 dark:bg-red-950/50 dark:text-red-300"
      : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"}`}>
      {label}: <b>{value}</b>
    </span>
  )
}

export const TH = "px-2 py-2 text-left text-[10px] font-semibold uppercase text-gray-500"
export const THR = "px-2 py-2 text-right text-[10px] font-semibold uppercase text-gray-500"
