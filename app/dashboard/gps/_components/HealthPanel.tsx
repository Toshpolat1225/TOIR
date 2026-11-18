"use client"

import { HEALTH_HINT, HEALTH_LABEL, HEALTH_ORDER, healthColor, okShareText } from "@/lib/gps-analytics"
import { ageMinText, kmText, type GpsHealthPage } from "@/lib/gps-view"
import { Loader2 } from "@/components/ui/icons"
import { HealthChip } from "./parts"

/** «Рейтинг трекеров GTK»: the worst trackers first. A class chip filters the table, a row opens the unit's drawer. */
export function HealthPanel({
  page, activeClasses, onPickClass, onOpenUnit, loading, selectedId,
}: {
  page: GpsHealthPage | null
  activeClasses: string[]
  onPickClass: (health: string) => void
  onOpenUnit: (assetId: string) => void
  loading: boolean
  selectedId?: string | null
}) {
  return (
    <section className="min-w-0 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900" data-testid="gps-health-panel">
      <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Рейтинг трекеров GTK</h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">Какие трекеры GTK теряют данные: худшие сверху. Это список для проверки на технике и для администратора GTK.</p>
      {!page ? <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div> : (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Классы трекеров">
            {HEALTH_ORDER.filter((h) => (page.counts[h] ?? 0) > 0).map((h) => {
              const on = activeClasses.includes(h)
              return (
                <button
                  key={h} type="button" aria-pressed={on} title={HEALTH_HINT[h]} onClick={() => onPickClass(h)} data-testid={`gps-health-class-${h}`}
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ring-1 transition ${on ? "bg-gray-900 text-white ring-gray-900 dark:bg-white dark:text-gray-900" : "bg-white text-gray-800 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-700"}`}
                >
                  <i className="h-2 w-2 rounded-full" style={{ background: healthColor(h) }} />{HEALTH_LABEL[h]}<b className="tabular-nums">{page.counts[h]}</b>
                </button>
              )
            })}
          </div>
          {page.items.length === 0 ? <p className="text-sm text-gray-500">Нет данных по трекерам за период.</p> : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-800">
              {page.items.map((r) => {
                const share = r.health.ok_share ?? (r.health.active_days > 0 ? r.health.ok_days / r.health.active_days : 0)
                return (
                  <li key={r.asset_id}>
                    <button
                      type="button" onClick={() => onOpenUnit(r.asset_id)} data-testid="gps-health-row" data-health={r.health.health_class}
                      className={`flex w-full min-w-0 items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-800/60 ${selectedId === r.asset_id ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2"><b className="text-sm text-gray-900 dark:text-white">{r.inv_number}</b><HealthChip health={r.health.health_class} />{r.anomaly && <span className="text-[11px] text-rose-600">{r.anomaly === "frozen" ? "координата застыла" : r.anomaly === "silent" ? "молчит" : r.anomaly}</span>}</div>
                        <div className="truncate text-xs text-gray-500 dark:text-gray-400">{r.name}{r.section_name ? ` · ${r.section_name}` : ""} · {okShareText(r.health)}</div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800" aria-hidden><div className="h-full rounded-full" style={{ width: `${Math.round(share * 100)}%`, background: healthColor(r.health.health_class) }} /></div>
                      </div>
                      <div className="shrink-0 text-right text-xs">
                        <div className="font-semibold tabular-nums text-gray-900 dark:text-white">{r.health.km_lost_m > 0 ? `−${kmText(r.health.km_lost_m)}` : "0 км"}</div>
                        <div className="text-gray-500">{r.health.last_gtk_fix_age_h != null ? ageMinText(r.health.last_gtk_fix_age_h * 60) : "—"}</div>
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
          {loading && <p className="mt-2 text-xs text-gray-400">Обновляю…</p>}
        </>
      )}
    </section>
  )
}
