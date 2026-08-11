"use client"

import { useState, useEffect, useCallback } from "react"
import { supabase } from "@/lib/supabase"
import {
  Wrench, Plus, Pencil, Trash2, Save, X, AlertTriangle,
  CheckCircle, Settings, Info, RefreshCw
} from "lucide-react"

type MaintenanceInterval = {
  id: string
  code: string
  name: string
  interval_km: number
  interval_days: number | null
  asset_types: string[]
  description: string | null
  is_active: boolean
  created_at: string
}

const ASSET_TYPE_OPTIONS = [
  { value: "locomotive", label: "Локомотив" },
  { value: "diesel", label: "Тепловоз" },
]

export default function MaintenanceIntervalsPage() {
  const [intervals, setIntervals] = useState<MaintenanceInterval[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [formData, setFormData] = useState<Partial<MaintenanceInterval>>({})
  const [saving, setSaving] = useState(false)

  const fetchIntervals = useCallback(async () => {
    setLoading(true)
    const { data, error } = await supabase
      .from("maintenance_intervals")
      .select("*")
      .order("interval_km", { ascending: true })

    if (!error && data) {
      setIntervals(data)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchIntervals()
  }, [fetchIntervals])

  const handleEdit = (interval: MaintenanceInterval) => {
    setEditingId(interval.id)
    setFormData(interval)
    setIsCreating(false)
  }

  const handleCreate = () => {
    setIsCreating(true)
    setEditingId(null)
    setFormData({
      code: "",
      name: "",
      interval_km: 90,
      interval_days: null,
      asset_types: ["locomotive", "diesel"],
      description: "",
      is_active: true,
    })
  }

  const handleCancel = () => {
    setEditingId(null)
    setIsCreating(false)
    setFormData({})
  }

  const handleSave = async () => {
    if (!formData.code || !formData.name || !formData.interval_km) {
      alert("Заполните обязательные поля: Код, Название, Интервал (км)")
      return
    }

    setSaving(true)

    if (isCreating) {
      const { error } = await supabase
        .from("maintenance_intervals")
        .insert({
          code: formData.code,
          name: formData.name,
          interval_km: formData.interval_km,
          interval_days: formData.interval_days || null,
          asset_types: formData.asset_types || ["locomotive", "diesel"],
          description: formData.description || null,
          is_active: formData.is_active ?? true,
        })

      if (error) {
        alert(`Ошибка: ${error.message}`)
      } else {
        await fetchIntervals()
        handleCancel()
      }
    } else if (editingId) {
      const { error } = await supabase
        .from("maintenance_intervals")
        .update({
          code: formData.code,
          name: formData.name,
          interval_km: formData.interval_km,
          interval_days: formData.interval_days || null,
          asset_types: formData.asset_types || ["locomotive", "diesel"],
          description: formData.description || null,
          is_active: formData.is_active ?? true,
        })
        .eq("id", editingId)

      if (error) {
        alert(`Ошибка: ${error.message}`)
      } else {
        await fetchIntervals()
        handleCancel()
      }
    }

    setSaving(false)
  }

  const handleDelete = async (id: string, code: string) => {
    if (!confirm(`Удалить интервал "${code}"?`)) return

    const { error } = await supabase
      .from("maintenance_intervals")
      .delete()
      .eq("id", id)

    if (error) {
      alert(`Ошибка: ${error.message}`)
    } else {
      await fetchIntervals()
    }
  }

  const handleToggleActive = async (id: string, currentState: boolean) => {
    const { error } = await supabase
      .from("maintenance_intervals")
      .update({ is_active: !currentState })
      .eq("id", id)

    if (!error) {
      setIntervals(prev =>
        prev.map(i => (i.id === id ? { ...i, is_active: !currentState } : i))
      )
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-gray-400">
        <RefreshCw className="w-5 h-5 animate-spin mr-2" />
        Загрузка...
      </div>
    )
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg">
            <Settings className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Интервалы ТО и ремонтов
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Настройка пробегов для каждого типа технического обслуживания
            </p>
          </div>
        </div>
        <button
          onClick={handleCreate}
          disabled={isCreating}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          Добавить интервал
        </button>
      </div>

      {/* Info */}
      <div className="flex items-start gap-2 text-xs text-gray-500 bg-blue-50 dark:bg-blue-950/30 rounded-xl px-4 py-3 border border-blue-200 dark:border-blue-800">
        <Info className="w-4 h-4 flex-shrink-0 mt-0.5 text-blue-500" />
        <span>
          Укажите интервал в километрах для каждого типа ТО. Например, если ТО-2 должен
          выполняться каждые 90 км, установите значение 90. Система автоматически
          рассчитает, когда агрегат должен заходить в ремонт.
        </span>
      </div>

      {/* Create Form */}
      {isCreating && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border-2 border-blue-500 p-6 space-y-4">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Plus className="w-5 h-5 text-blue-500" />
            Новый интервал ТО
          </h3>
          <div className="grid grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Код *
              </label>
              <input
                type="text"
                value={formData.code || ""}
                onChange={e => setFormData({ ...formData, code: e.target.value })}
                placeholder="ТО-2"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Название *
              </label>
              <input
                type="text"
                value={formData.name || ""}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                placeholder="Техническое обслуживание 2"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Интервал (км) *
              </label>
              <input
                type="number"
                value={formData.interval_km || ""}
                onChange={e => setFormData({ ...formData, interval_km: parseInt(e.target.value) || 0 })}
                placeholder="90"
                min={1}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Интервал (дней)
              </label>
              <input
                type="number"
                value={formData.interval_days || ""}
                onChange={e => setFormData({ ...formData, interval_days: parseInt(e.target.value) || null })}
                placeholder="30"
                min={1}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Описание
              </label>
              <input
                type="text"
                value={formData.description || ""}
                onChange={e => setFormData({ ...formData, description: e.target.value })}
                placeholder="Описание типа ТО"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
              />
            </div>
            <div className="col-span-2 flex items-end gap-3">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-semibold disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {saving ? "Сохранение..." : "Сохранить"}
              </button>
              <button
                onClick={handleCancel}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <X className="w-4 h-4" />
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
          <div className="flex items-center gap-3">
            <Wrench className="w-4 h-4 text-amber-500" />
            <h2 className="text-sm font-bold text-gray-900 dark:text-white">
              Настроенные интервалы
            </h2>
            <span className="text-xs text-gray-400">· {intervals.length} записей</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-800">
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase">
                  Статус
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase">
                  Код
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase">
                  Название
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase">
                  Интервал (км)
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase">
                  Интервал (дней)
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase">
                  Описание
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase">
                  Действия
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {intervals.map(interval => (
                <tr
                  key={interval.id}
                  className={`hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors ${
                    !interval.is_active ? "opacity-50" : ""
                  }`}
                >
                  {editingId === interval.id ? (
                    <>
                      <td className="px-5 py-3">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={formData.is_active ?? true}
                            onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                            className="w-4 h-4 rounded border-gray-300 text-green-600"
                          />
                          <span className="text-xs">Активен</span>
                        </label>
                      </td>
                      <td className="px-5 py-3">
                        <input
                          type="text"
                          value={formData.code || ""}
                          onChange={e => setFormData({ ...formData, code: e.target.value })}
                          className="w-20 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800"
                        />
                      </td>
                      <td className="px-5 py-3">
                        <input
                          type="text"
                          value={formData.name || ""}
                          onChange={e => setFormData({ ...formData, name: e.target.value })}
                          className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800"
                        />
                      </td>
                      <td className="px-5 py-3">
                        <input
                          type="number"
                          value={formData.interval_km || ""}
                          onChange={e => setFormData({ ...formData, interval_km: parseInt(e.target.value) || 0 })}
                          className="w-24 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800"
                          min={1}
                        />
                      </td>
                      <td className="px-5 py-3">
                        <input
                          type="number"
                          value={formData.interval_days || ""}
                          onChange={e => setFormData({ ...formData, interval_days: parseInt(e.target.value) || null })}
                          className="w-20 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800"
                          min={1}
                        />
                      </td>
                      <td className="px-5 py-3">
                        <input
                          type="text"
                          value={formData.description || ""}
                          onChange={e => setFormData({ ...formData, description: e.target.value })}
                          className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800"
                        />
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleSave}
                            disabled={saving}
                            className="p-1.5 rounded-lg bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-950 dark:text-green-400"
                          >
                            <Save className="w-4 h-4" />
                          </button>
                          <button
                            onClick={handleCancel}
                            className="p-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-5 py-3">
                        <button
                          onClick={() => handleToggleActive(interval.id, interval.is_active)}
                          className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full cursor-pointer ${
                            interval.is_active
                              ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400"
                              : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                          }`}
                        >
                          {interval.is_active ? (
                            <>
                              <CheckCircle className="w-3 h-3" /> Активен
                            </>
                          ) : (
                            <>
                              <AlertTriangle className="w-3 h-3" /> Отключен
                            </>
                          )}
                        </button>
                      </td>
                      <td className="px-5 py-3">
                        <span className="text-sm font-bold text-blue-600 dark:text-blue-400">
                          {interval.code}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-sm text-gray-900 dark:text-white">
                        {interval.name}
                      </td>
                      <td className="px-5 py-3">
                        <span className="text-sm font-bold text-amber-600 dark:text-amber-400">
                          {interval.interval_km.toLocaleString()} км
                        </span>
                      </td>
                      <td className="px-5 py-3 text-sm text-gray-600 dark:text-gray-300">
                        {interval.interval_days ? `${interval.interval_days} дн.` : "—"}
                      </td>
                      <td className="px-5 py-3 text-sm text-gray-500 dark:text-gray-400 max-w-xs truncate">
                        {interval.description || "—"}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleEdit(interval)}
                            className="p-1.5 rounded-lg bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-950 dark:text-blue-400"
                            title="Редактировать"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(interval.id, interval.code)}
                            className="p-1.5 rounded-lg bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-950 dark:text-red-400"
                            title="Удалить"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
              {intervals.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-10 text-center text-sm text-gray-400">
                    Нет настроенных интервалов. Нажмите "Добавить интервал" для создания.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Example */}
      <div className="bg-amber-50 dark:bg-amber-950/30 rounded-xl p-4 border border-amber-200 dark:border-amber-800">
        <h3 className="text-sm font-bold text-amber-800 dark:text-amber-300 mb-2">
          Пример настройки
        </h3>
        <p className="text-xs text-amber-700 dark:text-amber-400">
          Если ТО-2 должен выполняться каждые <strong>90 км</strong>, установите:
        </p>
        <ul className="text-xs text-amber-700 dark:text-amber-400 mt-2 space-y-1 ml-4 list-disc">
          <li>Код: <code className="bg-amber-200 dark:bg-amber-900 px-1 rounded">ТО-2</code></li>
          <li>Интервал (км): <code className="bg-amber-200 dark:bg-amber-900 px-1 rounded">90</code></li>
          <li>
            Система автоматически рассчитает: при пробеге 85 км — предупреждение, при 90+ км — требуется ремонт
          </li>
        </ul>
      </div>
    </div>
  )
}
