"use client"

import Link from "next/link"
import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import { useDebouncedValue } from "@/lib/use-debounced-value"
import { useSections } from "@/lib/use-sections"
import {
  BASIS_LABEL, CONFIDENCE_COLOR, CONFIDENCE_HINT, CONFIDENCE_LABEL, CONFIDENCE_ORDER, DAY_CHOICES, DEFAULT_WAGON_FILTERS, FLAG_HINT, FLAG_LABEL, FLAG_ORDER, PAGE_SIZE,
  parseWagonFilters, patchActive, segKm, serializeWagonFilters, toggleValue, wagonApiParams, wagonFilterChips, type WagonFilters,
} from "@/lib/gps-analytics"
import { POSITION_LABEL, ageMinText, kmText, timeText, type GpsWagonPage, type GpsWagonRow, type PositionVerdict } from "@/lib/gps-view"
import { Empty, Panel } from "../../scales/_components/viz"
import { Loader2, RefreshCw } from "@/components/ui/icons"
import { GpsMap, type GpsMarker } from "../_components/GpsMap"
import { ConfidenceChip, FlagChip } from "../_components/parts"
import { Pager, SortHeader, ChipGroup, FilterChips, field, useAutoRefresh } from "../_components/ui"
import { useUrlState } from "../_components/useUrlState"
import { WagonBanner } from "../_components/WagonParts"

const TYPE_OPTIONS = [["", "Все типы"], ["wagon", "Вагон-самосвал"], ["tank_car", "Цистерна"], ["platform", "Платформа"]] as const
const wagonKey = (r: GpsWagonRow) => r.asset_id ?? `gtk-${r.carriage_gtk_id}`

type Tile = { id: string; label: string; value: React.ReactNode; hint?: string; testId: string; patch?: Partial<WagonFilters>; clear?: boolean; color?: string }

export default function WagonsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Загрузка…</div>}>
      <WagonsInner />
    </Suspense>
  )
}

function WagonsInner() {
  const { state: filters, set, reset } = useUrlState(parseWagonFilters, serializeWagonFilters)
  const { sectionsData } = useSections()
  const [qText, setQText] = useState(filters.q)
  const [trainText, setTrainText] = useState(filters.train)
  const [locoText, setLocoText] = useState(filters.loco)
  const dq = useDebouncedValue(qText, 350), dt = useDebouncedValue(trainText, 350), dl = useDebouncedValue(locoText, 350)
  const [data, setData] = useState<GpsWagonPage | null>(null)
  const [mapRows, setMapRows] = useState<GpsWagonRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)
  const offset = filters.page * PAGE_SIZE
  const query = serializeWagonFilters(filters)

  useEffect(() => { setQText(filters.q) }, [filters.q])
  useEffect(() => { setTrainText(filters.train) }, [filters.train])
  useEffect(() => { setLocoText(filters.loco) }, [filters.loco])
  useEffect(() => { if (qText === dq && qText !== filters.q) set({ q: qText, page: 0 }, { replace: true }) }, [qText, dq, filters.q, set])
  useEffect(() => { if (trainText === dt && trainText !== filters.train) set({ train: trainText, page: 0 }, { replace: true }) }, [trainText, dt, filters.train, set])
  useEffect(() => { if (locoText === dl && locoText !== filters.loco) set({ loco: locoText, page: 0 }, { replace: true }) }, [locoText, dl, filters.loco, set])

  const load = useCallback(async (silent: boolean, signal: AbortSignal) => {
    if (!silent) setLoading(true)
    try {
      const main = await api.gps.wagons(wagonApiParams(filters, { limit: PAGE_SIZE, offset }), signal)
      const wide = main.total > PAGE_SIZE || offset > 0 ? (await api.gps.wagons(wagonApiParams(filters, { limit: 500, offset: 0 }), signal)).items : main.items
      if (signal.aborted) return
      setData(main)
      setMapRows(wide)
      setLoadedAt(new Date())
      setError(null)
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить вагоны")
    } finally {
      if (!signal.aborted) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, offset])
  const { refresh } = useAutoRefresh(load, [query, offset], false)

  const sections = useMemo(() => sectionsData.map((s) => ({ id: s.id, name: s.name })), [sectionsData])
  const sectionName = useCallback((id: string) => sections.find((s) => s.id === id)?.name, [sections])
  const chips = useMemo(() => wagonFilterChips(filters, sectionName), [filters, sectionName])
  const rows = data?.items ?? []
  const s = data?.summary
  const cc = s?.confidence_counts ?? {}
  const fc = s?.flag_counts ?? {}

  const markers = useMemo<GpsMarker[]>(() => mapRows.flatMap((r) => {
    if (!r.position) return []
    const key = wagonKey(r)
    return [{
      id: key, lat: r.position.lat, lon: r.position.lon, color: CONFIDENCE_COLOR[r.confidence] ?? "#94a3b8", hollow: r.confidence === "low" || r.confidence === "none",
      label: `${r.inv_number ?? r.name} · состав ${r.train_number ?? "—"} · локомотив ${r.loco_inv_number ?? "—"} · уверенность: ${CONFIDENCE_LABEL[r.confidence]}`,
    }]
  }), [mapRows])

  const tiles: Tile[] = s ? [
    { id: "all", label: "Вагонов", value: s.wagons, hint: "в вашем охвате · сбросить фильтры", testId: "wagons-kpi-wagons", clear: true },
    { id: "in-train", label: "В составе", value: s.in_train, hint: "числятся в открытом составе GTK", testId: "wagons-kpi-in-train", patch: { in_train: "1" } },
    ...CONFIDENCE_ORDER.map((c): Tile => ({ id: `conf-${c}`, label: `Уверенность: ${CONFIDENCE_LABEL[c].toLowerCase()}`, value: cc[c] ?? 0, hint: CONFIDENCE_HINT[c], testId: `wagons-kpi-conf-${c}`, patch: { confidence: [c] }, color: CONFIDENCE_COLOR[c] })),
    ...FLAG_ORDER.map((f): Tile => ({ id: `flag-${f}`, label: FLAG_LABEL[f], value: fc[f] ?? 0, hint: FLAG_HINT[f], testId: `wagons-kpi-flag-${f}`, patch: { flag: [f] } })),
    { id: "km", label: `Км · ${data?.days} дн.`, value: kmText((s.km_period ?? 0) * 1000), hint: "выбранный пробег · сортировать", testId: "wagons-kpi-km", patch: { sort_by: "km_period", sort_dir: "desc" } },
  ] : []
  const tileActive = (t: Tile) => !!t.patch && patchActive(filters, t.patch)
  const pressTile = (t: Tile) => {
    if (t.clear) return reset({ ...DEFAULT_WAGON_FILTERS, days: filters.days })
    if (!t.patch) return
    if (tileActive(t)) {
      const undo = Object.fromEntries(Object.keys(t.patch).map((k) => [k, DEFAULT_WAGON_FILTERS[k as keyof WagonFilters]])) as Partial<WagonFilters>
      set({ ...undo, page: 0 })
    } else set({ ...t.patch, page: 0 })
  }
  const onSort = (key: string) => {
    if (filters.sort_by === key) set({ sort_dir: filters.sort_dir === "asc" ? "desc" : "asc", page: 0 })
    else set({ sort_by: key as WagonFilters["sort_by"], sort_dir: key === "inv_number" || key === "train_number" ? "asc" : "desc", page: 0 })
  }

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] min-w-0 space-y-4 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950" data-testid="wagons-page">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-teal-950 to-sky-900 p-5 text-white shadow-lg sm:p-6">
        <div className="relative flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold sm:text-3xl">Вагоны (по составу)</h1>
            <p className="mt-1 max-w-3xl text-sm text-sky-100/80">Где вагон и сколько он проехал: выводится из локомотива состава. Плитки нажимаются: это фильтры.{loadedAt ? ` · обновлено ${loadedAt.toLocaleTimeString("ru-RU")}` : ""}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/dashboard/gps" className="rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20">← Локомотивы</Link>
            <button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20"><RefreshCw className="h-4 w-4" /> Обновить</button>
          </div>
        </div>
        <div className="relative mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-6" data-testid="wagons-kpi">
          {tiles.map((t) => {
            const active = tileActive(t)
            return (
              <div
                key={t.id} data-testid={t.testId} data-active={active} role="button" tabIndex={0} aria-pressed={active} onClick={() => pressTile(t)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pressTile(t) } }}
                className={`min-w-0 cursor-pointer rounded-2xl p-3 ring-1 backdrop-blur transition hover:brightness-125 focus:outline-none focus-visible:ring-2 focus-visible:ring-white ${active ? "bg-white/20 ring-2 ring-white" : "bg-white/10 ring-white/10"}`}
              >
                <div className="flex items-center gap-1.5 truncate text-[11px] uppercase tracking-wide text-sky-100/70">{t.color && <i className="h-2 w-2 shrink-0 rounded-full" style={{ background: t.color }} />}<span className="truncate">{t.label}</span></div>
                <div className="mt-0.5 truncate text-2xl font-extrabold tabular-nums sm:text-3xl">{t.value}</div>
                {t.hint && <div className="mt-0.5 line-clamp-2 text-[11px] leading-tight text-sky-100/60">{t.hint}</div>}
              </div>
            )
          })}
          {!s && <div className="col-span-full flex items-center gap-2 py-6 text-sm text-sky-100/80"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>}
        </div>
      </section>

      <WagonBanner historyFrom={s?.history_from} />
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}

      <section className="space-y-3 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900" data-testid="gps-filter-bar" aria-label="Фильтры">
        <div className="flex flex-wrap items-center gap-2">
          <input type="search" value={qText} onChange={(e) => setQText(e.target.value)} placeholder="Инв. номер, название вагона" aria-label="Поиск" className={`${field} w-full sm:w-64`} data-testid="wagons-search" />
          <select value={filters.section_id} onChange={(e) => set({ section_id: e.target.value, page: 0 })} aria-label="Участок" className={field}>
            <option value="">Все участки</option>
            {sections.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
          <input type="search" value={trainText} onChange={(e) => setTrainText(e.target.value)} placeholder="Состав №" aria-label="Состав" className={`${field} w-28`} data-testid="wagons-train" />
          <input type="search" value={locoText} onChange={(e) => setLocoText(e.target.value)} placeholder="Локомотив" aria-label="Локомотив" className={`${field} w-32`} data-testid="wagons-loco" />
          <select value={filters.asset_type} onChange={(e) => set({ asset_type: e.target.value, page: 0 })} aria-label="Тип" className={field}>
            {TYPE_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={filters.in_train} onChange={(e) => set({ in_train: e.target.value as WagonFilters["in_train"], page: 0 })} aria-label="В составе" className={field} data-testid="wagons-in-train">
            <option value="">В составе: любые</option><option value="1">Только в составе</option><option value="0">Не в составе</option>
          </select>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">Период
            <select value={filters.days} onChange={(e) => set({ days: Number(e.target.value), page: 0 })} aria-label="Период, дней" className={field}>
              {DAY_CHOICES.map((d) => <option key={d} value={d}>{d === 1 ? "сутки" : `${d} дн.`}</option>)}
            </select>
          </label>
          <span className="ml-auto text-sm text-gray-500 dark:text-gray-400" data-testid="gps-count">Показано: <b>{rows.length}</b>{data && data.total !== rows.length ? ` из ${data.total}` : ""}</span>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <ChipGroup label="Уверенность" testId="wagons-f-confidence" value={filters.confidence} onToggle={(v) => set({ confidence: toggleValue(filters.confidence, v), page: 0 })} options={CONFIDENCE_ORDER.map((c) => ({ value: c, label: CONFIDENCE_LABEL[c], hint: CONFIDENCE_HINT[c] }))} counts={s ? cc : null} />
          <ChipGroup label="Признаки" testId="wagons-f-flag" value={filters.flag} onToggle={(v) => set({ flag: toggleValue(filters.flag, v), page: 0 })} options={FLAG_ORDER.map((f) => ({ value: f, label: FLAG_LABEL[f], hint: FLAG_HINT[f] }))} counts={s ? fc : null} />
        </div>
        <FilterChips chips={chips} onRemove={(c) => set(c.patch)} onReset={() => reset(DEFAULT_WAGON_FILTERS)} />
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr] [&>*]:min-w-0">
        <Panel title="Вагоны" hint="Строки сортируются на сервере. Инвентарный номер ведёт на карточку вагона: сегменты по составам и четыре варианта пробега.">
          {loading && !data ? <div className="flex items-center gap-2 p-6 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>
            : rows.length === 0 ? <Empty text={chips.length ? "По выбранным условиям вагонов нет" : "Нет вагонов в охвате"} /> : (
            <div className="-mx-1 overflow-x-auto">
              <table className="w-full min-w-[1020px] text-left text-sm" data-testid="wagons-table">
                <thead className="text-xs text-gray-500 dark:text-gray-400">
                  <tr>
                    <SortHeader field="inv_number" label="Вагон" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} testPrefix="wagons-sort" />
                    <SortHeader field="train_number" label="Состав" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} testPrefix="wagons-sort" />
                    <th className="px-2 py-2 text-xs uppercase tracking-wide">Локомотив</th>
                    <SortHeader field="since" label="В составе с" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} testPrefix="wagons-sort" />
                    <th className="px-2 py-2 text-xs uppercase tracking-wide">Позиция</th>
                    <SortHeader field="confidence" label="Уверенность" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} testPrefix="wagons-sort" />
                    <th className="px-2 py-2 text-xs uppercase tracking-wide">Признаки</th>
                    <SortHeader field="km_period" label="Км за период" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} align="right" testPrefix="wagons-sort" />
                    <th className="px-2 py-2 text-right text-xs uppercase tracking-wide">Сегментов</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {rows.map((r) => {
                    const key = wagonKey(r)
                    return (
                      <tr key={key} data-testid="wagon-row" data-confidence={r.confidence} onClick={() => setSelectedKey(selectedKey === key ? null : key)}
                        className={`cursor-pointer align-middle hover:bg-gray-50 dark:hover:bg-gray-800/60 ${key === selectedKey ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}`}>
                        <td className="px-2 py-2">
                          <Link href={`/dashboard/gps/wagons/${encodeURIComponent(key)}`} onClick={(e) => e.stopPropagation()} className="font-semibold text-blue-700 hover:underline dark:text-blue-400">{r.inv_number ?? r.name}</Link>
                          <div className="max-w-[200px] truncate text-xs text-gray-500 dark:text-gray-400">{[r.asset_type_name, r.section_name, r.asset_id ? null : "не привязан к ОС"].filter(Boolean).join(" · ")}</div>
                        </td>
                        <td className="px-2 py-2">{r.in_train ? <span className="tabular-nums">№ {r.train_number ?? r.train_gtk_id}</span> : <span className="text-xs text-gray-400">не в составе</span>}</td>
                        <td className="px-2 py-2 text-xs">{r.loco_asset_id ? <Link href={`/dashboard/gps/${r.loco_asset_id}`} onClick={(e) => e.stopPropagation()} className="text-blue-700 hover:underline dark:text-blue-400">{r.loco_inv_number ?? r.loco_name}</Link> : r.loco_inv_number ?? <span className="text-gray-400">—</span>}</td>
                        <td className="px-2 py-2 text-xs tabular-nums">{timeText(r.since)}</td>
                        <td className="px-2 py-2 text-xs">{r.position ? <span>{r.position_source === "gtk_gps" ? "GTK GPS" : "Wialon"} · {ageMinText(r.position.age_min)}{r.position_verdict ? <span className="block text-gray-500">{POSITION_LABEL[r.position_verdict as PositionVerdict] ?? r.position_verdict}</span> : null}</span> : <span className="text-gray-400">нет</span>}</td>
                        <td className="px-2 py-2"><ConfidenceChip level={r.confidence} /></td>
                        <td className="px-2 py-2"><div className="flex flex-wrap gap-1">{r.flags.length === 0 ? <span className="text-xs text-gray-400">—</span> : r.flags.map((f) => <FlagChip key={f} flag={f} />)}</div></td>
                        <td className="px-2 py-2 text-right font-semibold tabular-nums">{segKm(r.km_period)}</td>
                        <td className="px-2 py-2 text-right text-xs tabular-nums">{r.segments_n}{Object.keys(r.basis_counts).length ? <span className="block text-gray-500">{Object.entries(r.basis_counts).map(([b, n]) => `${BASIS_LABEL[b as keyof typeof BASIS_LABEL] ?? b}: ${n}`).join(", ")}</span> : null}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          <Pager total={data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={(page) => set({ page })} />
        </Panel>

        <section className="min-w-0 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2 px-1">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Карта: выведенные положения вагонов</h2>
            <span className="text-xs text-gray-500 dark:text-gray-400">{markers.length} вагонов · цвет = уверенность; пустой кружок — низкая или нет</span>
          </header>
          <div className="h-[56vh] min-h-[320px] min-w-0 overflow-hidden rounded-xl">
            {mapError ? <div className="flex h-full items-center justify-center p-4 text-center text-sm text-amber-800">{`Карта OpenStreetMap недоступна: ${mapError}`}</div> : (
              <GpsMap markers={markers} selectedId={selectedKey} onSelect={setSelectedKey} onError={setMapError} testId="wagons-map" ariaLabel="Положения вагонов (OpenStreetMap)" fitKey={`wagons-${markers.length > 0}`} />
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-600 dark:text-gray-300">
            {CONFIDENCE_ORDER.map((c) => <span key={c} className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full" style={{ background: CONFIDENCE_COLOR[c] }} />{CONFIDENCE_LABEL[c]}</span>)}
          </div>
        </section>
      </div>
    </div>
  )
}
