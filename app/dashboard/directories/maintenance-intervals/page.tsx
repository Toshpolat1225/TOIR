"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { api, type MaintenanceInterval, type WorkType } from "@/lib/api"
import {
  AlertTriangle,
  CheckCircle,
  Info,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Settings,
  Trash2,
  Wrench,
  X,
} from "@/components/ui/icons"

const ASSET_TYPE_OPTIONS = [
  { value: "locomotive", label: "Локомотив" },
  { value: "diesel", label: "Тепловоз" },
  { value: "wagon", label: "Вагон" },
]

type IntervalForm = {
  work_type_id: string | null
  code: string
  name: string
  interval_km: string
  interval_days: string
  asset_types: string[]
  warn_percent: string
  is_active: boolean
}

const emptyForm: IntervalForm = {
  work_type_id: null,
  code: "",
  name: "",
  interval_km: "",
  interval_days: "",
  asset_types: ["locomotive", "diesel"],
  warn_percent: "10",
  is_active: true,
}

function toForm(interval: MaintenanceInterval): IntervalForm {
  return {
    work_type_id: interval.work_type_id,
    code: interval.code,
    name: interval.name,
    interval_km: interval.interval_km?.toString() ?? "",
    interval_days: interval.interval_days?.toString() ?? "",
    asset_types: [...interval.asset_types],
    warn_percent: interval.warn_percent.toString(),
    is_active: interval.is_active,
  }
}

export default function MaintenanceIntervalsPage() {
  const [intervals, setIntervals] = useState<MaintenanceInterval[]>([])
  const [workTypes, setWorkTypes] = useState<WorkType[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [formData, setFormData] = useState<IntervalForm>(emptyForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const workTypeNames = useMemo(
    () => new Map(workTypes.map((workType) => [workType.id, `${workType.code} — ${workType.name}`])),
    [workTypes]
  )

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [intervalResponse, workTypeResponse] = await Promise.all([
        api.maintenanceIntervals.list({
          limit: 1000,
          sort_by: "interval_km",
          sort_order: "asc",
        }),
        api.workTypes.list({ limit: 1000, sort_by: "sort_order", sort_order: "asc" }),
      ])
      setIntervals(intervalResponse.items)
      setWorkTypes(workTypeResponse.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить интервалы")
      setIntervals([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  const handleEdit = (interval: MaintenanceInterval) => {
    setEditingId(interval.id)
    setFormData(toForm(interval))
    setIsCreating(false)
    setError("")
  }

  const handleCreate = () => {
    setIsCreating(true)
    setEditingId(null)
    setFormData({ ...emptyForm, asset_types: [...emptyForm.asset_types] })
    setError("")
  }

  const handleCancel = () => {
    setEditingId(null)
    setIsCreating(false)
    setFormData(emptyForm)
    setError("")
  }

  const handleSave = async () => {
    const code = formData.code.trim()
    const name = formData.name.trim()
    const km = formData.interval_km.trim() ? Number(formData.interval_km) : null
    const days = formData.interval_days.trim() ? Number(formData.interval_days) : null
    if (!code || !name) {
      setError("Укажите код и название интервала")
      return
    }
    if (km === null && days === null) {
      setError("Укажите пробег и/или срок в днях")
      return
    }
    if ((km !== null && !Number.isFinite(km)) || (days !== null && !Number.isInteger(days))) {
      setError("Значения интервала должны быть корректными числами")
      return
    }

    setSaving(true)
    setError("")
    const payload = {
      work_type_id: formData.work_type_id,
      code,
      name,
      interval_km: km,
      interval_days: days,
      asset_types: formData.asset_types,
      warn_percent: Number(formData.warn_percent),
      is_active: formData.is_active,
    }

    try {
      if (isCreating) {
        await api.maintenanceIntervals.create(payload)
      } else if (editingId) {
        await api.maintenanceIntervals.update(editingId, payload)
      }
      handleCancel()
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить интервал")
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (interval: MaintenanceInterval) => {
    if (!confirm(`Удалить интервал "${interval.code}"?`)) return
    setError("")
    try {
      await api.maintenanceIntervals.remove(interval.id)
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить интервал")
    }
  }

  const handleToggleActive = async (interval: MaintenanceInterval) => {
    setError("")
    try {
      const updated = await api.maintenanceIntervals.update(interval.id, {
        is_active: !interval.is_active,
      })
      setIntervals((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить статус интервала")
    }
  }

  const form = (
    <div className="rounded-2xl border-2 border-blue-500 bg-white p-6 dark:bg-gray-900">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white">
        {isCreating ? <Plus className="h-5 w-5 text-blue-500" /> : <Pencil className="h-5 w-5 text-blue-500" />}
        {isCreating ? "Новый интервал ТО" : "Редактировать интервал"}
      </h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
          Код *
          <input
            value={formData.code}
            onChange={(event) => setFormData({ ...formData, code: event.target.value })}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal dark:border-gray-600 dark:bg-gray-800"
          />
        </label>
        <label className="space-y-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
          Название *
          <input
            value={formData.name}
            onChange={(event) => setFormData({ ...formData, name: event.target.value })}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal dark:border-gray-600 dark:bg-gray-800"
          />
        </label>
        <label className="space-y-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
          Вид работ
          <select
            value={formData.work_type_id ?? ""}
            onChange={(event) =>
              setFormData({ ...formData, work_type_id: event.target.value || null })
            }
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal dark:border-gray-600 dark:bg-gray-800"
          >
            <option value="">Не связан</option>
            {workTypes.map((workType) => (
              <option key={workType.id} value={workType.id}>
                {workType.code} — {workType.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
          Интервал (км)
          <input
            type="number"
            min="0"
            step="0.01"
            value={formData.interval_km}
            onChange={(event) => setFormData({ ...formData, interval_km: event.target.value })}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal dark:border-gray-600 dark:bg-gray-800"
          />
        </label>
        <label className="space-y-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
          Интервал (дней)
          <input
            type="number"
            min="0"
            step="1"
            value={formData.interval_days}
            onChange={(event) => setFormData({ ...formData, interval_days: event.target.value })}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal dark:border-gray-600 dark:bg-gray-800"
          />
        </label>
        <label className="space-y-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
          Предупреждение (%)
          <input
            type="number"
            min="0"
            step="0.01"
            value={formData.warn_percent}
            onChange={(event) => setFormData({ ...formData, warn_percent: event.target.value })}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal dark:border-gray-600 dark:bg-gray-800"
          />
        </label>
        <fieldset className="space-y-2 md:col-span-2">
          <legend className="text-xs font-semibold text-gray-700 dark:text-gray-300">Типы ОС</legend>
          <div className="flex flex-wrap gap-3">
            {ASSET_TYPE_OPTIONS.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={formData.asset_types.includes(option.value)}
                  onChange={(event) => {
                    const assetTypes = event.target.checked
                      ? [...formData.asset_types, option.value]
                      : formData.asset_types.filter((value) => value !== option.value)
                    setFormData({ ...formData, asset_types: assetTypes })
                  }}
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex items-center gap-2 self-end pb-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            checked={formData.is_active}
            onChange={(event) => setFormData({ ...formData, is_active: event.target.checked })}
          />
          Активен
        </label>
      </div>
      <div className="mt-5 flex gap-3">
        <button
          onClick={() => void handleSave()}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "Сохранение..." : "Сохранить"}
        </button>
        <button
          onClick={handleCancel}
          className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          <X className="h-4 w-4" />
          Отмена
        </button>
      </div>
    </div>
  )

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
            <Settings className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Интервалы ТО и ремонтов</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Настройки интервалов по пробегу и/или сроку эксплуатации
            </p>
          </div>
        </div>
        <button
          onClick={handleCreate}
          disabled={isCreating}
          className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          Добавить интервал
        </button>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        Укажите хотя бы один интервал: по пробегу, по дням или оба. Значения не создаются автоматически.
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      )}

      {(isCreating || editingId) && form}

      <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <div className="flex items-center gap-3 border-b border-gray-200 px-6 py-4 dark:border-gray-800">
          <Wrench className="h-4 w-4 text-amber-500" />
          <h2 className="text-sm font-bold text-gray-900 dark:text-white">Настроенные интервалы</h2>
          <span className="text-xs text-gray-400">· {intervals.length} записей</span>
        </div>
        {loading ? (
          <div className="flex h-40 items-center justify-center gap-2 text-sm text-gray-400">
            <RefreshCw className="h-5 w-5 animate-spin" />
            Загрузка...
          </div>
        ) : intervals.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-500">
            Нет настроенных интервалов. Их значения задаются пользователем.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-800">
                  {["Статус", "Код", "Название", "Вид работ", "Интервал", "Типы ОС", "Предупреждение", "Действия"].map((heading) => (
                    <th key={heading} className="whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {intervals.map((interval) => (
                  <tr key={interval.id} className={!interval.is_active ? "opacity-60" : ""}>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => void handleToggleActive(interval)}
                        className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium ${
                          interval.is_active
                            ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400"
                            : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                        }`}
                      >
                        {interval.is_active ? <CheckCircle className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                        {interval.is_active ? "Активен" : "Отключен"}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-sm font-bold text-blue-600 dark:text-blue-400">{interval.code}</td>
                    <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">{interval.name}</td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {interval.work_type_id ? workTypeNames.get(interval.work_type_id) ?? "—" : "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                      {interval.interval_km !== null ? `${Number(interval.interval_km).toLocaleString()} км` : "—"}
                      {interval.interval_days !== null ? ` / ${interval.interval_days} дн.` : ""}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {interval.asset_types.map((assetType) =>
                        ASSET_TYPE_OPTIONS.find((option) => option.value === assetType)?.label ?? assetType
                      ).join(", ") || "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{interval.warn_percent}%</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button onClick={() => handleEdit(interval)} title="Редактировать" className="rounded-lg bg-blue-100 p-1.5 text-blue-700 hover:bg-blue-200 dark:bg-blue-950 dark:text-blue-400">
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button onClick={() => void handleDelete(interval)} title="Удалить" className="rounded-lg bg-red-100 p-1.5 text-red-700 hover:bg-red-200 dark:bg-red-950 dark:text-red-400">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
