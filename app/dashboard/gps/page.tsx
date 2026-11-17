"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import type { MapPoint } from "@/lib/map-view"
import { useDebouncedValue } from "@/lib/use-debounced-value"
import {
  BASE_TOLERANCE_M, DISTANCE_HINT, DISTANCE_LABEL, DISTANCE_ORDER, FRESH_MIN, IDLE_M, MATCH_RANGE, MINOR_RANGE, POSITION_HINT, POSITION_LABEL, POSITION_ORDER, SAME_SPOT_M,
  ageMinText, distText, distanceColor, isStale, kmText, positionColor, runStatusText, runStatusTone, speedText, statusTone, timeText,
  type GpsAssetRow, type GpsFeedHealth, type GpsOverview, type PositionVerdict,
} from "@/lib/gps-view"
import { Empty, Panel } from "../scales/_components/viz"
import { Loader2, RefreshCw } from "@/components/ui/icons"
import { GpsMap, type GpsLine, type GpsMarker } from "./_components/GpsMap"
import { Chip, GTK_COLOR, MiniPair, PositionChip, SourceLegend, StackBar, WIALON_COLOR } from "./_components/parts"

const REFRESH_MS = 60_000
const DAY_OPTIONS = [1, 2, 3, 5, 7, 10, 14, 21, 31]
const field = "rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
const chipBtn = (on: boolean) => `rounded-full px-3 py-1 text-sm ring-1 transition ${on ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-gray-800 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-800"}`

type Tile = { label: string; value: React.ReactNode; hint?: string; tone?: "warn" | "bad" | "good"; testId?: string }

export default function GpsPage() {
  const [days, setDays] = useState(7)
  const [q, setQ] = useState("")
  const [verdict, setVerdict] = useState<PositionVerdict | "">("")
  const [onlyIssues, setOnlyIssues] = useState(false)
  const [section, setSection] = useState("")
  const [data, setData] = useState<GpsOverview | null>(null)
  const [points, setPoints] = useState<MapPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)
  const debouncedQ = useDebouncedValue(q, 300)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [value, unified] = await Promise.all([
        api.gps.overview({ days, q: debouncedQ.trim() || undefined, verdict: verdict || undefined, only_issues: onlyIssues, limit: 500 }),
        api.assetMap.assets().catch(() => null), // the unified map of TOIR: one point per locomotive (the newer fix of its two trackers)
      ])
      setPoints(unified?.points ?? [])
      setData(value)
      setLoadedAt(new Date())
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить сравнение GPS")
    } finally {
      setLoading(false)
    }
  }, [days, debouncedQ, verdict, onlyIssues])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(true), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  const sections = useMemo(() => [...new Set((data?.items ?? []).map((r) => r.section_name).filter((s): s is string => !!s))].sort(), [data])
  const rows = useMemo(() => (data?.items ?? []).filter((r) => !section || r.section_name === section), [data, section])
  const selected = useMemo(() => rows.find((r) => r.asset_id === selectedId) ?? null, [rows, selectedId])

  const markersOf = useCallback((source: "wialon" | "gtk"): GpsMarker[] => rows.flatMap((r) => {
    const fix = source === "wialon" ? r.wialon : r.gtk
    if (!fix) return []
    return [{
      id: r.asset_id, lat: fix.lat, lon: fix.lon, color: positionColor(r.position.verdict), hollow: !fix.fresh,
      label: `${r.inv_number} ${r.name} · ${source === "wialon" ? "Wialon" : "GTK"}: ${ageMinText(fix.age_min)} · ${POSITION_LABEL[r.position.verdict]}`,
    }]
  }), [rows])
  // «Карта TOIR (единая)»: the point /map/assets draws for each of these locomotives, ringed by the verdict, plus the other tracker's fix as a ghost
  const toirMarkers = useMemo<GpsMarker[]>(() => {
    const byAsset = new Map(points.map((p) => [p.asset_id, p]))
    return rows.flatMap((r) => {
      const p = byAsset.get(r.asset_id)
      if (!p) return []
      const color = positionColor(p.gps_verdict ?? r.position.verdict)
      const own: GpsMarker = {
        id: r.asset_id, lat: p.lat, lon: p.lon, color, hollow: p.online === false,
        label: `${r.inv_number} ${r.name} · TOIR: ${p.source === "gtk_gps" ? "GTK GPS" : "Wialon"}${p.gps_diff_m != null ? ` · между трекерами ${distText(p.gps_diff_m)}` : ""} · ${POSITION_LABEL[(p.gps_verdict ?? r.position.verdict) as PositionVerdict] ?? ""}`,
      }
      if (p.alt_lat == null || p.alt_lon == null) return [own]
      return [own, { id: `${r.asset_id}:alt`, selectId: r.asset_id, ghost: true, lat: p.alt_lat, lon: p.alt_lon, color, label: `${r.inv_number} · другой трекер (${p.alt_source === "gtk_gps" ? "GTK GPS" : "Wialon"}), ${ageMinText(p.alt_source === "gtk_gps" ? p.gps_gtk_age_min : p.gps_wialon_age_min)}`, hollow: true }]
    })
  }, [points, rows])
  const toirLines = useMemo<GpsLine[]>(() => {
    const byAsset = new Map(points.map((p) => [p.asset_id, p]))
    return rows.flatMap((r) => {
      const p = byAsset.get(r.asset_id)
      if (!p || p.alt_lat == null || p.alt_lon == null) return []
      return [{ id: `${r.asset_id}:line`, points: [[p.lat, p.lon], [p.alt_lat, p.alt_lon]] as [number, number][], color: positionColor(p.gps_verdict ?? r.position.verdict), weight: 2, dashed: true }]
    })
  }, [points, rows])
  const wialonMarkers = useMemo(() => markersOf("wialon"), [markersOf])
  const gtkMarkers = useMemo(() => markersOf("gtk"), [markersOf])

  const s = data?.summary
  const pv = s?.position_verdicts ?? {}
  const tiles: Tile[] = s ? [
    { label: "Локомотивов", value: s.assets, hint: "в вашем охвате", testId: "gps-kpi-assets" },
    { label: "Оба трекера", value: s.both_sources, hint: "есть и Wialon, и GTK", testId: "gps-kpi-both" },
    { label: "Подтверждено", value: pv.confirmed ?? 0, hint: "оба свежие и в одном месте", tone: "good", testId: "gps-kpi-confirmed" },
    { label: "Расхождения", value: (pv.diverged ?? 0) + (pv.both_stale_apart ?? 0), hint: "точки далеко друг от друга", tone: (pv.diverged ?? 0) + (pv.both_stale_apart ?? 0) > 0 ? "bad" : undefined, testId: "gps-kpi-diverged" },
    { label: "GTK молчит", value: pv.gtk_stale ?? 0, hint: `дольше ${FRESH_MIN} мин, Wialon свежий`, tone: (pv.gtk_stale ?? 0) > 0 ? "warn" : undefined, testId: "gps-kpi-gtk-stale" },
    { label: "Wialon молчит", value: pv.wialon_stale ?? 0, hint: `дольше ${FRESH_MIN} мин, GTK свежий`, tone: (pv.wialon_stale ?? 0) > 0 ? "warn" : undefined, testId: "gps-kpi-wialon-stale" },
    { label: `Км Wialon · ${data?.days} дн.`, value: kmText(s.week_wialon_m), hint: "длина сохранённого трека", testId: "gps-kpi-km-wialon" },
    { label: `Км GTK · ${data?.days} дн.`, value: kmText(s.week_gtk_m), hint: "пробег по данным GTK", testId: "gps-kpi-km-gtk" },
    { label: "Единый пробег", value: kmText(s.week_unified_m), hint: "совпало — среднее, провал — полный источник", testId: "gps-kpi-km-unified" },
    {
      label: "Норма · внимание · проблема",
      value: <span className="tabular-nums"><span className="text-emerald-300">{s.ok}</span> · <span className="text-amber-300">{s.warn}</span> · <span className="text-rose-300">{s.bad}</span></span>,
      hint: "по худшему из признаков", testId: "gps-kpi-status",
    },
  ] : []

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] min-w-0 space-y-4 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950" data-testid="gps-page">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-sky-900 p-5 text-white shadow-lg sm:p-6">
        <div className="pointer-events-none absolute -right-10 -top-16 h-60 w-60 rounded-full bg-sky-400/10 blur-3xl" />
        <div className="relative flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold sm:text-3xl">GPS: Wialon ↔ GTK</h1>
            <p className="mt-1 max-w-3xl text-sm text-sky-100/80">
              Два независимых трекера на каждом локомотиве: у каждого своя карта, свои треки и свой пробег. Здесь они сравниваются: подтверждают друг друга, а расхождения и провалы названы.
              {loadedAt ? ` · обновлено ${loadedAt.toLocaleTimeString("ru-RU")}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/dashboard/map" className="rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20">Единая карта →</Link>
            <button type="button" onClick={() => void load()} className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20">
              <RefreshCw className="h-4 w-4" /> Обновить
            </button>
          </div>
        </div>
        <div className="relative mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5" data-testid="gps-kpi">
          {tiles.map((t) => (
            <div key={t.label} data-testid={t.testId} className={`min-w-0 rounded-2xl p-3 ring-1 backdrop-blur ${t.tone === "bad" ? "bg-rose-400/20 ring-rose-300/40" : t.tone === "warn" ? "bg-amber-400/15 ring-amber-300/30" : t.tone === "good" ? "bg-emerald-400/15 ring-emerald-300/30" : "bg-white/10 ring-white/10"}`}>
              <div className="truncate text-[11px] uppercase tracking-wide text-sky-100/70">{t.label}</div>
              <div className="mt-0.5 truncate text-2xl font-extrabold tabular-nums sm:text-3xl">{t.value}</div>
              {t.hint && <div className="mt-0.5 text-[11px] leading-tight text-sky-100/60">{t.hint}</div>}
            </div>
          ))}
          {!s && <div className="col-span-full flex items-center gap-2 py-6 text-sm text-sky-100/80"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>}
        </div>
      </section>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Инв. номер, название, участок" aria-label="Поиск" className={`${field} w-full sm:w-72`} />
        <select value={verdict} onChange={(e) => setVerdict(e.target.value as PositionVerdict | "")} aria-label="Вердикт" className={field}>
          <option value="">Все вердикты</option>
          {POSITION_ORDER.filter((v) => v !== "no_position" || (pv.no_position ?? 0) > 0).map((v) => <option key={v} value={v}>{`${POSITION_LABEL[v]}${pv[v] ? ` (${pv[v]})` : ""}`}</option>)}
        </select>
        <select value={section} onChange={(e) => setSection(e.target.value)} aria-label="Участок" className={field}>
          <option value="">Все участки</option>
          {sections.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
          Период
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Период, дней" className={field}>
            {DAY_OPTIONS.map((d) => <option key={d} value={d}>{d === 1 ? "сегодня" : `${d} дн.`}</option>)}
          </select>
        </label>
        <button type="button" className={chipBtn(onlyIssues)} aria-pressed={onlyIssues} onClick={() => setOnlyIssues(!onlyIssues)} data-testid="gps-only-issues">Только проблемные</button>
        <span className="text-sm text-gray-500 dark:text-gray-400">Показано: <b>{rows.length}</b>{data && data.total !== rows.length ? ` из ${data.total}` : ""}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Положение: кто с кем согласен" hint="Живые позиции двух трекеров на сейчас; нажмите на вердикт, чтобы отфильтровать.">
          <StackBar
            order={POSITION_ORDER} counts={pv} label={(k) => POSITION_LABEL[k]} color={positionColor} hint={(k) => POSITION_HINT[k]}
            active={verdict || null} onPick={(k) => setVerdict(verdict === k ? "" : k)} testIdPrefix="gps-verdict"
          />
        </Panel>
        <Panel title={`Пробег по дням: ${data?.days ?? days} дн.`} hint="Каждый день каждого локомотива: GTK-пробег против длины трека Wialon.">
          <StackBar
            order={DISTANCE_ORDER} counts={s?.distance_verdicts ?? {}} label={(k) => DISTANCE_LABEL[k]} color={distanceColor} hint={(k) => DISTANCE_HINT[k]} testIdPrefix="gps-dist-verdict"
          />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {([
          ["wialon", "Карта Wialon", WIALON_COLOR, wialonMarkers, [] as GpsLine[], "только позиции Wialon"],
          ["gtk", "Карта GTK", GTK_COLOR, gtkMarkers, [] as GpsLine[], "только позиции GTK GPS"],
          ["toir", "Карта TOIR (единая)", "#7c3aed", toirMarkers, toirLines, "одна точка на локомотив: свежая; пунктир и кружок — позиция другого трекера"],
        ] as const).map(([key, title, color, markers, lines, note]) => (
          <section key={key} className="min-w-0 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2 px-1">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white"><i className="h-3 w-3 rounded-sm" style={{ background: color }} />{title}</h2>
              <span className="text-xs text-gray-500 dark:text-gray-400">{`${markers.filter((m) => !m.ghost).length} точек · ${note} · цвет = вердикт`}</span>
            </header>
            <div className="h-[44vh] min-h-[300px] min-w-0 overflow-hidden rounded-xl">
              {mapError ? <div className="flex h-full items-center justify-center p-4 text-center text-sm text-amber-800">{`Карта OpenStreetMap недоступна: ${mapError}`}</div> : (
                <GpsMap
                  markers={markers} lines={lines} selectedId={selectedId} onSelect={setSelectedId} onError={setMapError}
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

      {selected && <SelectedStrip row={selected} onClose={() => setSelectedId(null)} />}

      <Panel title="Локомотивы: худшие сверху" hint="Нажмите на строку, чтобы показать локомотив на обеих картах; инвентарный номер ведёт в подробное сравнение.">
        {loading && !data ? <div className="flex items-center gap-2 p-6 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>
          : rows.length === 0 ? <Empty text={onlyIssues || verdict || q ? "По выбранным условиям локомотивов нет" : "Нет локомотивов в охвате"} /> : (
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[980px] text-left text-sm" data-testid="gps-table">
              <thead className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
                <tr>
                  <th className="px-2 py-2">Локомотив</th>
                  <th className="px-2 py-2">Wialon</th>
                  <th className="px-2 py-2">GTK</th>
                  <th className="px-2 py-2 text-right">Между точками</th>
                  <th className="px-2 py-2">Вердикт</th>
                  <th className="px-2 py-2 text-right">Км Wialon</th>
                  <th className="px-2 py-2 text-right">Км GTK</th>
                  <th className="px-2 py-2 text-right">Единый км</th>
                  <th className="px-2 py-2">По дням</th>
                  <th className="px-2 py-2 text-right">Проблемных дней</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {rows.map((r) => (
                  <tr
                    key={r.asset_id} data-testid="gps-row" data-verdict={r.position.verdict} data-status={r.status} onClick={() => setSelectedId(r.asset_id === selectedId ? null : r.asset_id)}
                    className={`cursor-pointer align-middle hover:bg-gray-50 dark:hover:bg-gray-800/60 ${r.asset_id === selectedId ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}`}
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
                    <td className="px-2 py-2 text-right tabular-nums">{kmText(r.week_wialon_m)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{kmText(r.week_gtk_m)}</td>
                    <td className="px-2 py-2 text-right font-semibold tabular-nums">{kmText(r.week_unified_m)}</td>
                    <td className="px-2 py-2"><MiniPair days={r.days.slice(0, 14)} /></td>
                    <td className="px-2 py-2 text-right">{r.distance_issues > 0 ? <Chip tone={statusTone(r.status === "ok" ? "warn" : r.status)}>{`${r.distance_issues} из ${r.days.length}`}</Chip> : <span className="text-xs text-gray-400">нет</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-2 flex items-center justify-between gap-3"><SourceLegend /><span className="text-xs text-gray-500 dark:text-gray-400">Столбики справа: Wialon и GTK по дням, старые слева</span></div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <FeedPanel feed={data?.feed ?? null} />
        <Explanation />
      </div>
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

function SelectedStrip({ row, onClose }: { row: GpsAssetRow; onClose: () => void }) {
  return (
    <section className="rounded-2xl border border-indigo-200 bg-indigo-50 p-3 dark:border-indigo-900 dark:bg-indigo-950/40" data-testid="gps-selected">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-gray-900 dark:text-white">{row.inv_number} · {row.name}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-700 dark:text-gray-200">
            <PositionChip verdict={row.position.verdict} />
            <span>Wialon: {row.wialon ? `${timeText(row.wialon.at)} (${ageMinText(row.wialon.age_min)})` : "нет позиции"}</span>
            <span>GTK: {row.gtk ? `${timeText(row.gtk.at)} (${ageMinText(row.gtk.age_min)})` : "нет позиции"}</span>
            {row.position.diff_m !== null && row.position.diff_m !== undefined && <span>между точками {distText(row.position.diff_m)}</span>}
          </div>
        </div>
        <div className="flex gap-2 text-xs">
          <Link href={`/dashboard/gps/${row.asset_id}`} className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-700">Подробное сравнение →</Link>
          <button type="button" onClick={onClose} aria-label="Снять выбор" className="rounded-lg bg-white px-2.5 py-1.5 text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50">✕</button>
        </div>
      </div>
    </section>
  )
}

function FeedPanel({ feed }: { feed: GpsFeedHealth | null }) {
  const rows: { label: string; value: React.ReactNode }[] = feed ? [
    { label: "Приём GTK GPS", value: feed.gtk_enabled ? <Chip tone="ok">включён</Chip> : <Chip tone="warn">выключен (GTK_GPS_SYNC_ENABLED)</Chip> },
    { label: "Последний запуск GTK", value: feed.gtk_last_run_at ? <span className="inline-flex flex-wrap items-center gap-1.5">{timeText(feed.gtk_last_run_at)} <Chip tone={runStatusTone(feed.gtk_last_status)}>{runStatusText(feed.gtk_last_status)}</Chip>{feed.gtk_last_error ? <Chip tone="bad">{feed.gtk_last_error}</Chip> : null}</span> : "запусков не было" },
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
    ["Единый пробег", "Совпало — среднее двух; небольшая разница или провал — значение источника, который записал больше. Так провал одного трекера не занижает пробег."],
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
