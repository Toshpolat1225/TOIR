"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { api, type AssetMapSummary } from "@/lib/api"
import {
  SOURCE_LABEL, UNPLACED_LABEL, ageText, filterPoints, googleEmbedUrl, googleMapsLink, isTracked, markerColor, trainText, typeOptions,
  type MapPoint, type MapSource,
} from "@/lib/map-view"
import { KIND_LABEL, TRUE_SCALE_ZOOM, iconSvg, type IconKind, type LiveTrain } from "@/lib/map-icons"
import { MOVING_KMH, buildTrains, fleetStats, historyHref, isLocomotive, movementText, type TrainOnLine } from "@/lib/map-history"
import { locoHref, wagonHref } from "@/lib/scales-insights"
import { GROUP_COLOR, GROUP_LABEL, GROUP_ORDER, gpsPointLines, groupCounts, positionColor, verdictGroup, type VerdictGroup } from "@/lib/gps-view"
import { GoogleAssetMap } from "./_components/GoogleAssetMap"
import { OsmAssetMap } from "./_components/OsmAssetMap"
import { HBars } from "../scales/_components/viz"
import { Loader2, MapPin, RefreshCw } from "@/components/ui/icons"

// Public by design (it ends up in the page); restrict it by HTTP referrer in Google Cloud.
const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? ""
const REFRESH_MS = 60_000
const LIST_LIMIT = 300
type Tab = "trains" | "units" | "summary"
const TAB_LABEL: Record<Tab, string> = { trains: "Составы", units: "Единицы", summary: "Сводка" }
const field = "rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
const chip = (on: boolean) => `rounded-full px-3 py-1 text-sm ring-1 transition ${on ? "bg-blue-600 text-white ring-blue-600" : "bg-white text-gray-800 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-800"}`

export default function MapPage() {
  const [points, setPoints] = useState<MapPoint[]>([])
  const [liveTrains, setLiveTrains] = useState<LiveTrain[]>([])
  const [summary, setSummary] = useState<AssetMapSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [osmError, setOsmError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  const [type, setType] = useState("")
  const [source, setSource] = useState<MapSource | "">("")
  const [verdictFilter, setVerdictFilter] = useState<VerdictGroup | "">("")
  const [section, setSection] = useState("")
  const [onlyMoving, setOnlyMoving] = useState(false)
  const [onlyOnline, setOnlyOnline] = useState(false)
  const [tab, setTab] = useState<Tab>("trains")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [response, drawn] = await Promise.all([api.assetMap.assets(), api.assetMap.trains().catch(() => null)])
      setLiveTrains(drawn?.trains ?? [])
      setPoints(response.points)
      setSummary(response.summary)
      setLoadedAt(new Date())
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить данные карты")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(true), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  const sections = useMemo(() => [...new Set(points.map((p) => p.section_name).filter((s): s is string => !!s))].sort(), [points])
  const visible = useMemo(() => {
    const base = filterPoints(points, { q, type, source })
    return base.filter((p) => {
      if (section && p.section_name !== section) return false
      if (verdictFilter && verdictGroup(p.gps_verdict) !== verdictFilter) return false
      if (onlyOnline && !(isTracked(p.source) && p.online)) return false
      if (onlyMoving) {
        const speed = p.speed === null || p.speed === undefined || p.speed === "" ? null : Number(p.speed)
        if (!(isTracked(p.source) && speed !== null && speed >= MOVING_KMH)) return false
      }
      return true
    })
  }, [points, q, type, source, section, onlyMoving, onlyOnline, verdictFilter])
  const verdictCounts = useMemo(() => groupCounts(summary?.gps_verdicts), [summary])
  const hasVerdicts = GROUP_ORDER.some((g) => verdictCounts[g] > 0)
  const stats = useMemo(() => fleetStats(points), [points])
  // trains drawn to scale: those with a visible locomotive or a visible wagon
  const drawnTrains = useMemo(() => {
    const ids = new Set(visible.map((p) => p.asset_id))
    return liveTrains.filter((t) => (t.loco_asset_id && ids.has(t.loco_asset_id)) || t.vehicles.some((v) => v.asset_id && ids.has(v.asset_id)) || t.vehicles.some((v) => v.hidden))
  }, [liveTrains, visible])
  const trains = useMemo(() => buildTrains(visible), [visible])
  const types = useMemo(() => typeOptions(points), [points])
  const selected = useMemo(() => points.find((p) => p.asset_id === selectedId) ?? null, [points, selectedId])
  const selectedGps = useMemo(() => (selected ? gpsPointLines(selected) : null), [selected])
  const useGoogle = GOOGLE_MAPS_API_KEY !== "" && mapError === null
  const useOsm = !useGoogle && osmError === null

  const focusTrain = (t: TrainOnLine) => setSelectedId(t.locoPoint?.asset_id ?? t.wagons[0]?.asset_id ?? null)

  const tiles: { label: string; value: string | number; hint?: string; tone?: string; href?: string }[] = [
    { label: "На карте", value: stats.placed, hint: summary ? `из ${summary.total_assets} основных средств` : undefined },
    { label: "На связи сейчас", value: stats.online, hint: "техника с GPS, сообщение < 15 мин" },
    { label: "Едут сейчас", value: stats.moving, hint: `скорость от ${MOVING_KMH} км/ч` },
    { label: "Составов на линии", value: stats.trains, hint: `${stats.wagonsInTrains} вагонов в них` },
    { label: "Молчат более суток", value: stats.silent24h, hint: "GPS не передаёт позицию", tone: stats.silent24h ? "warn" : undefined },
    ...(hasVerdicts ? [{ label: "Подтверждено двумя GPS", value: verdictCounts.confirmed, hint: `${verdictCounts.diverged} расхождений · GTK молчит: ${verdictCounts.gtk_stale} · Wialon молчит: ${verdictCounts.wialon_stale}`, tone: verdictCounts.diverged ? "warn" : undefined, href: "/dashboard/gps" }] : []),
    ...(summary && summary.unplaced > 0 ? [{ label: "Без координат", value: summary.unplaced, hint: "нажмите: почему и как давно", tone: "warn", href: "/dashboard/map/unplaced" }] : []),
  ]

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] space-y-4 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-emerald-950 to-teal-900 p-5 text-white shadow-lg sm:p-6">
        <div className="pointer-events-none absolute -left-10 -top-16 h-60 w-60 rounded-full bg-emerald-400/10 blur-3xl" />
        <div className="relative flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-bold sm:text-3xl">Карта парка</h1>
            <p className="mt-1 max-w-3xl text-sm text-emerald-100/80">
              Где находится каждое основное средство. Вагоны без GPS показаны у локомотива своего состава. Выберите единицу, чтобы увидеть, где она была раньше, с каким локомотивом и что делала.
              {loadedAt ? ` · обновлено ${loadedAt.toLocaleTimeString("ru-RU")}` : ""}
            </p>
          </div>
          <button type="button" onClick={() => void load()} className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm font-medium ring-1 ring-white/20 hover:bg-white/20">
            <RefreshCw className="h-4 w-4" /> Обновить
          </button>
        </div>
        <div className="relative mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-7" data-testid="map-kpis">
          {tiles.map((t) => {
            const body = (
              <div className={`h-full rounded-2xl p-3 ring-1 backdrop-blur ${t.tone === "warn" ? "bg-amber-400/15 ring-amber-300/30" : "bg-white/10 ring-white/10"}`}>
                <div className="text-[11px] uppercase tracking-wide text-emerald-100/70">{t.label}</div>
                <div className="mt-0.5 text-3xl font-extrabold tabular-nums">{t.value}</div>
                {t.hint && <div className="mt-0.5 text-[11px] text-emerald-100/60">{t.hint}</div>}
              </div>
            )
            return t.href ? <Link key={t.label} href={t.href} className="block transition hover:-translate-y-0.5">{body}</Link> : <div key={t.label}>{body}</div>
          })}
        </div>
      </section>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Инв. номер, название, участок, № состава" aria-label="Поиск" className={`${field} w-full sm:w-80`} />
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Источник">
          <button type="button" className={chip(source === "")} onClick={() => setSource("")}>Все</button>
          {(["wialon", "gtk_gps", "gtk", "train"] as MapSource[]).map((s) => (
            <button key={s} type="button" className={chip(source === s)} aria-pressed={source === s} onClick={() => setSource(source === s ? "" : s)}>
              <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full" style={{ background: markerColor({ source: s, online: true }) }} />{SOURCE_LABEL[s]}: {summary?.by_source[s] ?? 0}
            </button>
          ))}
        </div>
        {hasVerdicts && (
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Сверка Wialon и GTK GPS" data-testid="map-verdict-chips">
            {GROUP_ORDER.filter((g) => verdictCounts[g] > 0 || verdictFilter === g).map((g) => (
              <button key={g} type="button" data-testid={`map-verdict-chip-${g}`} className={chip(verdictFilter === g)} aria-pressed={verdictFilter === g} onClick={() => setVerdictFilter(verdictFilter === g ? "" : g)}>
                <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full ring-2 ring-offset-1" style={{ background: "#fff", boxShadow: `inset 0 0 0 2px ${GROUP_COLOR[g]}` }} />{GROUP_LABEL[g]}: {verdictCounts[g]}
              </button>
            ))}
          </div>
        )}
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Тип" className={field}>
          <option value="">Все типы</option>
          {types.map((t) => <option key={t.value} value={t.value}>{`${t.label} (${t.count})`}</option>)}
        </select>
        <select value={section} onChange={(e) => setSection(e.target.value)} aria-label="Участок" className={field}>
          <option value="">Все участки</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button type="button" className={chip(onlyMoving)} aria-pressed={onlyMoving} onClick={() => setOnlyMoving(!onlyMoving)}>Только едущие</button>
        <button type="button" className={chip(onlyOnline)} aria-pressed={onlyOnline} onClick={() => setOnlyOnline(!onlyOnline)}>Только на связи</button>
        <span className="text-sm text-gray-500 dark:text-gray-400">Показано: <b>{visible.length}</b></span>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-white px-3 py-2 text-xs text-gray-600 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-800" data-testid="map-legend" aria-label="Условные обозначения">
        {(["electric", "diesel", "dump", "tank", "platform"] as IconKind[]).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span dangerouslySetInnerHTML={{ __html: iconSvg(k, "online", 30) }} />{KIND_LABEL[k]}
          </span>
        ))}
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-[#16a34a]" />на связи</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-[#9ca3af]" />нет связи</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-[#0d9488]" />GTK GPS</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-[#3b82f6]" />по GTK</span>
        {hasVerdicts && (
          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1" data-testid="map-verdict-legend">
            кольцо у локомотива:
            {GROUP_ORDER.map((g) => <span key={g} className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full bg-white" style={{ boxShadow: `inset 0 0 0 2px ${GROUP_COLOR[g]}` }} />{GROUP_LABEL[g]}</span>)}
            <span>· пунктир и пустой кружок — позиция второго трекера</span>
          </span>
        )}
        <span className="ml-auto text-gray-500">Состав: значок с числом вагонов; приблизьте карту (от {TRUE_SCALE_ZOOM}-го уровня) и он рисуется в масштабе, вагоны по порядку GTK</span>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="h-[72vh] min-h-[460px] overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
          {loading && points.length === 0 ? (
            <div className="flex h-full items-center justify-center text-gray-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загрузка…</div>
          ) : useGoogle ? (
            <GoogleAssetMap apiKey={GOOGLE_MAPS_API_KEY} points={visible} selectedId={selectedId} onSelect={setSelectedId} onError={setMapError} />
          ) : useOsm ? (
            <div className="flex h-full flex-col">
              {mapError && <div className="border-b border-amber-200 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">{`Карта Google недоступна: ${mapError}. Показана карта OpenStreetMap.`}</div>}
              <div className="min-h-0 flex-1"><OsmAssetMap points={visible} trains={drawnTrains} selectedId={selectedId} onSelect={setSelectedId} onError={setOsmError} /></div>
            </div>
          ) : (
            <div className="flex h-full flex-col">
              <div className="border-b border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                {`Интерактивная карта недоступна: ${osmError ?? mapError ?? ""}. (Нет доступа к интернету?) `}Выберите единицу в списке: её положение откроется на карте Google ниже.
              </div>
              {selected ? <iframe key={selected.asset_id} title={`Положение ${selected.name}`} src={googleEmbedUrl(selected.lat, selected.lon)} className="h-full w-full border-0" loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
                : <div className="flex flex-1 items-center justify-center text-sm text-gray-500"><MapPin className="mr-2 h-5 w-5" /> Выберите единицу в списке</div>}
            </div>
          )}
        </div>

        <aside className="flex h-[72vh] min-h-[460px] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900" aria-label="Панель карты">
          {selected && (
            <div className="border-b border-gray-200 bg-gradient-to-r from-emerald-50 to-teal-50 p-3 dark:border-gray-800 dark:from-emerald-950/40 dark:to-teal-950/30" data-testid="inspector">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-gray-900 dark:text-white">{selected.name}</div>
                  <div className="text-xs text-gray-600 dark:text-gray-300">Инв. № {selected.inv_number}{selected.section_name ? ` · ${selected.section_name}` : ""}{selected.status_name ? ` · ${selected.status_name}` : ""}</div>
                </div>
                <button type="button" aria-label="Закрыть" className="text-gray-400 hover:text-gray-700" onClick={() => setSelectedId(null)}>✕</button>
              </div>
              <div className="mt-1 text-xs text-gray-700 dark:text-gray-200">
                {movementText(selected)} · {SOURCE_LABEL[selected.source]} · {ageText(selected.position_at)}
                {trainText(selected) ? <div>{trainText(selected)}</div> : null}
              </div>
              {selectedGps && (
                <div className="mt-2 rounded-lg bg-white/80 p-2 text-xs text-gray-800 ring-1 ring-gray-200 dark:bg-gray-900/60 dark:text-gray-100 dark:ring-gray-700" data-testid="inspector-gps">
                  <div className="flex items-center gap-1.5 font-semibold"><i className="h-2.5 w-2.5 rounded-full" style={{ background: positionColor(selectedGps.verdict) }} />{selectedGps.verdictLabel}</div>
                  <div>Рисуется: {selectedGps.drawn}</div>
                  {selectedGps.other && <div>Второй трекер: {selectedGps.other}</div>}
                  {selectedGps.diff && <div>Между точками: {selectedGps.diff}</div>}
                  <div className="mt-0.5 text-gray-500 dark:text-gray-400">{selectedGps.hint}</div>
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {selectedGps && <Link className="rounded-lg bg-teal-600 px-3 py-1.5 font-medium text-white hover:bg-teal-700" href={`/dashboard/gps/${selected.asset_id}`} data-testid="open-gps">Сравнение GPS →</Link>}
                <Link className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-700" href={historyHref({ asset_id: selected.asset_id })} data-testid="open-history">Где был и с кем →</Link>
                {isLocomotive(selected.asset_type)
                  ? <Link className="rounded-lg bg-white px-3 py-1.5 text-blue-700 ring-1 ring-blue-200 hover:bg-blue-50" href={locoHref(selected.asset_id)}>Работа по весам</Link>
                  : <Link className="rounded-lg bg-white px-3 py-1.5 text-blue-700 ring-1 ring-blue-200 hover:bg-blue-50" href={wagonHref({ asset_id: selected.asset_id, carriage_gtk_id: 0 })}>Рейсы по весам</Link>}
                {selected.locomotive_asset_id && <Link className="rounded-lg bg-white px-3 py-1.5 text-blue-700 ring-1 ring-blue-200 hover:bg-blue-50" href={historyHref({ asset_id: selected.locomotive_asset_id })}>Его локомотив →</Link>}
                <Link className="rounded-lg bg-white px-3 py-1.5 text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50" href={`/dashboard/directories/assets?q=${encodeURIComponent(selected.inv_number)}`}>Карточка ОС</Link>
                <a className="rounded-lg bg-white px-3 py-1.5 text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50" href={googleMapsLink(selected.lat, selected.lon)} target="_blank" rel="noopener noreferrer">Google Maps</a>
              </div>
            </div>
          )}

          <div className="flex gap-1 border-b border-gray-200 p-2 dark:border-gray-800" role="tablist">
            {(Object.keys(TAB_LABEL) as Tab[]).map((k) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`flex-1 rounded-lg px-3 py-1.5 text-sm ${tab === k ? "bg-blue-600 text-white" : "text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"}`}>
                {TAB_LABEL[k]}{k === "trains" ? ` (${trains.length})` : k === "units" ? ` (${visible.length})` : ""}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {tab === "trains" && (
              trains.length === 0 ? <p className="p-4 text-sm text-gray-500">{loading ? "Загрузка…" : "Составов с вагонами на карте нет по выбранным условиям."}</p> : (
                <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                  {trains.map((t) => (
                    <li key={t.key} data-testid="train-row">
                      <button type="button" onClick={() => focusTrain(t)} className={`block w-full px-3 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-800 ${t.locoPoint && t.locoPoint.asset_id === selectedId ? "bg-blue-50 dark:bg-blue-950/40" : ""}`}>
                        <span className="flex items-center justify-between gap-2">
                          <span className="min-w-0 truncate text-sm font-semibold text-gray-900 dark:text-white">⚡ {t.locoInv ?? ""} {t.locoName}</span>
                          <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${t.moving ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"}`}>{t.moving ? `едет ${Math.round(t.speed ?? 0)} км/ч` : t.online === false ? "нет связи" : "стоит"}</span>
                        </span>
                        <span className="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">{t.wagons.length} вагонов · {ageText(t.positionAt)}</span>
                        <span className="mt-1.5 flex flex-wrap gap-1">{t.wagons.slice(0, 14).map((w) => <span key={w.asset_id} className="h-3 w-3 rounded-[3px] bg-amber-500" title={w.inv_number} />)}{t.wagons.length > 14 && <span className="text-[10px] text-gray-500">+{t.wagons.length - 14}</span>}</span>
                      </button>
                      <div className="flex flex-wrap gap-x-3 px-3 pb-2 text-xs">
                        {t.locoId && <Link className="text-blue-600 hover:underline dark:text-blue-400" href={historyHref({ asset_id: t.locoId })}>История локомотива →</Link>}
                        {t.wagons.slice(0, 4).map((w) => <Link key={w.asset_id} className="text-gray-600 hover:underline dark:text-gray-300" href={historyHref({ asset_id: w.asset_id })}>{w.inv_number}</Link>)}
                      </div>
                    </li>
                  ))}
                </ul>
              )
            )}

            {tab === "units" && (
              visible.length === 0 ? <p className="p-4 text-sm text-gray-500">{loading ? "Загрузка…" : "Нет единиц с координатами по выбранным условиям."}</p> : (
                <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                  {visible.slice(0, LIST_LIMIT).map((p) => (
                    <li key={p.asset_id}>
                      <button type="button" onClick={() => setSelectedId(p.asset_id === selectedId ? null : p.asset_id)} className={`block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 ${p.asset_id === selectedId ? "bg-blue-50 dark:bg-blue-950/40" : ""}`}>
                        <span className="flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: markerColor(p) }} />{p.gps_verdict ? <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full bg-white" title={gpsPointLines(p)?.verdictLabel} style={{ boxShadow: `inset 0 0 0 2px ${positionColor(p.gps_verdict)}` }} /> : null}<span className="truncate font-medium text-gray-900 dark:text-white">{p.name}</span></span>
                        <span className="mt-0.5 block truncate text-xs text-gray-500 dark:text-gray-400">{`${trainText(p) ?? SOURCE_LABEL[p.source]} · ${movementText(p)} · ${ageText(p.position_at)}${p.section_name ? ` · ${p.section_name}` : ""}`}</span>
                      </button>
                    </li>
                  ))}
                  {visible.length > LIST_LIMIT && <li className="p-3 text-xs text-gray-500">{`Показаны первые ${LIST_LIMIT} из ${visible.length}: уточните поиск.`}</li>}
                </ul>
              )
            )}

            {tab === "summary" && (
              <div className="space-y-5 p-3">
                <div><h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">По типам</h3><HBars unit="" color="#0ea5e9" items={stats.byType.slice(0, 8).map((x) => ({ key: x.key, label: x.label, value: x.count }))} /></div>
                <div><h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">По участкам</h3><HBars unit="" color="#10b981" items={stats.bySection.slice(0, 8).map((x) => ({ key: x.key, label: x.label, value: x.count }))} /></div>
                {summary && summary.unplaced > 0 && (
                  <div><h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Почему нет на карте</h3>
                    <ul className="space-y-1 text-sm">{Object.entries(summary.unplaced_reasons).map(([reason, count]) => <li key={reason} className="flex justify-between gap-2"><span>{UNPLACED_LABEL[reason] ?? reason}</span><b>{count}</b></li>)}</ul>
                    <Link href="/dashboard/map/unplaced" className="mt-2 inline-block text-sm text-blue-600 hover:underline dark:text-blue-400">Подробнее: какие объекты и как давно →</Link>
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
