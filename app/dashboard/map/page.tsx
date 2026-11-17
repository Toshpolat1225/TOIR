"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { api, type AssetMapSummary } from "@/lib/api"
import {
  SOURCE_LABEL, UNPLACED_LABEL, ageText, filterPoints, googleEmbedUrl, googleMapsLink, markerColor, typeOptions,
  type MapPoint, type MapSource,
} from "@/lib/map-view"
import { GoogleAssetMap } from "./_components/GoogleAssetMap"
import { Loader2, MapPin, RefreshCw } from "@/components/ui/icons"

// Public by design (it ends up in the page); restrict it by HTTP referrer in Google Cloud.
const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? ""
const REFRESH_MS = 60_000
const LIST_LIMIT = 300

export default function MapPage() {
  const [points, setPoints] = useState<MapPoint[]>([])
  const [summary, setSummary] = useState<AssetMapSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  const [type, setType] = useState("")
  const [source, setSource] = useState<MapSource | "">("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const response = await api.assetMap.assets()
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

  const visible = useMemo(() => filterPoints(points, { q, type, source }), [points, q, type, source])
  const types = useMemo(() => typeOptions(points), [points])
  const selected = useMemo(() => visible.find((p) => p.asset_id === selectedId) ?? null, [visible, selectedId])
  const useGoogle = GOOGLE_MAPS_API_KEY !== "" && mapError === null

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] space-y-5 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950">
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Карта</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Где находится каждое основное средство: позиция из Wialon (GPS) или GTK
            {loadedAt ? ` · обновлено ${loadedAt.toLocaleTimeString("ru-RU")}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
        >
          <RefreshCw className="h-4 w-4" /> Обновить
        </button>
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </p>
      )}

      {summary && (
        <div className="flex flex-wrap gap-2 text-sm">
          <span className="rounded-full bg-white px-3 py-1 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-800">
            На карте: <b>{summary.placed}</b> из {summary.total_assets}
          </span>
          <span className="rounded-full bg-white px-3 py-1 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-800">
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full" style={{ background: markerColor({ source: "wialon", online: true }) }} />
            Wialon: <b>{summary.by_source.wialon ?? 0}</b>
          </span>
          <span className="rounded-full bg-white px-3 py-1 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-800">
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full" style={{ background: markerColor({ source: "gtk" }) }} />
            GTK: <b>{summary.by_source.gtk ?? 0}</b>
          </span>
          {summary.unplaced > 0 && (
            <span
              className="rounded-full bg-amber-50 px-3 py-1 text-amber-900 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900"
              title="Эти единицы не нарисованы: для них нет координат"
            >
              Без координат: <b>{summary.unplaced}</b>
              {" ("}
              {Object.entries(summary.unplaced_reasons).map(([reason, count]) => `${UNPLACED_LABEL[reason] ?? reason}: ${count}`).join("; ")}
              {")"}
            </span>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Инв. номер, название, участок"
          aria-label="Поиск"
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 sm:w-72 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        />
        <select
          value={type}
          onChange={(event) => setType(event.target.value)}
          aria-label="Тип"
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        >
          <option value="">Все типы</option>
          {types.map((t) => <option key={t.value} value={t.value}>{`${t.label} (${t.count})`}</option>)}
        </select>
        <select
          value={source}
          onChange={(event) => setSource(event.target.value as MapSource | "")}
          aria-label="Источник"
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        >
          <option value="">Все источники</option>
          <option value="wialon">{SOURCE_LABEL.wialon}</option>
          <option value="gtk">{SOURCE_LABEL.gtk}</option>
        </select>
        <span className="text-sm text-gray-500 dark:text-gray-400">Показано: {visible.length}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="h-[68vh] min-h-[420px] overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          {loading && points.length === 0 ? (
            <div className="flex h-full items-center justify-center text-gray-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загрузка…</div>
          ) : useGoogle ? (
            <GoogleAssetMap
              apiKey={GOOGLE_MAPS_API_KEY}
              points={visible}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onError={setMapError}
            />
          ) : (
            <div className="flex h-full flex-col">
              <div className="border-b border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                {mapError
                  ? `Интерактивная карта Google недоступна: ${mapError}. `
                  : "Ключ Google Maps не задан: интерактивная карта со всеми точками отключена. "}
                Выберите единицу в списке — её положение откроется на карте Google ниже. Чтобы увидеть все точки сразу, администратор
                задаёт <code>GOOGLE_MAPS_API_KEY</code> (см. docs/DEPLOY.md).
              </div>
              {selected ? (
                <iframe
                  key={selected.asset_id}
                  title={`Положение ${selected.name}`}
                  src={googleEmbedUrl(selected.lat, selected.lon)}
                  className="h-full w-full border-0"
                  loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              ) : (
                <div className="flex flex-1 items-center justify-center text-sm text-gray-500"><MapPin className="mr-2 h-5 w-5" /> Выберите единицу в списке</div>
              )}
            </div>
          )}
        </div>

        <aside className="h-[68vh] min-h-[420px] overflow-y-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900" aria-label="Список единиц">
          {visible.length === 0 ? (
            <p className="p-4 text-sm text-gray-500">{loading ? "Загрузка…" : "Нет единиц с координатами по выбранным условиям."}</p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-800">
              {visible.slice(0, LIST_LIMIT).map((p) => (
                <li key={p.asset_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(p.asset_id === selectedId ? null : p.asset_id)}
                    className={`block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 ${p.asset_id === selectedId ? "bg-blue-50 dark:bg-blue-950/40" : ""}`}
                  >
                    <span className="flex items-center gap-2">
                      <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: markerColor(p) }} />
                      <span className="truncate font-medium text-gray-900 dark:text-white">{p.name}</span>
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-gray-500 dark:text-gray-400">
                      {`${SOURCE_LABEL[p.source]} · ${ageText(p.position_at)}${p.section_name ? ` · ${p.section_name}` : ""}`}
                    </span>
                  </button>
                  {p.asset_id === selectedId && (
                    <div className="space-x-3 px-3 pb-2 text-xs">
                      <a className="text-blue-600 hover:underline dark:text-blue-400" href={googleMapsLink(p.lat, p.lon)} target="_blank" rel="noopener noreferrer">Открыть в Google Maps</a>
                      <a className="text-blue-600 hover:underline dark:text-blue-400" href={`/dashboard/directories/assets?q=${encodeURIComponent(p.inv_number)}`}>Карточка ОС</a>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {visible.length > LIST_LIMIT && (
            <p className="border-t border-gray-100 p-3 text-xs text-gray-500 dark:border-gray-800">{`Показаны первые ${LIST_LIMIT} из ${visible.length}: уточните поиск.`}</p>
          )}
        </aside>
      </div>
    </div>
  )
}
