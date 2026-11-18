"use client"

// Phrases the command centre did not understand (admin): the list the catalogue is extended from. Nothing is learned automatically.
import { useCallback, useEffect, useMemo, useState } from "react"
import { Loader2, Mic, RefreshCw, Search } from "@/components/ui/icons"
import { api, type AssistantUnmatchedPage } from "@/lib/api"
import { mapAssistantError } from "@/lib/assistant"

const PAGE_SIZE = 50

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(date)
}

export default function AssistantAdminPage() {
  const [data, setData] = useState<AssistantUnmatchedPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [offset, setOffset] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.assistant.unmatched({ limit: PAGE_SIZE, offset }))
    } catch (e) {
      setError(mapAssistantError(e))
    } finally {
      setLoading(false)
    }
  }, [offset])

  useEffect(() => {
    void load()
  }, [load])

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const all = data?.items ?? []
    return needle ? all.filter((item) => item.text.toLowerCase().includes(needle) || (item.best_intent ?? "").toLowerCase().includes(needle)) : all
  }, [data, query])

  const total = data?.total ?? 0

  return (
    <div data-testid="assistant-admin-page" className="mx-auto w-full max-w-6xl min-w-0 space-y-4 p-4 md:p-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-white"><Mic /> Помощник: непонятые фразы</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-gray-400">
            Фразы, которые голосовой помощник не распознал как команду, самые частые сверху. По ним расширяется каталог команд; автоматического обучения нет.
          </p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-60 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-700">
          {loading ? <Loader2 className="animate-spin" /> : <RefreshCw />} Обновить
        </button>
      </header>

      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по фразе или команде"
          aria-label="Поиск"
          className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>

      {error ? <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200">{error}</p> : null}

      <section className="min-w-0 rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-gray-800/60 dark:text-gray-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">Фраза</th>
                <th className="px-4 py-2.5 text-right font-medium">Раз</th>
                <th className="px-4 py-2.5 font-medium">Последний раз</th>
                <th className="px-4 py-2.5 font-medium">Ближайшая команда</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-gray-800">
              {items.map((item, i) => (
                <tr key={`${item.text}-${i}`}>
                  <td className="max-w-[420px] break-words px-4 py-2.5 font-medium text-slate-900 dark:text-white">{item.text}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{item.count}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-slate-600 dark:text-gray-300">{formatDate(item.last_at)}</td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-gray-300">{item.best_intent ?? "—"}</td>
                </tr>
              ))}
              {!loading && items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-gray-400">{query ? "Ничего не найдено" : "Непонятых фраз нет"}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-2 text-xs text-slate-500 dark:border-gray-800 dark:text-gray-400">
          <span>Всего: {total}</span>
          <span className="inline-flex gap-2">
            <button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="rounded-lg px-2 py-1 ring-1 ring-slate-200 disabled:opacity-40 dark:ring-gray-700">← Назад</button>
            <button type="button" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => setOffset(offset + PAGE_SIZE)} className="rounded-lg px-2 py-1 ring-1 ring-slate-200 disabled:opacity-40 dark:ring-gray-700">Вперёд →</button>
          </span>
        </footer>
      </section>
    </div>
  )
}
