"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Activity,
  CalendarDays,
  Download,
  Filter,
  RefreshCw,
  Search,
  X,
} from "@/components/ui/icons"
import { api, type AuditAction, type AuditLogEntry, type AuditLogFacets, type AuditLogFilters } from "@/lib/api"

const ACTIONS: Array<{ value: AuditAction | ""; label: string }> = [
  { value: "", label: "Все действия" },
  { value: "create", label: "Создание" },
  { value: "update", label: "Изменение" },
  { value: "delete", label: "Удаление" },
  { value: "login", label: "Авторизация" },
  { value: "logout", label: "Выход" },
  { value: "other", label: "Другое" },
]

const ACTION_STYLE: Record<AuditAction, string> = {
  create: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  update: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  delete: "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300",
  login: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  logout: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  other: "bg-violet-100 text-violet-800 dark:bg-violet-950/60 dark:text-violet-300",
}

const ACTION_LABEL: Record<AuditAction, string> = {
  create: "Создание",
  update: "Изменение",
  delete: "Удаление",
  login: "Авторизация",
  logout: "Выход",
  other: "Другое",
}
const PAGE_SIZE = 50

const INPUT_CLASS =
  "h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-blue-700 dark:focus:ring-blue-950"

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value))
}

function displayModule(module: string) {
  const labels: Record<string, string> = {
    assets: "Основные средства",
    auth: "Авторизация",
    gtk: "Данные GTK",
    maintenance: "ТО и ремонты",
    sections: "Участки",
    users: "Пользователи",
    wialon: "Данные Wialon",
    "work-orders": "Наряд-заказы",
  }
  return labels[module] ?? module
}

function renderValue(value: unknown) {
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function AuditDetails({
  entry,
  onClose,
}: {
  entry: AuditLogEntry
  onClose: () => void
}) {
  const fields = useMemo(
    () => [...new Set([...Object.keys(entry.old_values ?? {}), ...Object.keys(entry.new_values ?? {})])],
    [entry.old_values, entry.new_values],
  )

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-details-title"
        className="max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5 dark:border-slate-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">Детали события</p>
            <h2 id="audit-details-title" className="mt-1 text-lg font-bold text-slate-900 dark:text-white">
              {ACTION_LABEL[entry.action]} · {entry.object_label || entry.object_type || displayModule(entry.module)}
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{formatDate(entry.created_at)}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="max-h-[calc(90vh-100px)] space-y-5 overflow-y-auto p-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoCard label="Пользователь" value={entry.actor_name || (entry.actor_type === "system" ? "Система" : "Неизвестен")} />
            <InfoCard label="Раздел / маршрут" value={`${displayModule(entry.module)} · ${entry.route}`} />
            <InfoCard label="Объект" value={`${entry.object_label || entry.object_type || "—"}${entry.object_id ? ` · ${entry.object_id}` : ""}`} />
            <InfoCard label="Источник" value={entry.actor_type === "system" ? "Автоматическое действие" : entry.actor_type === "anonymous" ? "Без авторизации" : "Пользователь"} />
          </div>
          {fields.length > 0 ? (
            <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  <tr><th className="px-4 py-3">Поле</th><th className="px-4 py-3">Было</th><th className="px-4 py-3">Стало</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {fields.map((field) => (
                    <tr key={field}>
                      <td className="px-4 py-3 font-medium text-slate-700 dark:text-slate-200">{field}</td>
                      <td className="max-w-[240px] break-words px-4 py-3 text-rose-700 dark:text-rose-300">{renderValue(entry.old_values?.[field])}</td>
                      <td className="max-w-[240px] break-words px-4 py-3 text-emerald-700 dark:text-emerald-300">{renderValue(entry.new_values?.[field])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="rounded-xl bg-slate-50 px-4 py-5 text-sm text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              Для этого события сравнение полей не предусмотрено.
            </p>
          )}
          {entry.details && Object.keys(entry.details).length > 0 && (
            <pre className="overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-200">{JSON.stringify(entry.details, null, 2)}</pre>
          )}
        </div>
      </section>
    </div>
  )
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-800/70">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-slate-800 dark:text-slate-100">{value}</p>
    </div>
  )
}

export default function AuditLogsPage() {
  const [filters, setFilters] = useState<AuditLogFacets>({ users: [], modules: [] })
  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<AuditLogEntry | null>(null)
  const [draft, setDraft] = useState<AuditLogFilters>({})
  const [applied, setApplied] = useState<AuditLogFilters>({})
  const [searchText, setSearchText] = useState("")
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState("")
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const loadLogs = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const result = await api.auditLogs.list({ ...applied, limit: PAGE_SIZE, offset })
      setEntries(result.items)
      setTotal(result.total)
      setUpdatedAt(new Date())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить журнал.")
    } finally {
      setLoading(false)
    }
  }, [applied, offset])

  useEffect(() => {
    api.auditLogs.filters().then(setFilters).catch((loadError: unknown) => {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить фильтры.")
    })
  }, [])

  useEffect(() => {
    void loadLogs()
  }, [loadLogs, refreshKey])

  const applyFilters = () => {
    setApplied({
      ...draft,
      date_from: draft.date_from ? new Date(draft.date_from).toISOString() : undefined,
      date_to: draft.date_to ? new Date(draft.date_to).toISOString() : undefined,
      q: searchText.trim() || undefined,
    })
    setOffset(0)
  }

  const resetFilters = () => {
    setDraft({})
    setSearchText("")
    setApplied({})
    setOffset(0)
  }

  const exportCsv = async () => {
    setExporting(true)
    setError("")
    try {
      const file = await api.auditLogs.exportCsv(applied)
      const url = URL.createObjectURL(file)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = "audit-logs.csv"
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Не удалось экспортировать журнал.")
    } finally {
      setExporting(false)
    }
  }

  const firstRow = total === 0 ? 0 : offset + 1
  const lastRow = Math.min(offset + PAGE_SIZE, total)

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50 px-4 py-6 dark:bg-gray-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-blue-950 to-indigo-950 p-6 text-white shadow-xl sm:p-8">
          <div className="absolute -right-8 -top-16 h-64 w-64 rounded-full bg-blue-500/20 blur-3xl" />
          <div className="relative flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <div>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/15 bg-white/10">
                <Activity className="h-6 w-6 text-cyan-300" />
              </div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-200">Контроль действий</p>
              <h1 className="mt-2 text-2xl font-bold sm:text-3xl">Журнал логов</h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-300">
                История действий пользователей и автоматических процессов с деталями изменений.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div className="rounded-2xl border border-white/15 bg-white/10 px-4 py-3">
                <p className="text-xs text-blue-200">Событий по фильтру</p>
                <p className="mt-1 text-2xl font-bold">{total.toLocaleString("ru-RU")}</p>
              </div>
              <button type="button" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading} className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 text-sm font-semibold transition hover:bg-white/20 disabled:opacity-50">
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                Обновить
              </button>
            </div>
          </div>
          <p className="relative mt-5 text-xs text-blue-200">
            {updatedAt ? `Обновлено: ${updatedAt.toLocaleTimeString("ru-RU")}` : "Ожидание данных"}
          </p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-6">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
            <Filter className="h-4 w-4 text-blue-600 dark:text-blue-400" />
            Фильтры и поиск
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <label className="space-y-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
              Тип действия
              <select className={INPUT_CLASS} value={draft.action ?? ""} onChange={(event) => setDraft((current) => ({ ...current, action: (event.target.value || undefined) as AuditAction | undefined }))}>
                {ACTIONS.map((action) => <option key={action.value} value={action.value}>{action.label}</option>)}
              </select>
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
              Пользователь
              <select className={INPUT_CLASS} value={draft.actor_id ?? ""} onChange={(event) => setDraft((current) => ({ ...current, actor_id: event.target.value || undefined }))}>
                <option value="">Все пользователи</option>
                {filters.users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
              </select>
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
              Раздел системы
              <select className={INPUT_CLASS} value={draft.module ?? ""} onChange={(event) => setDraft((current) => ({ ...current, module: event.target.value || undefined }))}>
                <option value="">Все разделы</option>
                {filters.modules.map((module) => <option key={module} value={module}>{displayModule(module)}</option>)}
              </select>
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
              Объект / техника
              <input className={INPUT_CLASS} value={draft.object_q ?? ""} onChange={(event) => setDraft((current) => ({ ...current, object_q: event.target.value || undefined }))} placeholder="Название или номер" />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
              <span className="inline-flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" />С даты и времени</span>
              <input type="datetime-local" className={INPUT_CLASS} value={draft.date_from ?? ""} onChange={(event) => setDraft((current) => ({ ...current, date_from: event.target.value || undefined }))} />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
              До даты и времени (UTC)
              <input type="datetime-local" className={INPUT_CLASS} value={draft.date_to ?? ""} onChange={(event) => setDraft((current) => ({ ...current, date_to: event.target.value || undefined }))} />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-500 dark:text-slate-400 sm:col-span-2">
              Поиск по ключевым словам
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input className={`${INPUT_CLASS} pl-9`} value={searchText} onChange={(event) => setSearchText(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") applyFilters() }} placeholder="Пользователь, страница, объект, значения полей..." />
              </div>
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={applyFilters} className="h-10 rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700">Применить фильтры</button>
            <button type="button" onClick={resetFilters} className="h-10 rounded-xl border border-slate-200 px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">Сбросить</button>
            <button type="button" onClick={() => void exportCsv()} disabled={exporting} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">
              <Download className="h-4 w-4" />{exporting ? "Экспорт..." : "Экспорт CSV"}
            </button>
          </div>
        </section>

        {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">{error}</div>}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
            <h2 className="font-semibold text-slate-900 dark:text-white">События системы</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">{firstRow}–{lastRow} из {total.toLocaleString("ru-RU")}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800/70 dark:text-slate-400">
                <tr>
                  <th className="px-5 py-3.5">Тип действия</th>
                  <th className="px-5 py-3.5">Пользователь</th>
                  <th className="px-5 py-3.5">Раздел / страница</th>
                  <th className="px-5 py-3.5">Объект / техника</th>
                  <th className="px-5 py-3.5">Дата и время</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {entries.map((entry) => (
                  <tr key={entry.id} tabIndex={0} onClick={() => setSelected(entry)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected(entry) } }} className="cursor-pointer transition hover:bg-blue-50/60 focus:bg-blue-50/60 focus:outline-none dark:hover:bg-blue-950/20 dark:focus:bg-blue-950/20">
                    <td className="px-5 py-4">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${ACTION_STYLE[entry.action]}`}>{ACTION_LABEL[entry.action]}</span>
                    </td>
                    <td className="px-5 py-4 font-medium text-slate-800 dark:text-slate-100">{entry.actor_name || (entry.actor_type === "system" ? "Система" : "Неизвестен")}</td>
                    <td className="px-5 py-4">
                      <p className="font-medium text-slate-800 dark:text-slate-100">{displayModule(entry.module)}</p>
                      <p className="mt-0.5 max-w-[260px] truncate text-xs text-slate-500 dark:text-slate-400">{entry.route}</p>
                    </td>
                    <td className="px-5 py-4">
                      <p className="font-medium text-slate-800 dark:text-slate-100">{entry.object_label || entry.object_type || "—"}</p>
                      {entry.object_id && <p className="mt-0.5 max-w-[180px] truncate text-xs text-slate-500 dark:text-slate-400">{entry.object_id}</p>}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600 dark:text-slate-300">{formatDate(entry.created_at)}</td>
                  </tr>
                ))}
                {!loading && entries.length === 0 && (
                  <tr><td colSpan={5} className="px-5 py-14 text-center text-sm text-slate-500 dark:text-slate-400">По заданным условиям записи не найдены.</td></tr>
                )}
                {loading && (
                  <tr><td colSpan={5} className="px-5 py-14 text-center text-sm text-slate-500 dark:text-slate-400">Загрузка журнала...</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3 dark:border-slate-800">
            <button type="button" disabled={offset === 0 || loading} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-slate-700">Назад</button>
            <button type="button" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => setOffset((value) => value + PAGE_SIZE)} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-slate-700">Далее</button>
          </div>
        </section>
      </div>
      {selected && <AuditDetails entry={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
