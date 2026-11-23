"use client"

import { useEffect, useState, type ReactNode } from "react"

/** Compact collapsible panel; the open/closed choice is remembered in this browser. */
export function Fold({ id, title, hint, badge, defaultOpen = false, children }: {
  id: string; title: string; hint?: string; badge?: string | number | null; defaultOpen?: boolean; children: ReactNode
}) {
  const key = `toir.fold.${id}`
  const [open, setOpen] = useState(defaultOpen)
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(key)
      if (saved === "1") setOpen(true)
      else if (saved === "0") setOpen(false)
    } catch { /* storage unavailable: keep the default */ }
  }, [key])
  const toggle = () => {
    const next = !open
    setOpen(next)
    try { window.localStorage.setItem(key, next ? "1" : "0") } catch { /* ignore */ }
  }
  return (
    <section className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900" data-testid={`fold-${id}`}>
      <button type="button" onClick={toggle} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-2.5 text-left">
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{title}</span>
        {badge !== null && badge !== undefined && badge !== "" && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">{badge}</span>
        )}
        {hint && <span className="hidden truncate text-xs text-gray-400 sm:block">{hint}</span>}
        <span aria-hidden="true" className={`ml-auto text-xs text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}>▼</span>
      </button>
      {open && <div className="space-y-4 border-t border-gray-100 p-4 dark:border-gray-800">{children}</div>}
    </section>
  )
}
