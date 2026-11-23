"use client"

import { useEffect, useState } from "react"
import { api, type AvgDailyMileageDetail, type AvgDailyMileageRow } from "@/lib/api"

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 })
const REASON: Record<string, string> = {
  no_mileage: "Недостаточно данных: нет пробега у активной техники",
  no_gps_data: "Недостаточно данных GPS за последние 7 дней",
}

export function AvgDailyMileage() {
  const [rows, setRows] = useState<AvgDailyMileageRow[] | null>(null)
  const [error, setError] = useState(false)
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState<AvgDailyMileageRow | null>(null)

  useEffect(() => {
    let alive = true
    api.maintenanceLive.avgDailyMileage()
      .then((r) => { if (alive) setRows(r) })
      .catch(() => { if (alive) setError(true) })
    return () => { alive = false }
  }, [])

  const sections = Array.from(new Set((rows ?? []).map((r) => r.section_name ?? "—")))
  const ready = (rows ?? []).filter((r) => r.avg_daily_km !== null).length

  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900" data-testid="avg-daily-mileage">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center justify-between gap-3 text-left">
        <span>
          <span className="block text-base font-semibold text-gray-900 dark:text-white">Средний суточный пробег</span>
          <span className="block text-xs text-gray-500 dark:text-gray-400">
            По участкам и типам техники, по данным GPS за 7 дней{rows ? ` · рассчитано ${ready} из ${rows.length}` : ""}
          </span>
        </span>
        <span aria-hidden="true" className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="mt-3 space-y-4">
          {error && <p className="text-sm text-red-600">Не удалось загрузить данные</p>}
          {!rows && !error && <p className="text-sm text-gray-500">Загрузка…</p>}
          {rows && rows.length === 0 && <p className="text-sm text-gray-500">Нет активной техники с участком</p>}
          {sections.map((section) => (
            <div key={section}>
              <h3 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-200">{section}</h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {(rows ?? []).filter((r) => (r.section_name ?? "—") === section).map((r) => (
                  <button type="button" key={r.section_id + r.asset_type} onClick={() => setPicked(r)} title="Нажмите, чтобы увидеть расчёт"
                    className="rounded-xl border border-gray-200 p-3 text-left transition-colors hover:border-blue-300 dark:border-gray-800" data-testid="avg-daily-card">
                    <div className="text-xs font-medium text-gray-500 dark:text-gray-400">{r.asset_type_name}</div>
                    {r.avg_daily_km !== null ? (
                      <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                        {nf.format(Number(r.avg_daily_km))} <span className="text-sm font-medium text-gray-500">км/сутки</span>
                      </div>
                    ) : (
                      <div className="mt-1 text-sm font-medium text-amber-700 dark:text-amber-400">{REASON[r.reason ?? "no_gps_data"]}</div>
                    )}
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      Активных: {r.active_count} · макс. пробег: {r.max_mileage !== null ? nf.format(Number(r.max_mileage)) : "—"}
                      <br />Большой список: {r.big_count} · малый: {r.small_count} · с данными GPS: {r.with_data_count}
                    </div>
                    <div className="mt-2 text-xs font-medium text-blue-600">Как рассчитано →</div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {picked && <DetailDialog row={picked} onClose={() => setPicked(null)} />}
    </section>
  )
}

function DetailDialog({ row, onClose }: { row: AvgDailyMileageRow; onClose: () => void }) {
  const [d, setD] = useState<AvgDailyMileageDetail | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let alive = true
    api.maintenanceLive.avgDailyMileageDetail(row.section_id, row.asset_type)
      .then((r) => { if (alive) setD(r) })
      .catch(() => { if (alive) setError(true) })
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => { alive = false; window.removeEventListener("keydown", onKey) }
  }, [row, onClose])
  const n = (v: string | null) => (v === null ? "—" : nf.format(Number(v)))
  const small = (d?.units ?? []).filter((u) => u.in_small)
  const wagon = ["wagon", "tank_car", "platform"].includes(row.asset_type)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose} role="dialog" aria-modal="true" data-testid="avg-daily-detail">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl dark:bg-gray-900" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{row.section_name} · {row.asset_type_name}</h2>
            <p className="text-xs text-gray-500">Расчёт среднего суточного пробега</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg px-2 py-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" aria-label="Закрыть">✕</button>
        </div>
        {error && <p className="mt-3 text-sm text-red-600">Не удалось загрузить расчёт</p>}
        {!d && !error && <p className="mt-3 text-sm text-gray-500">Загрузка…</p>}
        {d && (
          <div className="mt-4 space-y-4 text-sm text-gray-700 dark:text-gray-200">
            <ol className="space-y-2">
              <li><b>1. Активная техника</b> этого участка и типа: {d.active_count} ед. Другие участки и типы не учитываются.</li>
              <li><b>2. Максимальный пробег:</b> {n(d.max_mileage)} км.</li>
              <li><b>3. Большой список</b> (10–100% от максимума): от {n(d.big_low)} до {n(d.max_mileage)} км → <b>{d.big_count}</b> ед.</li>
              <li><b>4. Малый список</b> (80–100% от максимума): от {n(d.small_low)} до {n(d.max_mileage)} км → <b>{d.small_count}</b> ед.</li>
              <li><b>5. Суточный пробег</b> каждой единицы малого списка за последние {d.window_days} дней: {wagon
                ? "сумма км из журнала пробега вагонов за 7 дней ÷ 7."
                : "(показание счётчика на последний день − на первый день) ÷ число дней между ними."} Единицы без данных пропускаются, а не считаются нулём.</li>
              <li><b>6. Результат</b> = среднее арифметическое по единицам с данными ({d.with_data_count} из {d.small_count}):{" "}
                {d.avg_daily_km !== null ? <b>{n(d.avg_daily_km)} км/сутки</b> : <b className="text-amber-700">недостаточно данных GPS — значение не выводится</b>}</li>
            </ol>
            <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
              <table className="w-full text-left text-xs">
                <thead><tr className="text-gray-500">
                  <th className="p-2">Инв. №</th><th className="p-2">Название</th><th className="p-2 text-right">Пробег, км</th>
                  <th className="p-2 text-right">% от макс.</th><th className="p-2">Список</th><th className="p-2">Расчёт за 7 дней</th><th className="p-2 text-right">км/сутки</th>
                </tr></thead>
                <tbody>
                  {d.units.map((u) => (
                    <tr key={u.asset_id} className={u.in_small ? "bg-blue-50/60 dark:bg-blue-950/30" : ""}>
                      <td className="p-2 font-medium">{u.inv_number ?? "—"}</td>
                      <td className="p-2">{u.name ?? "—"}</td>
                      <td className="p-2 text-right">{n(u.mileage)}</td>
                      <td className="p-2 text-right">{n(u.percent_of_max)}%</td>
                      <td className="p-2">{u.in_small ? "малый" : "большой"}</td>
                      <td className="p-2">
                        {!u.in_small ? "—" : u.source === "meter"
                          ? `${n(u.last_km)} (${u.last_day}) − ${n(u.first_km)} (${u.first_day}), показаний: ${u.readings}`
                          : u.source === "ledger" ? `${n(u.total_km)} км ÷ ${d.window_days} (записей: ${u.readings})` : "нет данных GPS"}
                      </td>
                      <td className="p-2 text-right font-semibold">{u.in_small ? n(u.daily_km) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500">Синим выделены единицы малого списка ({small.length}). Берётся только активная техника (статус «в эксплуатации»).</p>
          </div>
        )}
      </div>
    </div>
  )
}
