"use client"
import { fmtPercent } from "@/lib/format"

import Link from "next/link"
import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import type { MapPoint } from "@/lib/map-view"
import { useDebouncedValue } from "@/lib/use-debounced-value"
import { useSections } from "@/lib/use-sections"
import {
  CAUSE_HINT, CAUSE_LABEL, CAUSE_ORDER, DEFAULT_FILTERS, GTK_LOSS_CAUSES, PAGE_SIZE, bboxText, causeColor, confidenceText, confidenceTone, fusedText, gpsApiParams, gpsFilterChips,
  isDefaultFilters, parseGpsFilters, patchActive, serializeGpsFilters, sumGap, toggleValue, type GpsFilters,
} from "@/lib/gps-analytics"
import {
  BASE_TOLERANCE_M, DISTANCE_HINT, DISTANCE_LABEL, DISTANCE_ORDER, FRESH_MIN, IDLE_M, MATCH_RANGE, MINOR_RANGE, POSITION_HINT, POSITION_LABEL, POSITION_ORDER, SAME_SPOT_M,
  ageMinText, distText, distanceColor, isStale, kmText, positionColor, runStatusText, runStatusTone, speedText, timeText,
  type GpsAssetRow, type GpsFeedHealth, type GpsHealthPage, type GpsOverview, type PositionVerdict,
} from "@/lib/gps-view"
import { Empty, Panel } from "../scales/_components/viz"
import { Loader2, RefreshCw } from "@/components/ui/icons"
import { GpsDrawer } from "./_components/GpsDrawer"
import { GpsMap, type GpsLine, type GpsMarker } from "./_components/GpsMap"
import { HealthPanel } from "./_components/HealthPanel"
import { OverviewFilters } from "./_components/OverviewFilters"
import { CauseChip, Chip, GTK_COLOR, MiniPair, PositionChip, SourceLegend, StackBar, WIALON_COLOR } from "./_components/parts"
import { Pager, SortHeader, downloadBlob, useAutoRefresh } from "./_components/ui"
import { useUrlState } from "./_components/useUrlState"

type Tile = {
  id: string; label: string; value: React.ReactNode; hint?: string; tone?: "warn" | "bad" | "good"; testId: string
  patch?: Partial<GpsFilters>; clear?: boolean; custom?: React.ReactNode
}

export default function GpsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Загрузка…</div>}>
      <GpsPageInner />
    </Suspense>
  )
}

function GpsPageInner() {
  const { state: filters, set, reset, query } = useUrlState(parseGpsFilters, serializeGpsFilters)
  const { sectionsData } = useSections()
  const [qText, setQText] = useState(filters.q)
  const debouncedQ = useDebouncedValue(qText, 350)
  const [data, setData] = useState<GpsOverview | null>(null)
  const [mapRows, setMapRows] = useState<GpsAssetRow[]>([])
  const [points, setPoints] = useState<MapPoint[]>([])
  const [health, setHealth] = useState<GpsHealthPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [cursorId, setCursorId] = useState<string | null>(null)
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)
  const [paused, setPaused] = useState(false)
  const [rawBbox, setRawBbox] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const bbox = useDebouncedValue(rawBbox, 600)
  const bboxParam = filters.follow ? bbox : null
  const offset = filters.page * PAGE_SIZE

  // the search box <-> the URL: typed text is committed once it settles; an external change (a removed chip) wins immediately
  useEffect(() => { setQText(filters.q) }, [filters.q])
  useEffect(() => {
    if (qText === debouncedQ && qText !== filters.q) set({ q: qText, page: 0 }, { replace: true })
  }, [qText, debouncedQ, filters.q, set])

  const load = useCallback(async (silent: boolean, signal: AbortSignal) => {
    if (!silent) setLoading(true)
    try {
      const main = await api.gps.overview(gpsApiParams(filters, { limit: PAGE_SIZE, offset, facets: true, bbox: bboxParam }), signal)
      const needMap = filters.follow || main.total > PAGE_SIZE || offset > 0
      const [wide, unified, ranking] = await Promise.all([
        needMap ? api.gps.overview(gpsApiParams(filters, { limit: 500, offset: 0, withSort: false }), signal).then((r) => r.items) : Promise.resolve(main.items),
        api.assetMap.assets().catch(() => null), // the unified map of TOIR: one point per locomotive (the newer fix of its two trackers)
        api.gps.health({ days: 30, limit: 8 }, signal).catch(() => null),
      ])
      if (signal.aborted) return
      setData(main)
      setMapRows(wide)
      setPoints(unified?.points ?? [])
      setHealth(ranking)
      setLoadedAt(new Date())
      setError(null)
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить сравнение GPS")
    } finally {
      if (!signal.aborted) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, offset, bboxParam])
  const { refresh } = useAutoRefresh(load, [query, bboxParam], paused)

  const rows = useMemo(() => data?.items ?? [], [data])
  const sections = useMemo(() => sectionsData.map((s) => ({ id: s.id, name: s.name })), [sectionsData])
  const sectionName = useCallback((id: string) => sections.find((s) => s.id === id)?.name, [sections])
  const selected = useMemo(() => mapRows.find((r) => r.asset_id === selectedId) ?? rows.find((r) => r.asset_id === selectedId) ?? null, [mapRows, rows, selectedId])
  const chips = useMemo(() => gpsFilterChips(filters, sectionName), [filters, sectionName])
  const offsetHours = data?.feed.utc_offset_hours ?? 5

  const openUnit = useCallback((id: string) => { setSelectedId(id); setCursorId(id) }, [])

  // keyboard: ↑/↓ move through the table (and the open drawer follows), Enter opens the drawer, Esc closes it
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName) || el.isContentEditable)) return
      if (e.key === "Escape") { if (selectedId) setSelectedId(null); return }
      if (rows.length === 0) return
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault()
        const i = rows.findIndex((r) => r.asset_id === (cursorId ?? selectedId))
        const next = rows[Math.min(rows.length - 1, Math.max(0, i < 0 ? 0 : i + (e.key === "ArrowDown" ? 1 : -1)))]
        setCursorId(next.asset_id)
        if (selectedId) setSelectedId(next.asset_id)
        document.getElementById(`gps-row-${next.asset_id}`)?.scrollIntoView({ block: "nearest" })
      } else if (e.key === "Enter" && (cursorId || selectedId)) {
        setSelectedId(cursorId ?? selectedId)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [rows, cursorId, selectedId])

  const markersOf = useCallback((source: "wialon" | "gtk"): GpsMarker[] => mapRows.flatMap((r) => {
    const fix = source === "wialon" ? r.wialon : r.gtk
    if (!fix) return []
    return [{
      id: r.asset_id, lat: fix.lat, lon: fix.lon, color: positionColor(r.position.verdict), hollow: !fix.fresh,
      label: `${r.inv_number} ${r.name} · ${source === "wialon" ? "Wialon" : "GTK"}: ${ageMinText(fix.age_min)} · ${POSITION_LABEL[r.position.verdict]}`,
    }]
  }), [mapRows])
  // «Карта НейроТОиР (единая)»: the point /map/assets draws for each of these locomotives, ringed by the verdict, plus the other tracker's fix as a ghost
  const byAsset = useMemo(() => new Map(points.map((p) => [p.asset_id, p])), [points])
  const toirMarkers = useMemo<GpsMarker[]>(() => mapRows.flatMap((r) => {
    const p = byAsset.get(r.asset_id)
    if (!p) return []
    const color = positionColor(p.gps_verdict ?? r.position.verdict)
    const own: GpsMarker = {
      id: r.asset_id, lat: p.lat, lon: p.lon, color, hollow: p.online === false,
      label: `${r.inv_number} ${r.name} · НейроТОиР: ${p.source === "gtk_gps" ? "GTK GPS" : "Wialon"}${p.gps_diff_m != null ? ` · между трекерами ${distText(p.gps_diff_m)}` : ""} · ${POSITION_LABEL[(p.gps_verdict ?? r.position.verdict) as PositionVerdict] ?? ""}`,
    }
    if (p.alt_lat == null || p.alt_lon == null) return [own]
    return [own, { id: `${r.asset_id}:alt`, selectId: r.asset_id, ghost: true, lat: p.alt_lat, lon: p.alt_lon, color, label: `${r.inv_number} · другой трекер (${p.alt_source === "gtk_gps" ? "GTK GPS" : "Wialon"}), ${ageMinText(p.alt_source === "gtk_gps" ? p.gps_gtk_age_min : p.gps_wialon_age_min)}`, hollow: true }]
  }), [byAsset, mapRows])
  const toirLines = useMemo<GpsLine[]>(() => mapRows.flatMap((r) => {
    const p = byAsset.get(r.asset_id)
    if (!p || p.alt_lat == null || p.alt_lon == null) return []
    return [{ id: `${r.asset_id}:line`, points: [[p.lat, p.lon], [p.alt_lat, p.alt_lon]] as [number, number][], color: positionColor(p.gps_verdict ?? r.position.verdict), weight: 2, dashed: true }]
  }), [byAsset, mapRows])
  const wialonMarkers = useMemo(() => markersOf("wialon"), [markersOf])
  const gtkMarkers = useMemo(() => markersOf("gtk"), [markersOf])

  // ---- KPI tiles: every one applies its filter (a second click removes it) ----
  const s = data?.summary
  const pv = s?.position_verdicts ?? {}
  const hc = s?.health_counts ?? {}
  const diverged = (pv.diverged ?? 0) + (pv.both_stale_apart ?? 0)
  const tiles: Tile[] = s ? [
    { id: "assets", label: "Локомотивов", value: s.assets, hint: "в вашем охвате · сбросить фильтры", testId: "gps-kpi-assets", clear: true },
    { id: "both", label: "Оба трекера", value: s.both_sources, hint: "есть и Wialon, и GTK", testId: "gps-kpi-both", patch: { link: "both" } },
    { id: "confirmed", label: "Подтверждено", value: pv.confirmed ?? 0, hint: "оба свежие и в одном месте", tone: "good", testId: "gps-kpi-confirmed", patch: { verdict: ["confirmed"] } },
    { id: "diverged", label: "Расхождения", value: diverged, hint: "точки далеко друг от друга", tone: diverged > 0 ? "bad" : undefined, testId: "gps-kpi-diverged", patch: { verdict: ["diverged", "both_stale_apart"] } },
    { id: "gtk-stale", label: "GTK молчит", value: pv.gtk_stale ?? 0, hint: `дольше ${FRESH_MIN} мин, Wialon свежий`, tone: (pv.gtk_stale ?? 0) > 0 ? "warn" : undefined, testId: "gps-kpi-gtk-stale", patch: { verdict: ["gtk_stale"] } },
    { id: "wialon-stale", label: "Wialon молчит", value: pv.wialon_stale ?? 0, hint: `дольше ${FRESH_MIN} мин, GTK свежий`, tone: (pv.wialon_stale ?? 0) > 0 ? "warn" : undefined, testId: "gps-kpi-wialon-stale", patch: { verdict: ["wialon_stale"] } },
    { id: "km-wialon", label: `Км Wialon · ${data?.days} дн.`, value: kmText(s.week_wialon_m), hint: "длина сохранённого трека · сортировать", testId: "gps-kpi-km-wialon", patch: { sort_by: "week_wialon_m", sort_dir: "desc" } },
    { id: "km-gtk", label: `Км GTK · ${data?.days} дн.`, value: kmText(s.week_gtk_m), hint: "пробег по данным GTK · сортировать", testId: "gps-kpi-km-gtk", patch: { sort_by: "week_gtk_m", sort_dir: "desc" } },
    { id: "km-unified", label: "Единый пробег", value: kmText(s.week_fused_m ?? s.week_unified_m), hint: "единый трек: Wialon + заполнение из GTK", testId: "gps-kpi-km-unified", patch: { sort_by: "week_fused_m", sort_dir: "desc" } },
    { id: "lost", label: "Потеряно GTK", value: kmText(s.km_lost_m ?? 0), hint: "км Wialon в днях, где GTK не записал", tone: (s.km_lost_m ?? 0) > 0 ? "warn" : undefined, testId: "gps-kpi-lost", patch: { cause: GTK_LOSS_CAUSES } },
    { id: "dead", label: "Мёртвые трекеры", value: (hc.dead ?? 0) + (hc.frozen ?? 0), hint: "GTK не пишет или завис", tone: (hc.dead ?? 0) + (hc.frozen ?? 0) > 0 ? "bad" : undefined, testId: "gps-kpi-dead", patch: { health: ["dead", "frozen"] } },
    {
      id: "status", label: "Норма · внимание · проблема", value: null, hint: "по худшему из признаков", testId: "gps-kpi-status",
      custom: (
        <span className="tabular-nums">
          {([["ok", s.ok, "text-emerald-300"], ["warn", s.warn, "text-amber-300"], ["bad", s.bad, "text-rose-300"]] as const).map(([k, n, cls], i) => (
            <span key={k}>{i > 0 && " · "}
              <button type="button" onClick={(e) => { e.stopPropagation(); set({ severity: toggleValue(filters.severity, k), page: 0 }) }} aria-pressed={filters.severity.includes(k)} data-testid={`gps-kpi-status-${k}`}
                className={`${cls} rounded px-0.5 hover:bg-white/10 ${filters.severity.includes(k) ? "bg-white/20 ring-1 ring-white/50" : ""}`}>{n}</button>
            </span>
          ))}
        </span>
      ),
    },
  ] : []
  const tileActive = (t: Tile) => !!t.patch && patchActive(filters, t.patch)
  const pressTile = (t: Tile) => {
    if (t.clear) return reset({ ...DEFAULT_FILTERS, days: filters.days, date_from: filters.date_from, date_to: filters.date_to })
    if (!t.patch) return
    if (tileActive(t)) {
      const undo = Object.fromEntries(Object.keys(t.patch).map((k) => [k, DEFAULT_FILTERS[k as keyof GpsFilters]])) as Partial<GpsFilters>
      set({ ...undo, page: 0 })
    } else set({ ...t.patch, page: 0 })
  }

  const onSort = (key: string) => {
    if (filters.sort_by === key) set({ sort_dir: filters.sort_dir === "asc" ? "desc" : "asc", page: 0 })
    else set({ sort_by: key as GpsFilters["sort_by"], sort_dir: key === "inv_number" ? "asc" : "desc", page: 0 })
  }
  const onExport = async (format: "csv" | "xlsx") => {
    setExporting(true)
    try {
      const params = gpsApiParams(filters, { limit: PAGE_SIZE, offset: 0, bbox: bboxParam })
      delete params.limit; delete params.offset // the export endpoint returns the whole filtered list
      const blob = await api.gps.exportOverview(params, format)
      downloadBlob(blob, `gps-wialon-gtk-${new Date().toISOString().slice(0, 10)}.${format}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось выгрузить файл")
    } finally {
      setExporting(false)
    }
  }
  const pickClass = (h: string) => set({ health: toggleValue(filters.health, h), page: 0 })

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] min-w-0 space-y-4 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950" data-testid="gps-page">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-sky-900 p-5 text-white shadow-lg sm:p-6">
        <div className="pointer-events-none absolute -right-10 -top-16 h-60 w-60 rounded-full bg-sky-400/10 blur-3xl" />
        <div className="relative flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold sm:text-3xl">GPS: Wialon ↔ GTK</h1>
            <p className="mt-1 max-w-3xl text-sm text-sky-100/80">
              Два независимых трекера на каждом локомотиве: у каждого своя карта, свои треки и свой пробег. Здесь они сравниваются: подтверждают друг друга, а расхождения, провалы и их причины названы. Плитки и диаграммы нажимаются: это фильтры.
              {loadedAt ? ` · обновлено ${loadedAt.toLocaleTimeString("ru-RU")}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/dashboard/gps/wagons" className="rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20">Вагоны →</Link>
            <Link href="/dashboard/map" className="rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20">Единая карта →</Link>
            <button type="button" onClick={() => setPaused(!paused)} aria-pressed={paused} data-testid="gps-pause" className="rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20" title="Автообновление раз в минуту">{paused ? "▶ Автообновление" : "⏸ Пауза"}</button>
            <button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20">
              <RefreshCw className="h-4 w-4" /> Обновить
            </button>
          </div>
        </div>
        <div className="relative mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6" data-testid="gps-kpi">
          {tiles.map((t) => {
            const active = tileActive(t)
            const clickable = !!t.patch || !!t.clear
            return (
              <div
                key={t.id} data-testid={t.testId} data-active={active} role={clickable ? "button" : undefined} tabIndex={clickable ? 0 : undefined} aria-pressed={clickable ? active : undefined}
                onClick={clickable ? () => pressTile(t) : undefined}
                onKeyDown={clickable ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pressTile(t) } } : undefined}
                className={`min-w-0 rounded-2xl p-3 ring-1 backdrop-blur transition ${clickable ? "cursor-pointer hover:brightness-125 focus:outline-none focus-visible:ring-2 focus-visible:ring-white" : ""} ${active ? "ring-2 ring-white" : t.tone === "bad" ? "bg-rose-400/20 ring-rose-300/40" : t.tone === "warn" ? "bg-amber-400/15 ring-amber-300/30" : t.tone === "good" ? "bg-emerald-400/15 ring-emerald-300/30" : "bg-white/10 ring-white/10"} ${active ? "bg-white/20" : ""}`}
              >
                <div className="truncate text-[11px] uppercase tracking-wide text-sky-100/70">{t.label}</div>
                <div className="mt-0.5 truncate text-2xl font-extrabold tabular-nums sm:text-3xl">{t.custom ?? t.value}</div>
                {t.hint && <div className="mt-0.5 text-[11px] leading-tight text-sky-100/60">{t.hint}</div>}
              </div>
            )
          })}
          {!s && <div className="col-span-full flex items-center gap-2 py-6 text-sm text-sky-100/80"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>}
        </div>
      </section>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Положение: кто с кем согласен" hint="Живые позиции двух трекеров на сейчас; сегмент и подпись нажимаются.">
          <StackBar
            order={POSITION_ORDER} counts={pv} label={(k) => POSITION_LABEL[k]} color={positionColor} hint={(k) => POSITION_HINT[k]}
            active={filters.verdict} onPick={(k) => set({ verdict: toggleValue(filters.verdict, k), page: 0 })} testIdPrefix="gps-verdict"
          />
        </Panel>
        <Panel title={`Пробег по дням: ${data?.days ?? filters.days} дн.`} hint="Каждый день каждого локомотива: GTK-пробег против длины трека Wialon.">
          <StackBar
            order={DISTANCE_ORDER} counts={s?.distance_verdicts ?? {}} label={(k) => DISTANCE_LABEL[k]} color={distanceColor} hint={(k) => DISTANCE_HINT[k]}
            active={filters.distance_verdict} onPick={(k) => set({ distance_verdict: toggleValue(filters.distance_verdict, k), page: 0 })} testIdPrefix="gps-dist-verdict"
          />
        </Panel>
        <Panel title="Причины расхождений" hint="Почему пробеги не совпали: по дням окна. Нажмите причину, чтобы увидеть только такие локомотивы.">
          <div data-testid="gps-cause-bar">
            <StackBar
              order={CAUSE_ORDER.filter((c) => c !== "ok")} counts={s?.cause_counts ?? {}} label={(k) => CAUSE_LABEL[k]} color={causeColor} hint={(k) => CAUSE_HINT[k]}
              active={filters.cause} onPick={(k) => set({ cause: toggleValue(filters.cause, k), page: 0 })} testIdPrefix="gps-cause"
            />
          </div>
        </Panel>
      </div>

      <OverviewFilters
        filters={filters} set={set} facets={data?.facets ?? null} sections={sections} qText={qText} onQText={setQText} chips={chips} onReset={() => reset(DEFAULT_FILTERS)}
        total={data?.total ?? 0} shown={rows.length} query={query} onApplyView={(q) => reset(parseGpsFilters(q))} onExport={(f) => void onExport(f)} exporting={exporting} offsetHours={offsetHours}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {([
          ["wialon", "Карта Wialon", WIALON_COLOR, wialonMarkers, [] as GpsLine[], "только позиции Wialon"],
          ["gtk", "Карта GTK", GTK_COLOR, gtkMarkers, [] as GpsLine[], "только позиции GTK GPS"],
          ["toir", "Карта НейроТОиР (единая)", "#7c3aed", toirMarkers, toirLines, "одна точка на локомотив: свежая; пунктир и кружок — позиция другого трекера"],
        ] as const).map(([key, title, color, markers, lines, note]) => (
          <section key={key} className="min-w-0 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2 px-1">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white"><i className="h-3 w-3 rounded-sm" style={{ background: color }} />{title}</h2>
              <span className="text-xs text-gray-500 dark:text-gray-400">{`${markers.filter((m) => !m.ghost).length} точек · ${note} · цвет = вердикт`}</span>
            </header>
            <div className="h-[44vh] min-h-[300px] min-w-0 overflow-hidden rounded-xl">
              {mapError ? <div className="flex h-full items-center justify-center p-4 text-center text-sm text-amber-800">{`Карта OpenStreetMap недоступна: ${mapError}`}</div> : (
                <GpsMap
                  markers={markers} lines={lines} selectedId={selectedId} onSelect={openUnit} onError={setMapError}
                  onViewChange={key === "toir" ? (b) => setRawBbox(bboxText(b)) : undefined}
                  testId={`gps-map-${key}`} ariaLabel={`${title} (OpenStreetMap)`} fitKey={`${key}-${markers.length > 0}`}
                />
              )}
            </div>
          </section>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-white px-3 py-2 text-xs text-gray-600 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-800" aria-label="Условные обозначения цвета">
        {POSITION_ORDER.filter((v) => v !== "no_position").map((v) => <span key={v} className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full" style={{ background: positionColor(v) }} />{POSITION_LABEL[v]}</span>)}
      </div>

      <Panel title="Локомотивы" hint="Нажмите на строку: откроется панель справа и локомотив подсветится на трёх картах. ↑/↓ — по списку, Enter — открыть, Esc — закрыть. Заголовки столбцов сортируют на сервере.">
        {loading && !data ? <div className="flex items-center gap-2 p-6 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>
          : rows.length === 0 ? <Empty text={isDefaultFilters(filters) ? "Нет локомотивов в охвате" : "По выбранным условиям локомотивов нет"} /> : (
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[1180px] text-left text-sm" data-testid="gps-table">
              <thead className="text-xs text-gray-500 dark:text-gray-400">
                <tr>
                  <SortHeader field="inv_number" label="Локомотив" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} />
                  <SortHeader field="wialon_age" label="Wialon" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} />
                  <SortHeader field="gtk_age" label="GTK" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} />
                  <SortHeader field="diff_m" label="Между точками" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} align="right" />
                  <SortHeader field="severity" label="Вердикт" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} />
                  <SortHeader field="cause" label="Причина" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} />
                  <SortHeader field="week_wialon_m" label="Км Wialon" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} align="right" />
                  <SortHeader field="week_gtk_m" label="Км GTK" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} align="right" />
                  <SortHeader field="week_fused_m" label="Единый км ±" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} align="right" />
                  <SortHeader field="confidence" label="Уверенность" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} />
                  <th className="px-2 py-2 text-xs uppercase tracking-wide">По дням</th>
                  <SortHeader field="ratio" label="GTK/Wialon" sortBy={filters.sort_by} sortDir={filters.sort_dir} onSort={onSort} align="right" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {rows.map((r) => {
                  const lead = r.week_wialon_m > 0 ? (r.week_gtk_m / r.week_wialon_m) * 100 : null
                  return (
                    <tr
                      key={r.asset_id} id={`gps-row-${r.asset_id}`} data-testid="gps-row" data-verdict={r.position.verdict} data-status={r.status} onClick={() => openUnit(r.asset_id)}
                      className={`cursor-pointer align-middle hover:bg-gray-50 dark:hover:bg-gray-800/60 ${r.asset_id === selectedId ? "bg-indigo-50 dark:bg-indigo-950/40" : r.asset_id === cursorId ? "bg-gray-50 ring-1 ring-inset ring-indigo-300 dark:bg-gray-800/50" : ""}`}
                    >
                      <td className="px-2 py-2">
                        <div className="flex items-center gap-2">
                          <i className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: positionColor(r.position.verdict) }} />
                          <div className="min-w-0">
                            <Link href={`/dashboard/gps/${r.asset_id}`} onClick={(e) => e.stopPropagation()} className="font-semibold text-blue-700 hover:underline dark:text-blue-400">{r.inv_number}</Link>
                            <div className="max-w-[210px] truncate text-xs text-gray-500 dark:text-gray-400">{r.name}{r.section_name ? ` · ${r.section_name}` : ""}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-2 py-2"><FixCell fix={r.wialon} linked={r.wialon_linked} /></td>
                      <td className="px-2 py-2"><FixCell fix={r.gtk} linked={r.gtk_linked} /></td>
                      <td className="px-2 py-2 text-right tabular-nums">{r.position.diff_m === null || r.position.diff_m === undefined ? "—" : distText(r.position.diff_m)}</td>
                      <td className="px-2 py-2"><PositionChip verdict={r.position.verdict} /></td>
                      <td className="px-2 py-2">
                        <button type="button" disabled={!r.top_cause} onClick={(e) => { e.stopPropagation(); if (r.top_cause) set({ cause: toggleValue(filters.cause, r.top_cause), page: 0 }) }} title="Показать только с такой причиной" className="disabled:cursor-default">
                          <CauseChip cause={r.top_cause} />
                        </button>
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">{kmText(r.week_wialon_m)}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{kmText(r.week_gtk_m)}</td>
                      <td className="px-2 py-2 text-right font-semibold tabular-nums">{fusedText(r.week_fused_m ?? r.week_unified_m, sumGap(r.days))}</td>
                      <td className="px-2 py-2">{r.week_confidence == null ? <span className="text-xs text-gray-400">—</span> : <Chip tone={confidenceTone(r.week_confidence)}>{confidenceText(r.week_confidence)}</Chip>}</td>
                      <td className="px-2 py-2"><MiniPair days={r.days.slice(0, 14)} /></td>
                      <td className="px-2 py-2 text-right tabular-nums">{lead === null ? "—" : fmtPercent(lead)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <Pager total={data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={(page) => set({ page })} />
        <div className="mt-2 flex items-center justify-between gap-3"><SourceLegend /><span className="text-xs text-gray-500 dark:text-gray-400">Столбики: Wialon и GTK по дням, старые слева</span></div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <HealthPanel page={health} activeClasses={filters.health} onPickClass={pickClass} onOpenUnit={openUnit} loading={loading} selectedId={selectedId} />
        <FeedPanel feed={data?.feed ?? null} />
        <Explanation />
      </div>

      {selected && <GpsDrawer row={selected} onClose={() => setSelectedId(null)} />}
      <span className="sr-only" aria-live="polite">{loading ? "Загрузка" : ""}</span>
    </div>
  )
}

function FixCell({ fix, linked }: { fix: GpsAssetRow["wialon"]; linked: boolean }) {
  if (!fix) return <span className="text-xs text-gray-400">{linked ? "нет координат" : "не привязан"}</span>
  return (
    <div className="leading-tight">
      <div className={`tabular-nums ${fix.fresh ? "text-gray-900 dark:text-white" : "text-amber-700 dark:text-amber-400"}`}>{ageMinText(fix.age_min)}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400">{speedText(fix.speed)}</div>
    </div>
  )
}

function FeedPanel({ feed }: { feed: GpsFeedHealth | null }) {
  const rows: { label: string; value: React.ReactNode }[] = feed ? [
    { label: "Приём GTK GPS", value: feed.gtk_enabled ? <Chip tone="ok">включён</Chip> : <Chip tone="warn">выключен (GTK_GPS_SYNC_ENABLED)</Chip> },
    { label: "Последний запуск GTK", value: feed.gtk_last_run_at ? <span className="inline-flex flex-wrap items-center gap-1.5">{timeText(feed.gtk_last_run_at)} <Chip tone={runStatusTone(feed.gtk_last_status)}>{runStatusText(feed.gtk_last_status)}</Chip>{feed.gtk_running ? <Chip tone="info">идёт сейчас</Chip> : null}{feed.gtk_last_error ? <Chip tone="bad">{feed.gtk_last_error}</Chip> : null}</span> : "запусков не было" },
    { label: "Юнитов в ответе GTK", value: <span className="tabular-nums">{feed.gtk_units}{feed.gtk_tracks_failed > 0 ? <span className="ml-2 text-rose-600">треков с ошибкой: {feed.gtk_tracks_failed}</span> : null}</span> },
    { label: "Позиции GTK обновлены", value: <span className={isStale(feed.gtk_units_synced_at, 45) ? "text-amber-700 dark:text-amber-400" : ""}>{timeText(feed.gtk_units_synced_at)}</span> },
    { label: "Позиции Wialon обновлены", value: <span className={isStale(feed.wialon_units_synced_at, 15) ? "text-amber-700 dark:text-amber-400" : ""}>{timeText(feed.wialon_units_synced_at)}</span> },
    { label: "Сохранённые точки трека GTK", value: <span className="tabular-nums">{feed.gtk_track_points.toLocaleString("ru-RU")} · с {timeText(feed.gtk_track_from)}</span> },
    { label: "Сохранённые точки трека Wialon", value: <span className="tabular-nums">{feed.wialon_track_points.toLocaleString("ru-RU")} · с {timeText(feed.wialon_track_from)}</span> },
    { label: "Часовой пояс GTK", value: `UTC${feed.utc_offset_hours >= 0 ? "+" : "−"}${Math.abs(feed.utc_offset_hours)} (дни считаются по нему)` },
  ] : []
  return (
    <section className="min-w-0 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900" data-testid="gps-feed">
      <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Состояние каналов</h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">Откуда берутся данные и когда их обновляли в последний раз.</p>
      {!feed ? <div className="text-sm text-gray-500">Загрузка…</div> : (
        <dl className="divide-y divide-gray-100 text-sm dark:divide-gray-800">
          {rows.map((r) => (
            <div key={r.label} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-1.5">
              <dt className="text-gray-500 dark:text-gray-400">{r.label}</dt>
              <dd className="min-w-0 text-right text-gray-900 dark:text-gray-100">{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}

function Explanation() {
  const items: [string, string][] = [
    ["Свежесть", `Позиция старше ${FRESH_MIN} минут считается устаревшей: трекер молчит или техника выключена. Если молчит только один из двух, вердикт «GTK молчит» или «Wialon молчит», а на карте рисуется свежий.`],
    ["Допуск между точками", `Оба трекера свежие: допуск = ${BASE_TOLERANCE_M} м + скорость × (разница времени фиксов + 30 с). Движущийся локомотив легко «расходится» на 200–700 м из-за того, что точки сняты в разные секунды; стоящий — нет. Больше допуска — «Расхождение».`],
    ["Оба молчат", `Последние точки ближе ${SAME_SPOT_M} м — «место совпало», иначе — «места разные».`],
    ["Пробег за день", `GTK-пробег делится на длину сохранённого трека Wialon: ${Math.round(MATCH_RANGE[0] * 100)}–${Math.round(MATCH_RANGE[1] * 100)}% — «Совпало», ${Math.round(MINOR_RANGE[0] * 100)}–${Math.round(MINOR_RANGE[1] * 100)}% — «Небольшая разница», вне этого — провал у GTK или Wialon. Меньше ${IDLE_M / 1000} км в обоих — «Стоял».`],
    ["Причина", "Если пробеги не совпали, система называет причину: GTK не писал весь день, молчал два часа и больше, присылал мало точек; провал у Wialon; провалы у обоих; либо трекеры без провалов и разница мала (метод подсчёта)."],
    ["Единый пробег", "Единый трек: берётся трек Wialon, а провалы заполняются точками GTK. Если молчали оба, участок соединяется прямой, и эта часть показана как «±» (неопределённость). Уверенность — доля дня, покрытая точками, и согласие трекеров."],
  ]
  return (
    <section className="min-w-0 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900" data-testid="gps-explain">
      <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Как принимается решение</h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">Пороги проверены на живых данных парка; их использует и единая карта.</p>
      <ul className="space-y-2 text-sm">
        {items.map(([title, text]) => (
          <li key={title}><b className="text-gray-900 dark:text-white">{title}.</b> <span className="text-gray-700 dark:text-gray-300">{text}</span></li>
        ))}
      </ul>
    </section>
  )
}
