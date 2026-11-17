"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { api } from "@/lib/api"
import {
  DETAIL_LABEL, DETAIL_ORDER, candidateText, reasonExplanation, sinceText, sourceText,
  type UnplacedDetail, type UnplacedPage,
} from "@/lib/map-view"
import { ArrowLeft, Loader2, RefreshCw } from "@/components/ui/icons"

const PAGE_SIZE = 50
type SortKey = "reason" | "inv_number" | "asset_type" | "age"

const SORT_LABEL: Record<SortKey, string> = {
  reason: "По причине",
  inv_number: "По инв. номеру",
  asset_type: "По типу",
  age: "Давно в системе — сначала старые",
}

const chip = "rounded-full px-3 py-1 text-sm ring-1 transition"
const chipIdle = "bg-white text-gray-800 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-800 dark:hover:bg-gray-800"
const chipActive = "bg-blue-600 text-white ring-blue-600"

export default function UnplacedAssetsPage() {
  const [page, setPage] = useState<UnplacedPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  const [debouncedQ, setDebouncedQ] = useState("")
  const [type, setType] = useState("")
  const [reason, setReason] = useState<UnplacedDetail | "">("")
  const [onlyLinkable, setOnlyLinkable] = useState(false)
  const [sort, setSort] = useState<SortKey>("reason")
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQ(q.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [q])

  // a new filter starts again from the first page
  useEffect(() => setOffset(0), [debouncedQ, type, reason, onlyLinkable, sort])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.assetMap.unplaced({
        q: debouncedQ, asset_type: type, reason, only_linkable: onlyLinkable, sort_by: sort, limit: PAGE_SIZE, offset,
      })
      setPage(response)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить список")
    } finally {
      setLoading(false)
    }
  }, [debouncedQ, type, reason, onlyLinkable, sort, offset])

  useEffect(() => {
    void load()
  }, [load])

  const summary = page?.summary
  const from = page && page.total > 0 ? page.offset + 1 : 0
  const to = page ? Math.min(page.offset + page.items.length, page.total) : 0

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] space-y-5 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950">
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0">
          <Link href="/dashboard/map" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline dark:text-blue-400">
            <ArrowLeft className="h-4 w-4" /> К карте
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">Объекты без координат</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Какие основные средства не показаны на карте, почему, как давно они известны системе и откуда должна приходить их позиция
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
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2" aria-label="Причины">
            <button type="button" onClick={() => setReason("")} className={`${chip} ${reason === "" ? chipActive : chipIdle}`}>
              Все: <b>{summary.total}</b>
            </button>
            {DETAIL_ORDER.filter((code) => (summary.by_reason[code] ?? 0) > 0).map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setReason(reason === code ? "" : code)}
                className={`${chip} ${reason === code ? chipActive : chipIdle}`}
              >
                {DETAIL_LABEL[code]}: <b>{summary.by_reason[code]}</b>
              </button>
            ))}
          </div>
          {summary.linkable > 0 && (
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-900 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:ring-emerald-900">
              <input type="checkbox" checked={onlyLinkable} onChange={(event) => setOnlyLinkable(event.target.checked)} />
              Можно привязать к GTK сразу: <b>{summary.linkable}</b> — инв. и рег. номер совпали со свободным вагоном GTK
            </label>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Инв. или серийный номер"
          aria-label="Поиск"
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 sm:w-64 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        />
        <select
          value={type}
          onChange={(event) => setType(event.target.value)}
          aria-label="Тип"
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        >
          <option value="">Все типы</option>
          {(summary?.by_type ?? []).map((t) => <option key={t.value} value={t.value}>{`${t.label} (${t.count})`}</option>)}
        </select>
        <select
          value={sort}
          onChange={(event) => setSort(event.target.value as SortKey)}
          aria-label="Сортировка"
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        >
          {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => <option key={key} value={key}>{SORT_LABEL[key]}</option>)}
        </select>
        <span className="text-sm text-gray-500 dark:text-gray-400">{page ? `Показано ${from}–${to} из ${page.total}` : ""}</span>
        {loading && <Loader2 className="h-4 w-4 animate-spin text-gray-500" />}
      </div>

      <ul className="space-y-3" aria-label="Объекты без координат">
        {page && page.items.length === 0 && !loading && (
          <li className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-gray-800 dark:bg-gray-900">
            Нет объектов без координат по выбранным условиям.
          </li>
        )}
        {(page?.items ?? []).map((item) => {
          const hint = candidateText(item.candidate)
          return (
            <li
              key={item.asset_id}
              data-testid="unplaced-item"
              className="grid gap-3 rounded-xl border border-gray-200 bg-white p-4 text-sm lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)_minmax(0,340px)] dark:border-gray-800 dark:bg-gray-900"
            >
              <div className="min-w-0">
                <p className="truncate font-semibold text-gray-900 dark:text-white">{item.name}</p>
                <p className="text-gray-500 dark:text-gray-400">Инв. № {item.inv_number}</p>
                <p className="text-gray-500 dark:text-gray-400">{[item.asset_type_name, item.section_name, item.status_name].filter(Boolean).join(" · ")}</p>
              </div>
              <div className="min-w-0 space-y-1">
                <p className="font-medium text-amber-800 dark:text-amber-300">{DETAIL_LABEL[item.reason]}</p>
                <p className="text-gray-700 dark:text-gray-300">{reasonExplanation(item)}</p>
                {hint && <p className="rounded-lg bg-emerald-50 p-2 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">{hint}</p>}
              </div>
              <div className="min-w-0 space-y-1 text-gray-600 dark:text-gray-400">
                <p><span className="font-medium text-gray-800 dark:text-gray-200">Как давно:</span> {sinceText(item)}</p>
                <p><span className="font-medium text-gray-800 dark:text-gray-200">Откуда позиция:</span> {sourceText(item)}</p>
                <p>
                  <Link className="text-blue-600 hover:underline dark:text-blue-400" href={`/dashboard/directories/assets?q=${encodeURIComponent(item.inv_number)}`}>
                    Карточка ОС (привязки)
                  </Link>
                </p>
              </div>
            </li>
          )
        })}
      </ul>

      {page && page.total > PAGE_SIZE && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
          >
            Назад
          </button>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= page.total || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
          >
            Дальше
          </button>
        </div>
      )}

      <p className="text-xs text-gray-500 dark:text-gray-400">
        История позиций не хранится, поэтому «как давно» показывает, с какого момента актив известен системе или источнику, а не когда была последняя позиция.
      </p>
    </div>
  )
}
