"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Container,
  Loader2,
  Radio,
  RefreshCw,
  Search,
  Train,
  X,
} from "@/components/ui/icons"
import { Button } from "@/components/ui/button"
import {
  api,
  type GtkCarriage,
  type GtkCreateAssetsResponse,
  type GtkLocomotive,
  type GtkStatus,
  type GtkSyncRun,
  type GtkTrain,
  type GtkTrainDetail,
} from "@/lib/api"
import { useAuth } from "@/lib/auth-context"

type Tab = "locomotives" | "carriages" | "trains"
type PageResponse<T> = { items: T[]; total: number }
type PendingLink = {
  gtkId: number
  kind: "locomotive" | "carriage"
  name: string
  assetId: string
  assetName: string
  expectedInventoryNumber: string
}

const PAGE_SIZE = 50
const panelClass = "rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
const inputClass = "rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
const selectClass = `${inputClass} min-w-36`

function dateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—"
}

function statusLabel(status: GtkSyncRun["status"]) {
  const labels: Record<string, string> = {
    ok: "Успешно",
    error: "Ошибка",
    parse_error: "Ошибка разбора",
    suspicious: "Подозрительные данные",
    login_failed: "Ошибка входа",
  }
  return labels[status] ?? "нет данных"
}

function skipReasonLabel(reason: string | null) {
  const labels: Record<string, string> = {
    inactive: "Вагон неактивен",
    empty_name: "Нет названия вагона",
    already_linked: "Уже привязан к ОС",
    inventory_number_in_use: "Инвентарный номер уже занят",
  }
  return reason ? labels[reason] ?? "Не удалось создать ОС" : "Причина не указана"
}

function qualityList(quality: Record<string, unknown> | null, key: string): unknown[] {
  const value = quality?.[key]
  if (Array.isArray(value)) return value
  if (value && typeof value === "object") {
    const items = (value as Record<string, unknown>).items
    return Array.isArray(items) ? items : []
  }
  return []
}

function countQuality(quality: Record<string, unknown> | null, key: string) {
  const value = quality?.[key]
  if (Array.isArray(value)) return value.length
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>
    return Array.isArray(record.items) ? record.items.length : Object.keys(record).length
  }
  return 0
}

function recordNumber(value: unknown, key: string): number | null {
  if (!value || typeof value !== "object") return null
  const candidate = (value as Record<string, unknown>)[key]
  return typeof candidate === "number" ? candidate : null
}

function QualityPanel({ status, error, onRefresh }: {
  status: GtkStatus | null
  error: string
  onRefresh: () => void
}) {
  const run = status?.last_run ?? null
  const lastTime = run?.finished_at ?? run?.started_at ?? null
  const isOffline = !lastTime || Date.now() - new Date(lastTime).getTime() > 30 * 60 * 1000
  const quality = run?.quality ?? null
  const checks = [
    ["Локомотивы без инв. номера", countQuality(quality, "locomotives_without_inventory")],
    ["Вагоны без инв. номера", countQuality(quality, "carriages_without_inventory")],
    ["Необычный формат инв. номера", countQuality(quality, "locomotives_odd_inventory_format")],
    ["Дубли номеров вагонов", countQuality(quality, "carriages_reg_number_duplicate_groups")],
    ["Неактивные вагоны в составе", countQuality(quality, "inactive_carriages_in_open_trains")],
    ["Составы старше 30 дней", countQuality(quality, "open_trains_older_than_days")],
    ["Номер состава не совпадает", countQuality(quality, "train_number_locomotive_mismatches")],
  ] as const

  return (
    <section className={panelClass} aria-label="Состояние и качество данных GTK">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold text-gray-900 dark:text-white">Состояние данных GTK</h2>
            {isOffline ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-1 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-300">
                <AlertTriangle className="h-3.5 w-3.5" /> Нет связи с GTK
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                <CheckCircle className="h-3.5 w-3.5" /> Обновлено
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Последний запуск: {dateTime(lastTime)} · Статус: {run ? statusLabel(run.status) : "нет данных"}
            {status?.auto_sync_stopped ? " · Автосинхронизация остановлена после ошибок входа" : ""}
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onRefresh} className="gap-2">
          <RefreshCw className="h-4 w-4" /> Обновить
        </Button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-7">
        {checks.map(([label, count]) => (
          <div key={label} className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800/70">
            <p className="text-[11px] leading-4 text-gray-500 dark:text-gray-400">{label}</p>
            <p className={`mt-1 text-lg font-semibold ${count ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>{count}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function ConfirmDialog({ title, children, busy, onCancel, onConfirm }: {
  title: string
  children: React.ReactNode
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="gtk-confirm-title" className="w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-start justify-between gap-3">
          <h2 id="gtk-confirm-title" className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          <button type="button" aria-label="Закрыть" onClick={onCancel} disabled={busy} className="rounded p-1 text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"><X className="h-5 w-5" /></button>
        </div>
        <div className="mt-3 text-sm text-gray-600 dark:text-gray-300">{children}</div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" disabled={busy} onClick={onCancel}>Отмена</Button>
          <Button type="button" disabled={busy} onClick={onConfirm} className="gap-2">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            Подтвердить
          </Button>
        </div>
      </section>
    </div>
  )
}

export default function GtkPage() {
  const router = useRouter()
  const { profile, loading: authLoading } = useAuth()
  const role = profile?.role
  const canWrite = role === "admin" || role === "operator"
  const [tab, setTab] = useState<Tab>("locomotives")
  const [status, setStatus] = useState<GtkStatus | null>(null)
  const [statusError, setStatusError] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState("")
  const [page, setPage] = useState(0)
  const [locomotives, setLocomotives] = useState<PageResponse<GtkLocomotive>>({ items: [], total: 0 })
  const [carriages, setCarriages] = useState<GtkCarriage[]>([])
  const [trains, setTrains] = useState<PageResponse<GtkTrain>>({ items: [], total: 0 })
  const [carriageFilter, setCarriageFilter] = useState("all")
  const [activeFilter, setActiveFilter] = useState("all")
  const [trainFilter, setTrainFilter] = useState("open")
  const [openTrainId, setOpenTrainId] = useState<number | null>(null)
  const [trainDetails, setTrainDetails] = useState<Record<number, GtkTrainDetail>>({})
  const [trainDetailError, setTrainDetailError] = useState("")
  const [trainDetailLoading, setTrainDetailLoading] = useState(false)
  const [pendingLink, setPendingLink] = useState<PendingLink | null>(null)
  const [linkBusy, setLinkBusy] = useState(false)
  const [bulkPreview, setBulkPreview] = useState<GtkCreateAssetsResponse | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkReport, setBulkReport] = useState<GtkCreateAssetsResponse | null>(null)

  useEffect(() => {
    if (!authLoading && role === "master") router.replace("/dashboard/directories/assets")
  }, [authLoading, role, router])

  const loadStatus = useCallback(async () => {
    setStatusError("")
    try {
      setStatus(await api.gtk.status())
    } catch {
      setStatusError("Не удалось загрузить состояние GTK.")
    }
  }, [])

  const loadTabData = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      if (tab === "locomotives") {
        const response = await api.gtk.locomotives({
          q: query || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          sort_by: "gtk_id",
          sort_order: "asc",
        })
        setLocomotives(response)
      } else if (tab === "carriages") {
        const all: GtkCarriage[] = []
        let offset = 0
        let total = 0
        do {
          const response = await api.gtk.carriages({
            q: query || undefined,
            is_active: activeFilter === "active" ? true : activeFilter === "inactive" ? false : undefined,
            duplicate: carriageFilter === "duplicate" ? true : carriageFilter === "unique" ? false : undefined,
            in_train: carriageFilter === "in_train" ? true : undefined,
            limit: 1000,
            offset,
            sort_by: "gtk_id",
            sort_order: "asc",
          })
          all.push(...response.items)
          total = response.total
          offset += response.items.length
          if (!response.items.length) break
        } while (offset < total)
        setCarriages(all)
      } else {
        const response = await api.gtk.trains({
          q: query || undefined,
          is_open: trainFilter === "open" ? true : trainFilter === "closed" ? false : undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          sort_by: "gtk_id",
          sort_order: "asc",
        })
        setTrains(response)
      }
    } catch {
      setError("Не удалось загрузить данные. Попробуйте обновить страницу.")
    } finally {
      setLoading(false)
    }
  }, [activeFilter, carriageFilter, page, query, tab, trainFilter])

  useEffect(() => {
    if (!authLoading && role !== "master") void loadStatus()
  }, [authLoading, loadStatus, role])
  useEffect(() => {
    if (!authLoading && role !== "master") void loadTabData()
  }, [authLoading, loadTabData, role])

  const filteredCarriages = useMemo(() => carriages.filter((carriage) => {
    if (carriageFilter === "linked") return Boolean(carriage.linked_asset)
    if (carriageFilter === "unlinked") return !carriage.linked_asset
    return true
  }), [carriages, carriageFilter])
  const visibleCarriages = filteredCarriages.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const carriageTotal = filteredCarriages.length
  const total = tab === "locomotives" ? locomotives.total : tab === "carriages" ? carriageTotal : trains.total
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const quality = status?.last_run?.quality ?? null
  const staleTrainIds = new Set(qualityList(quality, "open_trains_older_than_days")
    .map((item) => recordNumber(item, "train_id")).filter((id): id is number => id !== null))
  const mismatchedTrainIds = new Set(qualityList(quality, "train_number_locomotive_mismatches")
    .map((item) => recordNumber(item, "train_id")).filter((id): id is number => id !== null))

  const refresh = () => {
    void loadStatus()
    void loadTabData()
  }

  const prepareLink = (row: GtkLocomotive | GtkCarriage, kind: PendingLink["kind"]) => {
    const candidate = row.suggestion.asset
    if (!candidate || !canWrite || !row.inventory_number?.trim()) return
    setPendingLink({
      gtkId: row.gtk_id,
      kind,
      name: row.name || `GTK ${row.gtk_id}`,
      assetId: candidate.id,
      assetName: `${candidate.name} · ${candidate.inv_number}`,
      expectedInventoryNumber: row.inventory_number,
    })
  }

  const confirmLink = async () => {
    if (!pendingLink) return
    setLinkBusy(true)
    setError("")
    try {
      await api.gtk.link({
        links: [{
          asset_id: pendingLink.assetId,
          gtk_id: pendingLink.gtkId,
          kind: pendingLink.kind,
          expected_inventory_number: pendingLink.expectedInventoryNumber,
        }],
      })
      setPendingLink(null)
      await loadTabData()
    } catch {
      setError("Не удалось сохранить привязку. Проверьте, не привязан ли объект уже.")
    } finally {
      setLinkBusy(false)
    }
  }

  const unlink = async (assetId: string) => {
    if (!canWrite || !window.confirm("Отвязать этот объект ОС от GTK?")) return
    setError("")
    try {
      await api.gtk.unlink(assetId)
      await loadTabData()
    } catch {
      setError("Не удалось отвязать объект GTK.")
    }
  }

  const startBulkPreview = async () => {
    setBulkBusy(true)
    setError("")
    try {
      setBulkPreview(await api.gtk.createCarriageAssets(true))
      setBulkReport(null)
    } catch {
      setError("Не удалось подготовить список вагонов для создания ОС.")
    } finally {
      setBulkBusy(false)
    }
  }

  const confirmBulkCreate = async () => {
    setBulkBusy(true)
    setError("")
    try {
      const report = await api.gtk.createCarriageAssets(false)
      setBulkReport(report)
      setBulkPreview(null)
      await loadTabData()
    } catch {
      setError("Не удалось создать ОС для вагонов.")
    } finally {
      setBulkBusy(false)
    }
  }

  const toggleTrain = async (trainId: number) => {
    if (openTrainId === trainId) {
      setOpenTrainId(null)
      return
    }
    setOpenTrainId(trainId)
    setTrainDetailError("")
    if (trainDetails[trainId]) return
    setTrainDetailLoading(true)
    try {
      const detail = await api.gtk.train(trainId)
      setTrainDetails((existing) => ({ ...existing, [trainId]: detail }))
    } catch {
      setTrainDetailError("Не удалось загрузить состав.")
    } finally {
      setTrainDetailLoading(false)
    }
  }

  if (authLoading || role === "master") {
    return <div className="p-8 text-sm text-gray-500">Загрузка…</div>
  }

  return (
    <div className="space-y-5 p-4 sm:p-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="h-5 w-5 text-blue-600" />
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Данные GTK</h1>
          </div>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Отдельный источник данных локомотивов, вагонов и составов.</p>
        </div>
      </header>

      <QualityPanel status={status} error={statusError} onRefresh={refresh} />

      <nav className="flex flex-wrap gap-2" aria-label="Разделы GTK">
        {([
          ["locomotives", "Локомотивы", Train],
          ["carriages", "Вагоны", Container],
          ["trains", "Составы", Radio],
        ] as const).map(([key, label, Icon]) => (
          <button key={key} type="button" onClick={() => { setTab(key); setPage(0); setError("") }}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium ${tab === key ? "bg-blue-600 text-white" : "border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"}`}>
            <Icon className="h-4 w-4" />{label}
          </button>
        ))}
      </nav>

      <section className={panelClass}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <label className="relative min-w-56 flex-1 sm:max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input value={query} onChange={(event) => { setQuery(event.target.value); setPage(0) }} className={`${inputClass} w-full pl-9`} placeholder="Поиск по названию, номеру или ID" />
          </label>
          {tab === "carriages" && (
            <div className="flex flex-wrap gap-2">
              <select aria-label="Фильтр вагонов" value={carriageFilter} onChange={(event) => { setCarriageFilter(event.target.value); setPage(0) }} className={selectClass}>
                <option value="all">Все вагоны</option>
                <option value="linked">Привязанные</option>
                <option value="unlinked">Не привязанные</option>
                <option value="duplicate">Дубликаты</option>
                <option value="unique">Без дубликатов</option>
                <option value="in_train">В составе</option>
              </select>
              <select aria-label="Активность вагонов" value={activeFilter} onChange={(event) => { setActiveFilter(event.target.value); setPage(0) }} className={selectClass}>
                <option value="all">Любой статус</option>
                <option value="active">Активные</option>
                <option value="inactive">Неактивные</option>
              </select>
              {canWrite && (
                <Button type="button" disabled={bulkBusy} onClick={() => void startBulkPreview()} className="gap-2">
                  {bulkBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Container className="h-4 w-4" />}
                  Создать ОС
                </Button>
              )}
            </div>
          )}
          {tab === "trains" && (
            <select aria-label="Статус составов" value={trainFilter} onChange={(event) => { setTrainFilter(event.target.value); setPage(0) }} className={selectClass}>
              <option value="open">Открытые</option>
              <option value="closed">Закрытые</option>
              <option value="all">Все</option>
            </select>
          )}
        </div>

        {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}
        {bulkReport && (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
            Создано: {bulkReport.created} · Пропущено: {bulkReport.skipped}
            {bulkReport.items.filter((item) => item.status === "skipped").length > 0 && (
              <ul className="mt-2 list-inside list-disc">
                {bulkReport.items.filter((item) => item.status === "skipped").map((item) => (
                  <li key={item.gtk_id}>GTK {item.gtk_id}: {skipReasonLabel(item.reason)}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            {tab === "locomotives" ? (
              <>
                <thead className="border-b border-gray-200 text-xs uppercase text-gray-500 dark:border-gray-800">
                  <tr>{["Название", "Модель", "Инвентарный номер", "Статус", "В составе", "Связанное ОС", "Предложение"].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {locomotives.items.map((row) => (
                    <tr key={row.gtk_id}>
                      <td className="px-3 py-3"><span className="font-medium text-gray-900 dark:text-white">{row.name || "—"}</span><span className="block text-xs text-gray-500">GTK {row.gtk_id}</span></td>
                      <td className="px-3 py-3">{row.model_name || "—"}</td>
                      <td className="px-3 py-3">{row.inventory_number || "—"}</td>
                      <td className="px-3 py-3">{row.is_active ? "Активен" : "Неактивен"}</td>
                      <td className="px-3 py-3">{row.in_train ? "Да" : "Нет"}</td>
                      <td className="px-3 py-3">{row.linked_asset ? <>{row.linked_asset.name}<span className="block text-xs text-gray-500">{row.linked_asset.inv_number}</span></> : "—"}</td>
                      <td className="px-3 py-3">
                        {row.linked_asset && canWrite ? (
                          <button type="button" onClick={() => void unlink(row.linked_asset!.id)} className="text-xs font-medium text-red-600 hover:underline">Отвязать</button>
                        ) : row.suggestion.level === "ambiguous" ? (
                          <div>
                            <span className="text-xs font-medium text-amber-600">Неоднозначно</span>
                            <p className="max-w-48 truncate text-xs text-gray-500">Кандидатов ОС: {row.suggestion.candidate_count}</p>
                          </div>
                        ) : row.suggestion.level === "high" && row.suggestion.asset ? (
                          <div>
                            <span className="text-xs font-medium text-emerald-600">Совпадает инв. №</span>
                            <p className="max-w-48 truncate text-xs text-gray-500">{row.suggestion.asset.name}</p>
                            {canWrite && <button type="button" onClick={() => prepareLink(row, "locomotive")} className="mt-1 text-xs font-semibold text-blue-600 hover:underline">Привязать</button>}
                          </div>
                        ) : <span className="text-xs text-gray-400">Нет предложения</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </>
            ) : tab === "carriages" ? (
              <>
                <thead className="border-b border-gray-200 text-xs uppercase text-gray-500 dark:border-gray-800">
                  <tr>{["Название", "Номер вагона", "Модель / инв. №", "Статус", "Состав", "Связанное ОС", "Предложение"].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {visibleCarriages.map((row) => (
                    <tr key={row.gtk_id}>
                      <td className="px-3 py-3"><span className="font-medium text-gray-900 dark:text-white">{row.name || "—"}</span><span className="block text-xs text-gray-500">GTK {row.gtk_id}</span></td>
                      <td className="px-3 py-3">{row.reg_number || "—"}{row.duplicate && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">Дубликат</span>}</td>
                      <td className="px-3 py-3">{row.model_name || "—"}<span className="block text-xs text-gray-500">{row.inventory_number || "Инв. № —"}</span></td>
                      <td className="px-3 py-3">{row.is_active ? "Активен" : <span className="text-red-600">Неактивен</span>}</td>
                      <td className="px-3 py-3">{row.in_train ? "В составе" : "—"}</td>
                      <td className="px-3 py-3">{row.linked_asset ? <>{row.linked_asset.name}<span className="block text-xs text-gray-500">{row.linked_asset.inv_number}</span>{canWrite && <button type="button" onClick={() => void unlink(row.linked_asset!.id)} className="mt-1 text-xs font-medium text-red-600 hover:underline">Отвязать</button>}</> : "—"}</td>
                      <td className="px-3 py-3">
                        {row.linked_asset ? (
                          <span className="text-xs text-gray-400">Уже привязан</span>
                        ) : row.suggestion.level === "ambiguous" ? (
                          <div>
                            <span className="text-xs font-medium text-amber-600">Неоднозначно</span>
                            <p className="max-w-48 truncate text-xs text-gray-500">Кандидатов ОС: {row.suggestion.candidate_count}</p>
                          </div>
                        ) : row.suggestion.level === "high" && row.suggestion.asset ? (
                          <div>
                            <span className="text-xs font-medium text-emerald-600">Совпадает инв. №</span>
                            <p className="max-w-48 truncate text-xs text-gray-500">{row.suggestion.asset.name}</p>
                            {canWrite && <button type="button" onClick={() => prepareLink(row, "carriage")} className="mt-1 text-xs font-semibold text-blue-600 hover:underline">Привязать</button>}
                          </div>
                        ) : <span className="text-xs text-gray-400">Нет предложения</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </>
            ) : (
              <>
                <thead className="border-b border-gray-200 text-xs uppercase text-gray-500 dark:border-gray-800">
                  <tr>{["Состав", "Основной локомотив", "Вагоны", "Добавлен", "Признаки", ""].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {trains.items.map((train) => {
                    const detail = trainDetails[train.gtk_id]
                    const mainLoco = detail?.locomotives.find((loco) => loco.is_main)
                    return (
                      <tr key={train.gtk_id} className="align-top">
                        <td colSpan={6} className="p-0">
                          <div className="grid grid-cols-6 items-center">
                            <div className="px-3 py-3 font-medium text-gray-900 dark:text-white">{train.number || train.title || `GTK ${train.gtk_id}`}<span className="block text-xs font-normal text-gray-500">GTK {train.gtk_id}</span></div>
                            <div className="px-3 py-3">{mainLoco ? `${mainLoco.name || "—"} · ${mainLoco.garage_number || "—"}` : "Откройте состав"}</div>
                            <div className="px-3 py-3">{detail ? detail.carriages.length : "—"}</div>
                            <div className="px-3 py-3 text-xs">{dateTime(train.begin_time)}</div>
                            <div className="px-3 py-3">
                              {staleTrainIds.has(train.gtk_id) && <span className="mr-1 inline-block rounded bg-amber-100 px-2 py-1 text-xs text-amber-700">Старше 30 дней</span>}
                              {mismatchedTrainIds.has(train.gtk_id) && <span className="inline-block rounded bg-red-100 px-2 py-1 text-xs text-red-700">Номер не совпадает</span>}
                            </div>
                            <div className="px-3 py-3">
                              <button type="button" onClick={() => void toggleTrain(train.gtk_id)} aria-expanded={openTrainId === train.gtk_id} className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:underline">
                                {openTrainId === train.gtk_id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                {openTrainId === train.gtk_id ? "Скрыть" : "Открыть"}
                              </button>
                            </div>
                          </div>
                          {openTrainId === train.gtk_id && (
                            <div className="border-t border-gray-100 bg-gray-50 px-4 py-3 dark:border-gray-800 dark:bg-gray-800/40">
                              {trainDetailLoading && <p className="text-xs text-gray-500">Загрузка состава…</p>}
                              {trainDetailError && <p role="alert" className="text-xs text-red-600">{trainDetailError}</p>}
                              {detail && (
                                <div className="grid gap-4 md:grid-cols-2">
                                  <div>
                                    <p className="mb-2 text-xs font-semibold text-gray-600 dark:text-gray-300">Локомотивы</p>
                                    {detail.locomotives.length ? detail.locomotives.map((loco) => (
                                      <p key={loco.gtk_id} className="text-xs text-gray-700 dark:text-gray-300">
                                        {loco.is_main ? "Основной · " : ""}{loco.name || "—"} · {loco.garage_number || "—"}
                                      </p>
                                    )) : <p className="text-xs text-gray-500">Нет локомотивов</p>}
                                  </div>
                                  <div>
                                    <p className="mb-2 text-xs font-semibold text-gray-600 dark:text-gray-300">Вагоны ({detail.carriages.length})</p>
                                    {detail.carriages.length ? detail.carriages.map((carriage) => (
                                      <p key={carriage.gtk_id} className="text-xs text-gray-700 dark:text-gray-300">{carriage.ord}. {carriage.name || "—"} · {carriage.reg_number || "—"}</p>
                                    )) : <p className="text-xs text-gray-500">Нет вагонов</p>}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </>
            )}
          </table>
        </div>

        {!loading && total === 0 && <p className="py-10 text-center text-sm text-gray-500">Нет данных для отображения.</p>}
        {loading && <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" />Загрузка данных…</div>}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-gray-800">
          <span>Записей: {total}</span>
          <div className="flex items-center gap-2">
            <button type="button" disabled={page === 0 || loading} onClick={() => setPage((value) => Math.max(0, value - 1))} className="rounded border border-gray-200 px-3 py-1.5 disabled:opacity-40 dark:border-gray-700">Назад</button>
            <span>{page + 1} / {totalPages}</span>
            <button type="button" disabled={page + 1 >= totalPages || loading} onClick={() => setPage((value) => Math.min(totalPages - 1, value + 1))} className="rounded border border-gray-200 px-3 py-1.5 disabled:opacity-40 dark:border-gray-700">Далее</button>
          </div>
        </div>
      </section>

      {pendingLink && (
        <ConfirmDialog title="Подтвердить привязку" busy={linkBusy} onCancel={() => setPendingLink(null)} onConfirm={() => void confirmLink()}>
          <p>Привязать GTK объект <b>{pendingLink.name}</b> (ID {pendingLink.gtkId}) к ОС <b>{pendingLink.assetName}</b> по инв. № <b>{pendingLink.expectedInventoryNumber}</b>?</p>
          <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">Связь сохранится только после подтверждения и повторной проверки инвентарного номера.</p>
        </ConfirmDialog>
      )}

      {bulkPreview && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4">
          <section role="dialog" aria-modal="true" aria-labelledby="gtk-bulk-title" className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
            <header className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-gray-800">
              <div><h2 id="gtk-bulk-title" className="font-semibold text-gray-900 dark:text-white">Проверка создания ОС</h2><p className="mt-1 text-xs text-gray-500">Сначала показан предварительный результат. Записи пока не созданы.</p></div>
              <button type="button" aria-label="Закрыть" onClick={() => setBulkPreview(null)} disabled={bulkBusy} className="rounded p-1 text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"><X className="h-5 w-5" /></button>
            </header>
            <div className="flex-1 overflow-y-auto p-5">
              <p className="mb-3 text-sm text-gray-700 dark:text-gray-300">Будет создано: <b>{bulkPreview.would_create}</b> · Пропущено: <b>{bulkPreview.skipped}</b></p>
              <ul className="space-y-2 text-xs">
                {bulkPreview.items.map((item) => (
                  <li key={item.gtk_id} className="flex flex-wrap justify-between gap-2 rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800">
                    <span>GTK {item.gtk_id} · {item.asset?.name || "—"} · инв. № {item.asset?.inv_number || "—"}</span>
                    <span className={item.status === "skipped" ? "text-amber-700 dark:text-amber-300" : "text-emerald-700 dark:text-emerald-300"}>
                      {item.status === "skipped" ? skipReasonLabel(item.reason) : "Будет создано"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <footer className="flex justify-end gap-2 border-t border-gray-200 px-5 py-4 dark:border-gray-800">
              <Button type="button" variant="outline" disabled={bulkBusy} onClick={() => setBulkPreview(null)}>Отмена</Button>
              <Button type="button" disabled={bulkBusy || bulkPreview.would_create === 0} onClick={() => void confirmBulkCreate()} className="gap-2">
                {bulkBusy && <Loader2 className="h-4 w-4 animate-spin" />}Создать {bulkPreview.would_create} ОС
              </Button>
            </footer>
          </section>
        </div>
      )}
    </div>
  )
}
