"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api, type DataMigrationBatch, type DataMigrationItem } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"

const PAGE_SIZE = 50
const FIELD_LABELS: Record<string, string> = { last_maint_date: "Дата последнего обслуживания" }
const TYPE_LABELS: Record<string, string> = {
  wagon: "Вагон", locomotive: "Локомотив", diesel: "Тепловоз", platform: "Платформа", tank_car: "Цистерна", special_self_propelled: "Спецтехника",
}
const selectCls = "h-9 rounded-md border border-input bg-transparent px-3 text-sm dark:bg-input/30"

function fmtDate(value: string | null): string {
  if (!value) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : value
}
function fmtDateTime(value: string): string {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

type SortKey = "inv_number" | "serial_number" | "section_name" | "old_value" | "new_value" | "raw_value" | "status" | "updated_at"

export default function MigrationPage() {
  const { hasPermission } = useAuth()
  const canView = hasPermission("data_migration.view")
  const canManage = hasPermission("data_migration.manage")
  const [batches, setBatches] = useState<DataMigrationBatch[] | null>(null)
  const [batchError, setBatchError] = useState<string | null>(null)
  const [active, setActive] = useState<DataMigrationBatch | null>(null)

  const loadBatches = useCallback(async () => {
    setBatchError(null)
    try {
      const rows = await api.dataMigrations.batches()
      setBatches(rows)
      setActive((current) => (current ? rows.find((b) => b.id === current.id) ?? null : null))
    } catch (cause) {
      setBatches(null)
      setBatchError(cause instanceof Error ? cause.message : "Не удалось загрузить партии")
    }
  }, [])
  useEffect(() => { if (canView) void loadBatches() }, [canView, loadBatches])

  const revertBatch = async (batch: DataMigrationBatch) => {
    if (!window.confirm(`Откатить всю партию «${batch.name}»?\nЗначения вернутся к тому, что было до миграции. Значения, изменённые вручную после миграции, не будут затронуты.`)) return
    try {
      const result = await api.dataMigrations.revertBatch(batch.id)
      window.alert(`Откатано: ${result.reverted}. Пропущено (изменены вручную): ${result.skipped_changed_elsewhere}. Уже были откачены: ${result.already_reverted}.`)
      await loadBatches()
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : "Не удалось откатить партию")
    }
  }

  if (!canView) {
    return <div className="p-8 text-sm text-gray-500" data-testid="migration-forbidden">У вас нет доступа к журналу миграции данных.</div>
  }

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] space-y-6 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950" data-testid="migration-page">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Миграция данных</h1>
        <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
          Данные, перенесённые в систему из файлов Excel: можно просмотреть, исправить или откатить к прежнему значению.
        </p>
      </div>

      {batchError && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <span>{batchError}</span>
          <Button variant="outline" size="sm" onClick={() => void loadBatches()}>Повторить</Button>
        </div>
      )}
      {!batches && !batchError && <p className="text-sm text-gray-500">Загрузка…</p>}
      {batches && batches.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-gray-700">
          Миграций пока нет. Здесь появятся партии после импорта данных из файлов.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(batches ?? []).map((b) => {
          const selected = active?.id === b.id
          return (
            <div key={b.id} data-testid="migration-batch"
              className={`rounded-xl border bg-white p-4 transition-colors dark:bg-gray-900 ${selected ? "border-blue-400 ring-2 ring-blue-200 dark:ring-blue-900" : "border-gray-200 dark:border-gray-800"}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate font-semibold text-gray-900 dark:text-white" title={b.name}>{b.name}</h3>
                  <p className="mt-0.5 truncate text-xs text-gray-500" title={b.source_file}>Файл: {b.source_file}</p>
                  <p className="text-xs text-gray-500">Поле: {FIELD_LABELS[b.field] ?? b.field}</p>
                  <p className="text-xs text-gray-500">Дата импорта: {fmtDateTime(b.created_at)}</p>
                </div>
                <Badge variant="outline">{b.total}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">Применено: {b.applied}</span>
                <span className="rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300">Откачено: {b.reverted}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant={selected ? "default" : "outline"} onClick={() => setActive(selected ? null : b)}>{selected ? "Скрыть" : "Открыть"}</Button>
                {canManage && b.applied > 0 && <Button size="sm" variant="outline" onClick={() => void revertBatch(b)}>Откатить партию</Button>}
              </div>
            </div>
          )
        })}
      </div>

      {active && <BatchItems key={active.id} batch={active} canManage={canManage} onChanged={loadBatches} />}
    </div>
  )
}

function BatchItems({ batch, canManage, onChanged }: { batch: DataMigrationBatch; canManage: boolean; onChanged: () => Promise<void> }) {
  const [rows, setRows] = useState<DataMigrationItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [q, setQ] = useState("")
  const [statusFilter, setStatusFilter] = useState<"" | "applied" | "reverted">("")
  const [sortBy, setSortBy] = useState<SortKey>("inv_number")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<DataMigrationItem | null>(null)
  const requestId = useRef(0)

  const load = useCallback(async () => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const result = await api.dataMigrations.items(batch.id, {
        limit: PAGE_SIZE, offset: page * PAGE_SIZE, q: q.trim(), status: statusFilter || undefined, sort_by: sortBy, sort_dir: sortDir,
      })
      if (id !== requestId.current) return // an older answer must not overwrite a newer one
      setRows(result.items)
      setTotal(result.total)
    } catch (cause) {
      if (id !== requestId.current) return
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить данные")
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [batch.id, page, q, statusFilter, sortBy, sortDir])
  useEffect(() => { const t = window.setTimeout(() => void load(), q ? 250 : 0); return () => window.clearTimeout(t) }, [load, q])

  const sortHeader = (key: SortKey, label: string) => (
    <button type="button" className="inline-flex items-center gap-1 font-semibold hover:text-blue-600"
      onClick={() => { if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc")); else { setSortBy(key); setSortDir("asc") }; setPage(0) }}>
      {label}{sortBy === key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
    </button>
  )

  const revert = async (item: DataMigrationItem) => {
    if (!window.confirm(`Откатить значение для ${item.inv_number ?? "—"}?\nБыло до миграции: ${fmtDate(item.old_value)}.`)) return
    try {
      await api.dataMigrations.revert(item.id)
      await Promise.all([load(), onChanged()])
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : "Не удалось откатить")
    }
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const changedElsewhere = useMemo(() => rows.filter((r) => r.status === "applied" && r.current_value !== r.new_value).length, [rows])

  return (
    <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900" data-testid="migration-items">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">{batch.name}</h2>
        <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(0) }} placeholder="Поиск: инв. №, зав. №, исходный текст…" className="h-9 w-72" aria-label="Поиск" />
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value as "" | "applied" | "reverted"); setPage(0) }} className={selectCls} aria-label="Статус">
          <option value="">Все статусы</option>
          <option value="applied">Применено</option>
          <option value="reverted">Откачено</option>
        </select>
        <span className="ml-auto text-xs text-gray-500">Найдено: {total}</span>
      </div>
      {changedElsewhere > 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">На этой странице {changedElsewhere} знач. изменены вне миграции: их нельзя править отсюда.</p>
      )}

      {error && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <span>{error}</span><Button variant="outline" size="sm" onClick={() => void load()}>Повторить</Button>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500 dark:bg-gray-800/60">
            <tr>
              <th className="p-2">{sortHeader("inv_number", "Инв. №")}</th>
              <th className="p-2">{sortHeader("serial_number", "Зав. №")}</th>
              <th className="p-2">Название</th>
              <th className="p-2">{sortHeader("section_name", "Участок")}</th>
              <th className="p-2">{sortHeader("old_value", "Было")}</th>
              <th className="p-2">{sortHeader("new_value", "Стало")}</th>
              <th className="p-2">Сейчас в карточке</th>
              <th className="p-2">{sortHeader("raw_value", "Исходный текст")}</th>
              <th className="p-2">{sortHeader("status", "Статус")}</th>
              {canManage && <th className="p-2 text-right">Действия</th>}
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 && <tr><td colSpan={10} className="p-6 text-center text-gray-500">Загрузка…</td></tr>}
            {!loading && !error && rows.length === 0 && <tr><td colSpan={10} className="p-6 text-center text-gray-500">Ничего не найдено</td></tr>}
            {rows.map((r) => {
              const drift = r.status === "applied" && r.current_value !== r.new_value
              return (
                <tr key={r.id} className="border-t border-gray-100 dark:border-gray-800" data-testid="migration-row">
                  <td className="p-2 font-medium tabular-nums">{r.inv_number ?? "—"}</td>
                  <td className="p-2 tabular-nums">{r.serial_number ?? "—"}</td>
                  <td className="p-2">{r.asset_name ?? "—"} <span className="text-xs text-gray-400">{TYPE_LABELS[r.asset_type ?? ""] ?? ""}</span></td>
                  <td className="p-2">{r.section_name ?? "—"}</td>
                  <td className="p-2 tabular-nums">{fmtDate(r.old_value)}</td>
                  <td className="p-2 font-semibold tabular-nums">{fmtDate(r.new_value)}</td>
                  <td className={`p-2 tabular-nums ${drift ? "font-semibold text-amber-700 dark:text-amber-400" : ""}`} title={drift ? "Изменено вне миграции" : undefined}>{fmtDate(r.current_value)}</td>
                  <td className="p-2 text-gray-500">{r.raw_value ?? "—"}</td>
                  <td className="p-2">
                    {r.status === "applied"
                      ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">Применено</span>
                      : <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300">Откачено</span>}
                  </td>
                  {canManage && (
                    <td className="p-2 text-right whitespace-nowrap">
                      <Button size="sm" variant="outline" disabled={r.status !== "applied" || drift} onClick={() => setEditing(r)} className="mr-2">Изменить</Button>
                      <Button size="sm" variant="outline" disabled={r.status !== "applied" || drift} onClick={() => void revert(r)}>Откатить</Button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-xs text-gray-500">Страница {page + 1} из {pages}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>Назад</Button>
          <Button size="sm" variant="outline" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>Вперёд</Button>
        </div>
      </div>

      {editing && <EditDialog item={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await Promise.all([load(), onChanged()]) }} />}
    </section>
  )
}

function EditDialog({ item, onClose, onSaved }: { item: DataMigrationItem; onClose: () => void; onSaved: () => Promise<void> }) {
  const [value, setValue] = useState(item.new_value ?? "")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const today = new Date().toISOString().slice(0, 10)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])
  const save = async () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) { setError("Укажите дату полностью."); return }
    setBusy(true)
    setError(null)
    try {
      await api.dataMigrations.update(item.id, value)
      await onSaved()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить")
      setBusy(false)
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose} role="dialog" aria-modal="true" data-testid="migration-edit">
      <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl dark:bg-gray-900" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-gray-900 dark:text-white">Изменить значение</h3>
        <p className="mt-1 text-xs text-gray-500">Инв. № {item.inv_number ?? "—"} · исходный текст: {item.raw_value ?? "—"}</p>
        <label className="mt-4 block text-xs font-medium text-gray-600 dark:text-gray-300">Дата последнего обслуживания</label>
        <Input type="date" max={today} value={value} onChange={(e) => setValue(e.target.value)} className="mt-1" data-testid="migration-date" />
        {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={busy}>Отмена</Button>
          <Button onClick={() => void save()} disabled={busy}>{busy ? "Сохранение…" : "Сохранить"}</Button>
        </div>
      </div>
    </div>
  )
}
