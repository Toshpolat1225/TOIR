"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AlertTriangle, ChevronLeft, Radio, Search, Train, X } from "@/components/ui/icons"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, type WialonAssetSuggestion, type WialonUnit, type WialonUnitDetail } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"

const PAGE_SIZE = 50

function connectionLabel(unit: WialonUnit): string {
  if (!unit.last_message_at || Date.now() - new Date(unit.last_message_at).getTime() > 24 * 60 * 60 * 1000) {
    return "Давно"
  }
  return unit.is_online ? "Онлайн" : "Нет связи"
}

export default function WialonUnitsPage() {
  const router = useRouter()
  const { profile } = useAuth()
  const canWrite = profile?.role === "admin" || profile?.role === "operator"
  const [units, setUnits] = useState<WialonUnit[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState("")
  const [linked, setLinked] = useState<"" | "true" | "false">("")
  const [onlineOnly, setOnlineOnly] = useState(false)
  const [suspectOnly, setSuspectOnly] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [selected, setSelected] = useState<WialonUnitDetail | null>(null)
  const [suggestions, setSuggestions] = useState<WialonAssetSuggestion[]>([])
  const [detailError, setDetailError] = useState("")
  const [savingAsset, setSavingAsset] = useState(false)
  const [assetName, setAssetName] = useState("")
  const [inventoryNumber, setInventoryNumber] = useState("")
  const [assetType, setAssetType] = useState<"locomotive" | "diesel" | "wagon" | "">("")
  const [createError, setCreateError] = useState("")

  useEffect(() => {
    if (profile?.role === "master") router.replace("/dashboard/directories/assets")
  }, [profile?.role, router])

  const loadUnits = useCallback(async () => {
    if (!profile || profile.role === "master") return
    setLoading(true)
    setError("")
    try {
      const response = await api.wialon.listUnits({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        q: search.trim() || undefined,
        linked: linked === "" ? undefined : linked === "true",
        online: onlineOnly ? true : undefined,
        suspect: suspectOnly ? true : undefined,
        sort_by: "name",
        sort_order: "asc",
      })
      setUnits(response.items)
      setTotal(response.total)
    } catch (loadFailure) {
      setUnits([])
      setTotal(0)
      setError(loadFailure instanceof Error ? loadFailure.message : "Не удалось загрузить данные Wialon.")
    } finally {
      setLoading(false)
    }
  }, [profile, page, search, linked, onlineOnly, suspectOnly])

  useEffect(() => {
    void loadUnits()
  }, [loadUnits])

  const openUnit = async (unit: WialonUnit) => {
    setSelected({ ...unit, rejected_readings: [] })
    setSuggestions([])
    setDetailError("")
    setAssetName(unit.name)
    setInventoryNumber(`WIALON-${unit.unit_id}`)
    try {
      const [detail, matches] = await Promise.all([
        api.wialon.getUnit(unit.unit_id),
        api.wialon.suggestions(unit.unit_id),
      ])
      setSelected(detail)
      setSuggestions(matches.items)
    } catch (loadFailure) {
      setDetailError(loadFailure instanceof Error ? loadFailure.message : "Не удалось загрузить карточку единицы.")
    }
  }

  const linkAsset = async (suggestion: WialonAssetSuggestion) => {
    if (!selected || !canWrite) return
    setSavingAsset(true)
    setDetailError("")
    try {
      await api.fixedAssets.update(suggestion.asset_id, { wialon_id: selected.unit_id })
      await openUnit({ ...selected, linked_asset: { id: suggestion.asset_id, name: suggestion.name, inv_number: suggestion.inv_number } })
      await loadUnits()
    } catch (saveFailure) {
      setDetailError(saveFailure instanceof Error ? saveFailure.message : "Не удалось привязать ОС.")
    } finally {
      setSavingAsset(false)
    }
  }

  const createAsset = async () => {
    if (!selected || !canWrite || !assetName.trim() || !inventoryNumber.trim() || !assetType) {
      setCreateError("Укажите инвентарный номер, наименование и тип ОС.")
      return
    }
    setSavingAsset(true)
    setCreateError("")
    try {
      const response = await api.wialon.createAsset(selected.unit_id, {
        inv_number: inventoryNumber.trim(),
        name: assetName.trim(),
        asset_type: assetType,
      })
      const warning = response.warning
      await openUnit(selected)
      if (warning) setDetailError(warning)
      await loadUnits()
    } catch (saveFailure) {
      setCreateError(saveFailure instanceof Error ? saveFailure.message : "Не удалось создать ОС.")
    } finally {
      setSavingAsset(false)
    }
  }

  if (!profile || profile.role === "master") {
    return <div className="p-8 text-sm text-gray-500">Загрузка...</div>
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {selected && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={() => setSelected(null)}>
          <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-800 dark:bg-gray-900" onClick={(event) => event.stopPropagation()}>
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <button type="button" onClick={() => setSelected(null)} className="mb-3 inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"><ChevronLeft className="h-3.5 w-3.5"/>К списку</button>
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">{selected.name}</h2>
                <p className="mt-1 text-xs text-gray-500">ID: {selected.unit_id}</p>
              </div>
              <button type="button" aria-label="Закрыть" onClick={() => setSelected(null)} className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"><X className="h-4 w-4"/></button>
            </div>

            {detailError && <p role="alert" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">{detailError}</p>}

            <section className="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
              <h3 className="mb-3 text-sm font-semibold">Данные Wialon</h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <p>Пробег: <b>{selected.cnm ?? "—"} км</b></p>
                <p>Моточасы: <b>{selected.cneh ?? "—"}</b></p>
                <p>Скорость: <b>{selected.speed ?? "—"} км/ч</b></p>
                <p>Связь: <b>{connectionLabel(selected)}</b></p>
                <p className="col-span-2">Последнее сообщение: <b>{selected.last_message_at ? new Date(selected.last_message_at).toLocaleString("ru-RU") : "—"}</b></p>
              </div>
              {selected.suspect_absolute && <p className="mt-3 flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-300"><AlertTriangle className="h-4 w-4"/>Подозрительное значение счётчика</p>}
              <p className="mt-3 text-xs text-gray-500">Счётчик: {selected.counter_state?.last_status ?? "нет решения"}{selected.counter_state?.last_reason ? ` · ${selected.counter_state.last_reason}` : ""}</p>
            </section>

            <section className="mt-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
              <h3 className="mb-3 text-sm font-semibold">Отклонённые показания ({selected.rejected_count})</h3>
              {selected.rejected_readings.length ? (
                <ul className="space-y-2 text-xs">
                  {selected.rejected_readings.map((reading) => <li key={reading.id} className="rounded-lg bg-gray-50 p-2 dark:bg-gray-800">
                    <b>{reading.counter}</b>: {reading.value ?? "—"} · {reading.reason}
                    <span className="mt-1 block text-gray-500">{reading.reading_at ? new Date(reading.reading_at).toLocaleString("ru-RU") : "Дата неизвестна"}</span>
                  </li>)}
                </ul>
              ) : <p className="text-sm text-gray-500">Нет отклонённых показаний.</p>}
            </section>

            <section className="mt-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
              <h3 className="mb-3 text-sm font-semibold">Предполагаемые основные средства</h3>
              {selected.linked_asset && <p className="mb-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300">
                Привязано: {selected.linked_asset.name} · {selected.linked_asset.inv_number}
              </p>}
              {suggestions.length ? <div className="space-y-2">
                {suggestions.map((suggestion) => <div key={suggestion.asset_id} className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{suggestion.name}</p>
                    <p className="text-xs text-gray-500">{suggestion.inv_number} · {suggestion.series || suggestion.asset_type}</p>
                  </div>
                  {canWrite && !selected.linked_asset && <Button size="sm" disabled={savingAsset} onClick={() => void linkAsset(suggestion)}>Привязать</Button>}
                </div>)}
              </div> : <p className="text-sm text-gray-500">Подходящих ОС не найдено.</p>}
            </section>

            {canWrite && !selected.linked_asset && (
              <section className="mt-4 rounded-xl border border-blue-200 bg-blue-50/60 p-4 dark:border-blue-900 dark:bg-blue-950/20">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Train className="h-4 w-4"/>Создать ОС</h3>
                <div className="space-y-3">
                  <Input aria-label="Наименование ОС" value={assetName} onChange={(event) => setAssetName(event.target.value)} placeholder="Наименование"/>
                  <Input aria-label="Инвентарный номер" value={inventoryNumber} onChange={(event) => setInventoryNumber(event.target.value)} placeholder="Инвентарный номер"/>
                  <select aria-label="Тип ОС" required value={assetType} onChange={(event) => setAssetType(event.target.value as typeof assetType)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800">
                    <option value="" disabled>Выберите тип</option>
                    <option value="locomotive">Локомотив</option>
                    <option value="diesel">Тепловоз</option>
                    <option value="wagon">Вагон</option>
                  </select>
                  {createError && <p role="alert" className="text-xs text-red-600">{createError}</p>}
                  <Button disabled={savingAsset} onClick={() => void createAsset()}>{savingAsset ? "Сохранение..." : "Создать ОС"}</Button>
                </div>
              </section>
            )}
          </aside>
        </div>
      )}

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <a href="/dashboard/directories/assets" className="mb-2 inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"><ChevronLeft className="h-3.5 w-3.5"/>Основные средства</a>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Данные Wialon</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Отдельный список единиц Wialon и их привязок к ОС.</p>
        </div>
        <Button variant="outline" onClick={() => void loadUnits()} disabled={loading}><Radio className="mr-2 h-4 w-4"/>Обновить</Button>
      </header>

      <section className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"/>
          <Input className="pl-9" placeholder="Поиск по названию или ID" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0) }}/>
        </div>
        <select aria-label="Привязка" value={linked} onChange={(event) => { setLinked(event.target.value as typeof linked); setPage(0) }} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800">
          <option value="">Все привязки</option><option value="true">Привязанные</option><option value="false">Не привязанные</option>
        </select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlineOnly} onChange={(event) => { setOnlineOnly(event.target.checked); setPage(0) }}/>Онлайн</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={suspectOnly} onChange={(event) => { setSuspectOnly(event.target.checked); setPage(0) }}/>Подозрительные</label>
        <span className="ml-auto text-xs text-gray-500">Найдено: {total}</span>
      </section>

      {error && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
      <section className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <table className="w-full min-w-[760px]">
          <thead><tr className="border-b border-gray-200 bg-gray-50 text-left text-xs uppercase text-gray-500 dark:border-gray-800 dark:bg-gray-800/50">
            {["Наименование / ID", "Пробег, км", "Моточасы", "Скорость", "Последнее сообщение", "Связь", "ОС"].map((heading) => <th key={heading} className="px-4 py-3">{heading}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {loading ? <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-500">Загрузка...</td></tr>
              : units.length ? units.map((unit) => <tr key={unit.unit_id} onClick={() => void openUnit(unit)} className="cursor-pointer hover:bg-blue-50/50 dark:hover:bg-blue-950/20">
                <td className="px-4 py-3"><p className="text-sm font-semibold">{unit.name}</p><p className="text-xs text-gray-500">{unit.unit_id}{unit.suspect_absolute && <span className="ml-2 text-amber-600">⚠</span>}</p></td>
                <td className="px-4 py-3 text-sm">{unit.cnm ?? "—"}</td><td className="px-4 py-3 text-sm">{unit.cneh ?? "—"}</td>
                <td className="px-4 py-3 text-sm">{unit.speed ?? "—"}</td>
                <td className="px-4 py-3 text-xs">{unit.last_message_at ? new Date(unit.last_message_at).toLocaleString("ru-RU") : "—"}</td>
                <td className="px-4 py-3 text-xs">{connectionLabel(unit)}</td>
                <td className="px-4 py-3 text-xs">{unit.linked_asset?.inv_number ?? "Не привязан"}</td>
              </tr>) : <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-500">{error ? "Ошибка загрузки списка." : "Единиц Wialon не найдено."}</td></tr>}
          </tbody>
        </table>
        {totalPages > 1 && <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-xs dark:border-gray-800">
          <span>Страница {page + 1} из {totalPages}</span>
          <div className="flex gap-2"><Button variant="outline" size="sm" disabled={!page} onClick={() => setPage((value) => value - 1)}>Назад</Button><Button variant="outline" size="sm" disabled={page + 1 >= totalPages} onClick={() => setPage((value) => value + 1)}>Вперёд</Button></div>
        </div>}
      </section>
    </div>
  )
}
