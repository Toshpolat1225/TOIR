"use client"

import { useCallback, useEffect, useState } from "react"
import {
  api,
  type AssetConflictRow,
  type AssetFieldChange,
  type WialonCounterBlock,
} from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"

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

const ASSET_TYPE_LABELS: Record<string, string> = {
  wagon: "Вагон",
  locomotive: "Локомотив",
  diesel: "Тепловоз",
  platform: "Платформа",
  tank_car: "Цистерна",
  special_self_propelled: "Спецтехника",
}

const STATUS_LABELS: Record<AssetFieldChange["status"], string> = {
  pending: "Ожидают решения",
  accepted: "Приняты",
  rejected: "Отклонены",
  applied: "Применены автоматически",
}

const PAGE_SIZE = 50
const selectCls =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm dark:bg-input/30"

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—"
  return typeof value === "object" ? JSON.stringify(value) ?? String(value) : String(value)
}

function assetLabel(type: string, inv: string, serial?: string | null): string {
  const name = ASSET_TYPE_LABELS[type] || type
  return `${name} ${serial ? `${serial}-` : ""}${inv}`
}

function sinceText(iso: string): string {
  const hours = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000))
  if (hours < 24) return `${hours} ч.`
  return `${Math.floor(hours / 24)} дн. ${hours % 24} ч.`
}

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

function Pager({
  total, offset, loading, onChange,
}: { total: number; offset: number; loading: boolean; onChange: (next: number) => void }) {
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)
  return (
    <div className="flex items-center justify-between text-sm text-gray-500">
      <span>{from}–{to} из {total}</span>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))} disabled={loading || offset === 0}>Назад</Button>
        <Button size="sm" variant="outline" onClick={() => onChange(offset + PAGE_SIZE)} disabled={loading || offset + PAGE_SIZE >= total}>Далее</Button>
      </div>
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  if (!message) return null
  return <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{message}</p>
}

function StatCard({ title, value, hint, tone }: { title: string; value: number | string; hint: string; tone?: "warn" }) {
  return (
    <div className={`rounded-xl border p-4 ${tone === "warn" ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30" : "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"}`}>
      <p className="text-xs uppercase text-gray-500 dark:text-gray-400">{title}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>
    </div>
  )
}

export default function AssetConflictsPage() {
  const { profile, loading: authLoading, hasPermission } = useAuth()
  const canManage =
    (profile?.role === "admin" || profile?.role === "operator") &&
    hasPermission("asset_conflicts.manage")

  const [tab, setTab] = useState<"fields" | "wialon">("wialon")

  // passport conflicts
  const [items, setItems] = useState<AssetConflictRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<AssetFieldChange["status"]>("pending")
  const [source, setSource] = useState("")
  const [field, setField] = useState("")
  const [search, setSearch] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [busyId, setBusyId] = useState<number | null>(null)
  const debouncedSearch = useDebounced(search)

  // wialon counter blocks
  const [blocks, setBlocks] = useState<WialonCounterBlock[]>([])
  const [blockTotal, setBlockTotal] = useState(0)
  const [blockedLocos, setBlockedLocos] = useState(0)
  const [affectedWagons, setAffectedWagons] = useState(0)
  const [blockOffset, setBlockOffset] = useState(0)
  const [blockSearch, setBlockSearch] = useState("")
  const [blockLoading, setBlockLoading] = useState(true)
  const [blockError, setBlockError] = useState("")
  const debouncedBlockSearch = useDebounced(blockSearch)

  const loadFields = useCallback(async () => {
    if (authLoading || !canManage) return
    setLoading(true)
    setError("")
    try {
      const response = await api.assetConflicts.list({
        status,
        source: source || undefined,
        field: field || undefined,
        q: debouncedSearch.trim() || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setItems(response.items)
      setTotal(response.total)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить расхождения.")
    } finally {
      setLoading(false)
    }
  }, [authLoading, canManage, status, source, field, debouncedSearch, offset])

  const loadBlocks = useCallback(async () => {
    if (authLoading || !canManage) return
    setBlockLoading(true)
    setBlockError("")
    try {
      const response = await api.assetConflicts.wialonCounters({
        q: debouncedBlockSearch.trim() || undefined,
        limit: PAGE_SIZE,
        offset: blockOffset,
      })
      setBlocks(response.items)
      setBlockTotal(response.total)
      setBlockedLocos(response.blocked_locomotives)
      setAffectedWagons(response.affected_wagons)
    } catch (loadError) {
      setBlockError(loadError instanceof Error ? loadError.message : "Не удалось загрузить блокировки счётчиков.")
    } finally {
      setBlockLoading(false)
    }
  }, [authLoading, canManage, debouncedBlockSearch, blockOffset])

  useEffect(() => { void loadFields() }, [loadFields])
  useEffect(() => { void loadBlocks() }, [loadBlocks])
  useEffect(() => { setOffset(0) }, [status, source, field, debouncedSearch])
  useEffect(() => { setBlockOffset(0) }, [debouncedBlockSearch])

  const resolve = async (item: AssetConflictRow, action: "accept" | "reject") => {
    const actionLabel = action === "accept" ? "принять" : "отклонить"
    if (!window.confirm(`Вы уверены, что хотите ${actionLabel} это предложение?`)) return
    setBusyId(item.id)
    setError("")
    try {
      if (action === "accept") await api.assetConflicts.accept(item.id)
      else await api.assetConflicts.reject(item.id)
      await loadFields()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Не удалось обработать конфликт.")
    } finally {
      setBusyId(null)
    }
  }

  if (authLoading) {
    return <div className="p-8 text-sm text-gray-500">Загрузка...</div>
  }
  if (!canManage) {
    return <div className="p-8 text-sm text-gray-600 dark:text-gray-300">Нет доступа к этой странице.</div>
  }

  return (
    <div className="space-y-6 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Конфликты данных</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Здесь собраны места, где данные из разных источников расходятся и система не может выбрать верное значение сама.
          </p>
        </div>
        <Button variant="outline" onClick={() => { void loadFields(); void loadBlocks() }} disabled={loading || blockLoading}>Обновить</Button>
      </header>

      <details className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
        <summary className="cursor-pointer font-medium text-gray-900 dark:text-white">Что это за страница? (нажмите, чтобы прочитать)</summary>
        <div className="mt-3 space-y-2">
          <p>Система TOIR получает данные о технике из нескольких источников: <b>GTK</b> (составы и вагоны), <b>Wialon</b> (спутниковые счётчики пробега локомотивов), <b>1С</b> и весовой. Когда два источника сообщают разное, система ничего не меняет молча, а показывает расхождение здесь.</p>
          <p><b>Вкладка «Счётчики Wialon»</b>: у локомотива счётчик пробега получил два разных показания на одно и то же время. Пробег этого локомотива остановлен, а вагоны в его составе нельзя посчитать, пока администратор не снимет блокировку (подробности ниже).</p>
          <p><b>Вкладка «Расхождения паспорта»</b>: источник предлагает другое значение поля (номер, тип, модель, год и т.д.). Можно принять предложение или отклонить его.</p>
        </div>
      </details>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard title="Расхождения паспорта" value={status === "pending" ? total : "—"} hint="ожидают решения оператора" />
        <StatCard title="Заблокированные локомотивы" value={blockedLocos} hint="счётчик Wialon остановлен" tone={blockedLocos > 0 ? "warn" : undefined} />
        <StatCard title="Вагоны без расчёта пробега" value={affectedWagons} hint="их составы ведут заблокированные локомотивы" tone={affectedWagons > 0 ? "warn" : undefined} />
      </div>

      <div className="flex gap-2 border-b border-gray-200 dark:border-gray-800">
        {([["wialon", `Счётчики Wialon (${blockedLocos})`], ["fields", "Расхождения паспорта"]] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === key ? "border-blue-600 text-blue-700 dark:text-blue-400" : "border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "wialon" && (
        <section className="space-y-4">
          <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
            <p className="font-semibold">Что произошло</p>
            <p className="mt-1">Wialon прислал для локомотива два разных значения счётчика с одинаковым временем последнего сообщения, и система остановила приём показаний этого локомотива. Пока блокировка стоит, его пробег не растёт, а пробег вагонов в его составах не рассчитывается.</p>
            <p className="mt-3 font-semibold">Почему это не ошибка данных</p>
            <p className="mt-1">Проверка 668 таких случаев: счётчик продолжает расти, пока время последнего сообщения стоит на месте, и <b>второе значение было больше первого во всех случаях</b> (уменьшений не было). Рост укладывается в максимальную скорость. Поэтому новые такие случаи система больше не блокирует: первое показание остаётся основным, а прирост засчитывается со следующим показанием с новым временем.</p>
            <p className="mt-3 font-semibold">Что делать с локомотивами из списка (решает администратор)</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              <li><b>Снять блокировку по проверке истории</b> (рекомендуется): команда <code>wialon-counter-release</code> сначала показывает план, ничего не меняя. Блок снимается только у локомотива, у которого счётчик не уменьшался и не прыгал быстрее допустимого; пробег за период блокировки догоняется со следующим показанием. Остальные остаются в списке для ручной проверки.</li>
              <li><b>Сбросить «новую базовую линию»</b>: система примет текущее показание за точку отсчёта. Быстро, но пробег за период блокировки теряется безвозвратно, а причина остаётся неизвестной.</li>
            </ol>
            <p className="mt-2 text-xs">Кнопки сброса здесь намеренно нет: действие выполняется командой администратора и записывается в журнал.</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Input
              className="max-w-xs"
              placeholder="Поиск по инв. или серийному номеру"
              value={blockSearch}
              onChange={(event) => setBlockSearch(event.target.value)}
            />
            {blockSearch && <Button size="sm" variant="outline" onClick={() => setBlockSearch("")}>Сбросить</Button>}
          </div>

          <ErrorBox message={blockError} />

          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3">Локомотив</th>
                  <th className="px-4 py-3">ID в Wialon</th>
                  <th className="px-4 py-3">Заблокирован</th>
                  <th className="px-4 py-3">Последнее верное показание</th>
                  <th className="px-4 py-3">Отклонено за 24 ч.</th>
                  <th className="px-4 py-3">Вагонов затронуто</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {blockLoading ? (
                  <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={6}>Загрузка...</td></tr>
                ) : blocks.length === 0 ? (
                  <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={6}>Заблокированных счётчиков нет.</td></tr>
                ) : blocks.map((row) => (
                  <tr key={row.asset_id} className="align-top">
                    <td className="px-4 py-3">
                      <span className="font-medium text-gray-900 dark:text-white">{assetLabel(row.asset_type, row.inv_number, row.serial_number)}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{row.wialon_id || "—"}</td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <span className="text-gray-900 dark:text-white">{new Date(row.blocked_since).toLocaleString("ru-RU")}</span>
                      <span className="block text-xs text-gray-500">уже {sinceText(row.blocked_since)}</span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-600 dark:text-gray-300">
                      {row.last_cnm === null ? "—" : `${row.last_cnm.toLocaleString("ru-RU")} км`}
                      {row.last_cnm_at && <span className="block text-xs text-gray-500">{new Date(row.last_cnm_at).toLocaleString("ru-RU")}</span>}
                    </td>
                    <td className="px-4 py-3"><Badge variant={row.blocked_readings_24h > 0 ? "destructive" : "secondary"}>{row.blocked_readings_24h}</Badge></td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{row.affected_wagons}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={blockTotal} offset={blockOffset} loading={blockLoading} onChange={setBlockOffset} />
        </section>
      )}

      {tab === "fields" && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <select aria-label="Статус" className={selectCls} value={status} onChange={(event) => setStatus(event.target.value as AssetFieldChange["status"])}>
              {Object.entries(STATUS_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <select aria-label="Источник" className={selectCls} value={source} onChange={(event) => setSource(event.target.value)}>
              <option value="">Все источники</option>
              {Object.entries(SOURCE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <select aria-label="Поле" className={selectCls} value={field} onChange={(event) => setField(event.target.value)}>
              <option value="">Все поля</option>
              {Object.entries(FIELD_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <Input
              className="max-w-xs"
              placeholder="Поиск по инв. или серийному номеру"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            {(source || field || search || status !== "pending") && (
              <Button size="sm" variant="outline" onClick={() => { setSource(""); setField(""); setSearch(""); setStatus("pending") }}>Сбросить фильтры</Button>
            )}
          </div>

          <ErrorBox message={error} />

          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3">Техника</th>
                  <th className="px-4 py-3">Поле</th>
                  <th className="px-4 py-3">Сейчас в системе</th>
                  <th className="px-4 py-3">Предлагает источник</th>
                  <th className="px-4 py-3">Источник</th>
                  <th className="px-4 py-3">Дата</th>
                  <th className="px-4 py-3">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {loading ? (
                  <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={7}>Загрузка...</td></tr>
                ) : items.length === 0 ? (
                  <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={7}>Ничего не найдено.</td></tr>
                ) : items.map((item) => (
                  <tr key={item.id} className="align-top">
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{assetLabel(item.asset_type, item.asset_inv_number, item.asset_serial_number)}</td>
                    <td className="px-4 py-3 text-gray-900 dark:text-white">{FIELD_LABELS[item.field] || item.field}</td>
                    <td className="max-w-64 break-words px-4 py-3 text-gray-600 dark:text-gray-300">{displayValue(item.old_value)}</td>
                    <td className="max-w-64 break-words px-4 py-3 font-medium text-gray-900 dark:text-white">{displayValue(item.new_value)}</td>
                    <td className="px-4 py-3">{SOURCE_LABELS[item.source] || item.source}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-500">{new Date(item.created_at).toLocaleString("ru-RU")}</td>
                    <td className="px-4 py-3">
                      {item.status === "pending" ? (
                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" onClick={() => void resolve(item, "accept")} disabled={busyId === item.id}>Принять</Button>
                          <Button size="sm" variant="outline" onClick={() => void resolve(item, "reject")} disabled={busyId === item.id}>Отклонить</Button>
                        </div>
                      ) : (
                        <Badge variant="secondary">{STATUS_LABELS[item.status]}</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={total} offset={offset} loading={loading} onChange={setOffset} />
        </section>
      )}
    </div>
  )
}
