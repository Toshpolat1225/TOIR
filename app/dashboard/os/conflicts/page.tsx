"use client"

import { useCallback, useEffect, useState } from "react"
import { api, type AssetFieldChange } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"

const FIELD_LABELS: Record<string, string> = {
  asset_type: "Тип",
  model_id: "Модель",
  number: "Номер",
  serial_number: "Серийный номер",
  inv_number: "Инвентарный номер",
  accounting_inv_number: "Бухгалтерский инв. номер",
  commissioned_at: "Дата ввода в эксплуатацию",
  year_built: "Год постройки",
  org_unit_id: "Участок",
  decommissioned_at: "Дата списания",
}

const SOURCE_LABELS: Record<string, string> = {
  wialon: "Wialon",
  gtk: "GTK",
  vesavoy: "Весовой",
  onec: "1С",
}
const CONFLICT_PAGE_SIZE = 50

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—"
  return typeof value === "object" ? JSON.stringify(value) ?? String(value) : String(value)
}

export default function AssetConflictsPage() {
  const { profile, loading: authLoading, hasPermission } = useAuth()
  const canManage =
    (profile?.role === "admin" || profile?.role === "operator") &&
    hasPermission("asset_conflicts.manage")
  const [items, setItems] = useState<AssetFieldChange[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [busyId, setBusyId] = useState<number | null>(null)
  const load = useCallback(async () => {
    if (authLoading) {
      return <div className="p-8 text-sm text-gray-500">Загрузка...</div>
    }
    if (!canManage) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError("")
    try {
      const response = await api.assetConflicts.list({ status: "pending", limit: CONFLICT_PAGE_SIZE, offset })
      setItems(response.items)
      setTotal(response.total)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить конфликты.")
    } finally {
      setLoading(false)
    }
  }, [canManage, offset])

  useEffect(() => { void load() }, [load])

  const resolve = async (item: AssetFieldChange, action: "accept" | "reject") => {
    const actionLabel = action === "accept" ? "принять" : "отклонить"
    if (!window.confirm(`Вы уверены, что хотите ${actionLabel} это предложение?`)) return
    setBusyId(item.id)
    setError("")
    try {
      if (action === "accept") await api.assetConflicts.accept(item.id)
      else await api.assetConflicts.reject(item.id)
      await load()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Не удалось обработать конфликт.")
    } finally {
      setBusyId(null)
    }
  }

  if (!canManage) {
    return <div className="p-8 text-sm text-gray-600 dark:text-gray-300">Нет доступа к этой странице.</div>
  }

  return (
    <div className="space-y-6 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Конфликты данных</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Предложения источников для паспорта основных средств</p>
        </div>
        <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить</Button>
      </header>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</p>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500 dark:bg-gray-800 dark:text-gray-400">
            <tr>
              <th className="px-4 py-3">Поле</th>
              <th className="px-4 py-3">Текущее значение</th>
              <th className="px-4 py-3">Предложено</th>
              <th className="px-4 py-3">Источник</th>
              <th className="px-4 py-3">Дата</th>
              <th className="px-4 py-3">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {loading ? (
              <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={6}>Загрузка конфликтов...</td></tr>
            ) : items.length === 0 ? (
              <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={6}>Ожидающих конфликтов нет.</td></tr>
            ) : items.map((item) => (
              <tr key={item.id} className="align-top">
                <td className="px-4 py-3">
                  <span className="font-medium text-gray-900 dark:text-white">{FIELD_LABELS[item.field] || item.field}</span>
                  <span className="mt-1 block max-w-48 truncate text-xs text-gray-400" title={item.asset_id}>{item.asset_id}</span>
                </td>
                <td className="max-w-64 break-words px-4 py-3 text-gray-600 dark:text-gray-300">{displayValue(item.old_value)}</td>
                <td className="max-w-64 break-words px-4 py-3 font-medium text-gray-900 dark:text-white">{displayValue(item.new_value)}</td>
                <td className="px-4 py-3">{SOURCE_LABELS[item.source] || item.source}</td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-500">{new Date(item.created_at).toLocaleString("ru-RU")}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => void resolve(item, "accept")} disabled={busyId === item.id}>Принять</Button>
                    <Button size="sm" variant="outline" onClick={() => void resolve(item, "reject")} disabled={busyId === item.id}>Отклонить</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>Всего: {total}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setOffset((value) => Math.max(0, value - CONFLICT_PAGE_SIZE))} disabled={loading || offset === 0}>Назад</Button>
          <Button size="sm" variant="outline" onClick={() => setOffset((value) => value + CONFLICT_PAGE_SIZE)} disabled={loading || offset + CONFLICT_PAGE_SIZE >= total}>Далее</Button>
        </div>
      </div>
    </div>
  )
}
