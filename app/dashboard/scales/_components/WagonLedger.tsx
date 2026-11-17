"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { api, type WagonLedgerParams } from "@/lib/api"
import {
  BASIS_LABEL, dateTimeText, isLinked, ownShareText, tonnesText, tripTonnes, wagonLabel,
  type WagonTotalPage, type WagonTripPage,
} from "@/lib/scales-view"
import { locoHref, trainHref, wagonHref } from "@/lib/scales-insights"
import { Loader2 } from "@/components/ui/icons"

const PAGE_SIZE = 50
const field = "rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
const button = "rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"

const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const daysAgo = (n: number) => isoDay(new Date(Date.now() - n * 86_400_000))

type Mode = "totals" | "trips"

export default function WagonLedger({ posts }: { posts: { code: string; name: string }[] }) {
  const [mode, setMode] = useState<Mode>("totals")
  const [q, setQ] = useState("")
  const [debouncedQ, setDebouncedQ] = useState("")
  const [dateFrom, setDateFrom] = useState(daysAgo(30))
  const [dateTo, setDateTo] = useState(isoDay(new Date()))
  const [post, setPost] = useState("")
  const [onlyLinked, setOnlyLinked] = useState(false)
  const [asset, setAsset] = useState<{ id: string; label: string } | null>(null)
  const [offset, setOffset] = useState(0)
  const [totals, setTotals] = useState<WagonTotalPage | null>(null)
  const [trips, setTrips] = useState<WagonTripPage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQ(q.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [q])
  useEffect(() => setOffset(0), [mode, debouncedQ, dateFrom, dateTo, post, onlyLinked, asset])

  const filters = useMemo<WagonLedgerParams>(
    () => ({ q: debouncedQ, date_from: dateFrom, date_to: dateTo, post, only_linked: onlyLinked, asset_id: asset?.id }),
    [debouncedQ, dateFrom, dateTo, post, onlyLinked, asset],
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const run = async () => {
      try {
        if (mode === "totals") {
          const page = await api.scales.wagonTotals({ ...filters, asset_id: undefined, sort_by: "tonnes", limit: PAGE_SIZE, offset })
          if (!cancelled) setTotals(page)
        } else {
          const page = await api.scales.wagonTrips({ ...filters, sort_by: "started_at", limit: PAGE_SIZE, offset })
          if (!cancelled) setTrips(page)
        }
        if (!cancelled) setError(null)
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить данные")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => { cancelled = true }
  }, [mode, filters, offset])

  const open = (row: { asset_id: string | null; inv_number: string | null; gtk_inventory_number: string | null; gtk_name: string | null; carriage_gtk_id: number }) => {
    const label = wagonLabel(row)
    if (row.asset_id) setAsset({ id: row.asset_id, label })
    else { setAsset(null); setQ(label) }
    setMode("trips")
  }

  const exportCsv = async () => {
    try {
      const blob = await api.scales.exportWagonTrips(filters)
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = "wagon_trips.csv"
      link.click()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось выгрузить файл")
    }
  }

  const page = mode === "totals" ? totals : trips
  const total = page?.total ?? 0
  const summary = mode === "totals"
    ? totals ? `Вагонов: ${totals.total} · рейсов: ${totals.trips_total} · тонн: ${tonnesText(totals.tonnes_total)}` : ""
    : trips ? `Рейсов: ${trips.total} · вагонов: ${trips.wagons_total} · тонн: ${tonnesText(trips.tonnes_total)}` : ""

  return (
    <section className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Какой вагон, когда и сколько тонн перевёз: за выбранный период. «≈» значит доля состава или оценка, а не взвешивание самого вагона.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-lg ring-1 ring-gray-300 dark:ring-gray-700" role="group" aria-label="Режим">
          {(["totals", "trips"] as Mode[]).map((m) => (
            <button
              key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}
              className={`px-3 py-1.5 text-sm ${mode === m ? "bg-blue-600 text-white" : "bg-white text-gray-800 dark:bg-gray-900 dark:text-gray-100"}`}
            >
              {m === "totals" ? "Итоги по вагонам" : "Все рейсы"}
            </button>
          ))}
        </div>
        <input aria-label="Вагон" type="search" placeholder="Вагон: инв. № или название GTK" className={`${field} w-64`} value={q} onChange={(e) => { setQ(e.target.value); setAsset(null) }} />
        <label className="flex items-center gap-1 text-sm">с <input aria-label="С даты" type="date" className={field} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
        <label className="flex items-center gap-1 text-sm">по <input aria-label="По дату" type="date" className={field} value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
        <select aria-label="Весы" className={field} value={post} onChange={(e) => setPost(e.target.value)}>
          <option value="">Все весы</option>
          {posts.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyLinked} onChange={(e) => setOnlyLinked(e.target.checked)} /> только связанные с ОС</label>
        <button type="button" className={button} onClick={() => void exportCsv()}>Выгрузить в Excel (CSV)</button>
        {loading && <Loader2 className="h-4 w-4 animate-spin text-gray-500" />}
      </div>
      {asset && (
        <p className="text-sm">
          Вагон <b>{asset.label}</b>{" "}
          <button type="button" className="text-blue-600 hover:underline dark:text-blue-400" onClick={() => setAsset(null)}>показать все вагоны</button>
        </p>
      )}
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}
      <p className="text-sm text-gray-500 dark:text-gray-400" data-testid="ledger-summary">{summary}</p>

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        {mode === "totals" ? (
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
              <tr>{["Вагон", "Рейсов", "Тонн", "В среднем за рейс", "Последний рейс", "Точность"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {(totals?.items ?? []).map((w) => (
                <tr key={`${w.carriage_gtk_id}-${w.asset_id ?? ""}`} data-testid="wagon-total" className="cursor-pointer border-t border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800" onClick={() => open(w)}>
                  <td className="px-3 py-2 font-medium"><Link className="text-blue-600 hover:underline dark:text-blue-400" href={wagonHref(w)} onClick={(e) => e.stopPropagation()} title="Открыть карточку вагона">{wagonLabel(w)}</Link>{!isLinked(w) && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">нет связи с ОС</span>}</td>
                  <td className="px-3 py-2">{w.trips}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{tonnesText(w.tonnes)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{tonnesText(w.avg_tonnes)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{dateTimeText(w.last_at)}</td>
                  <td className="px-3 py-2 text-xs text-gray-600 dark:text-gray-400">{ownShareText(w)}</td>
                </tr>
              ))}
              {totals && totals.items.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-500">Нет рейсов по выбранным условиям.</td></tr>}
            </tbody>
          </table>
        ) : (
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
              <tr>{["Когда", "Вагон", "Тонн", "Основание", "Локомотив", "Груз", "Экскаватор", "Весы"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {(trips?.items ?? []).map((t) => (
                <tr key={`${t.train_id}-${t.carriage_gtk_id}`} data-testid="wagon-trip" className="border-t border-gray-100 dark:border-gray-800">
                  <td className="px-3 py-2 whitespace-nowrap"><Link className="text-blue-600 hover:underline dark:text-blue-400" href={trainHref(t.train_id)} title="Открыть состав">{dateTimeText(t.started_at)}</Link></td>
                  <td className="px-3 py-2 font-medium"><Link className="hover:underline" href={wagonHref(t)}>{wagonLabel(t)}</Link>{t.position ? <span className="ml-1 text-xs font-normal text-gray-500">поз. {t.position}</span> : null}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{tripTonnes(t)}</td>
                  <td className="px-3 py-2 text-xs text-gray-600 dark:text-gray-400">{BASIS_LABEL[t.basis]}</td>
                  <td className="px-3 py-2">{t.loco_asset_id ? <Link className="text-blue-600 hover:underline dark:text-blue-400" href={locoHref(t.loco_asset_id)}>{t.loco_number ?? t.loco_inv_number}</Link> : (t.loco_number ?? "—")}{t.loco_inv_number ? <span className="block text-xs text-gray-500">ОС {t.loco_inv_number}</span> : null}</td>
                  <td className="px-3 py-2">{t.cargo_name ?? "—"}</td>
                  <td className="px-3 py-2">{t.excavator ?? "—"}</td>
                  <td className="px-3 py-2">{t.post_code}</td>
                </tr>
              ))}
              {trips && trips.items.length === 0 && <tr><td colSpan={8} className="px-3 py-6 text-center text-gray-500">Нет рейсов по выбранным условиям.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
      {total > PAGE_SIZE && (
        <div className="flex items-center gap-2">
          <button className={button} type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Назад</button>
          <button className={button} type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Дальше</button>
          <span className="text-sm text-gray-500">{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} из {total}</span>
        </div>
      )}
    </section>
  )
}
