"use client"

import { useCallback, useEffect, useState } from "react"
import { api, type AssetCatalogBehavior, type AssetCatalogColor, type AssetCatalogItem, type AssetCatalogKind, type TranslationLocale } from "@/lib/api"

const locales: { id: TranslationLocale; label: string }[] = [
  { id: "uz-Latn", label: "O‘zbekcha (lotin)" },
  { id: "uz-Cyrl", label: "Ўзбекча (кирилл)" },
  { id: "ru", label: "Русский" },
]
const colors: AssetCatalogColor[] = ["blue", "green", "amber", "orange", "red", "gray", "purple"]
const behaviorLabels: Record<AssetCatalogBehavior, string> = {
  operational: "В эксплуатации", maintenance: "На ТО", repair: "Ремонт", out_of_service: "Выведен",
}
const initialNames = (): Record<TranslationLocale, string> => ({ "uz-Latn": "", "uz-Cyrl": "", ru: "" })

export default function AssetCatalogsPage() {
  const [kind, setKind] = useState<AssetCatalogKind>("types")
  const [rows, setRows] = useState<AssetCatalogItem[]>([])
  const [query, setQuery] = useState("")
  const [active, setActive] = useState("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [editing, setEditing] = useState<AssetCatalogItem | null>(null)
  const [creating, setCreating] = useState(false)
  const [code, setCode] = useState("")
  const [names, setNames] = useState(initialNames())
  const [isActive, setIsActive] = useState(true)
  const [behavior, setBehavior] = useState<AssetCatalogBehavior>("operational")
  const [color, setColor] = useState<AssetCatalogColor>("blue")
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError("")
    try {
      const result = await api.fixedAssetCatalogs.list(kind, {
        limit: 500, offset: 0, q: query || undefined,
        is_active: active === "all" ? undefined : active === "active",
      })
      setRows(result.items)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить справочник")
      setRows([])
    } finally { setLoading(false) }
  }, [kind, query, active])
  useEffect(() => { void load() }, [load])

  const beginCreate = () => {
    setEditing(null); setCreating(true); setCode(""); setNames(initialNames())
    setIsActive(true); setBehavior("operational"); setColor(kind === "statuses" ? "green" : "blue"); setError("")
  }
  const beginEdit = (row: AssetCatalogItem) => {
    setCreating(false); setEditing(row); setCode(row.code)
    setNames({ "uz-Latn": row.names["uz-Latn"] || "", "uz-Cyrl": row.names["uz-Cyrl"] || "", ru: row.names.ru || "" })
    setIsActive(row.is_active); setBehavior(row.behavior || "operational"); setColor(row.color); setError("")
  }
  const save = async () => {
    if (Object.values(names).some((value) => !value.trim()) || (creating && !/^[a-z][a-z0-9_]{1,49}$/.test(code))) {
      setError("Заполните все переводы. Код: латинские строчные буквы, цифры и _."); return
    }
    setSaving(true); setError("")
    try {
      const payload = { names, is_active: isActive, color, ...(kind === "statuses" ? { behavior } : {}) }
      if (creating) await api.fixedAssetCatalogs.create(kind, { ...payload, code })
      else if (editing) await api.fixedAssetCatalogs.update(kind, editing.code, payload)
      setCreating(false); setEditing(null); await load()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить запись") }
    finally { setSaving(false) }
  }
  const remove = async (row: AssetCatalogItem) => {
    if (row.usage_count) { setError(`Запись используется в ${row.usage_count} объектах ОС. Деактивируйте её.`); return }
    if (!window.confirm(`Удалить запись «${row.name}» (${row.code})?`)) return
    setError("")
    try { await api.fixedAssetCatalogs.remove(kind, row.code); await load() }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось удалить запись") }
  }
  const close = () => { setCreating(false); setEditing(null); setError("") }
  const formOpen = creating || Boolean(editing)
  const inputClass = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white"

  return <main className="space-y-5 p-4 md:p-6">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div><h1 className="text-2xl font-bold text-gray-900 dark:text-white">Справочники основных средств</h1><p className="mt-1 text-sm text-gray-500">Типы и статусы объектов ОС</p></div>
      <button onClick={beginCreate} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Добавить</button>
    </header>
    <div className="flex flex-wrap gap-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <select value={kind} onChange={(e) => setKind(e.target.value as AssetCatalogKind)} className={inputClass + " max-w-xs"}>
        <option value="types">Типы ОС</option><option value="statuses">Статусы ОС</option>
      </select>
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по коду или названию" className={inputClass + " max-w-sm"}/>
      <select value={active} onChange={(e) => setActive(e.target.value)} className={inputClass + " max-w-xs"}>
        <option value="all">Все записи</option><option value="active">Активные</option><option value="inactive">Неактивные</option>
      </select>
    </div>
    {error && !formOpen && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}
    {loading ? <p className="p-8 text-center text-gray-500">Загрузка справочника…</p> : rows.length === 0 ? <p className="rounded-xl border border-dashed border-gray-300 p-10 text-center text-gray-500 dark:border-gray-700">Записей нет</p> :
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"><table className="w-full min-w-[760px] text-left text-sm">
        <thead className="bg-gray-50 text-xs uppercase text-gray-500 dark:bg-gray-800"><tr><th className="p-3">Код</th><th className="p-3">Название (ru)</th><th className="p-3">O‘zbekcha</th><th className="p-3">Ўзбекча</th>{kind === "statuses" && <th className="p-3">Правило</th>}<th className="p-3">Используется</th><th className="p-3">Состояние</th><th className="p-3">Действия</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.code} className="border-t border-gray-100 dark:border-gray-800"><td className="p-3 font-mono">{row.code}</td><td className="p-3">{row.names.ru || "—"}</td><td className="p-3">{row.names["uz-Latn"] || "—"}</td><td className="p-3">{row.names["uz-Cyrl"] || "—"}</td>{kind === "statuses" && <td className="p-3">{row.behavior ? behaviorLabels[row.behavior] : "—"}</td>}<td className="p-3">{row.usage_count}</td><td className="p-3">{row.is_active ? "Активна" : "Неактивна"}</td><td className="p-3"><div className="flex gap-2"><button onClick={() => beginEdit(row)} className="text-blue-600 hover:underline">Изменить</button><button onClick={() => void remove(row)} className="text-red-600 hover:underline">Удалить</button></div></td></tr>)}</tbody>
      </table></div>}
    {formOpen && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"><section role="dialog" aria-modal="true" className="w-full max-w-xl space-y-4 rounded-2xl bg-white p-6 shadow-xl dark:bg-gray-900">
      <div className="flex items-center justify-between"><h2 className="text-lg font-bold text-gray-900 dark:text-white">{creating ? "Новая запись" : "Изменить запись"}</h2><button onClick={close} aria-label="Закрыть" className="text-gray-500">✕</button></div>
      {editing && editing.usage_count > 0 && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">Эта запись используется в {editing.usage_count} объектах ОС. Её можно деактивировать, но нельзя удалить; для статуса также нельзя менять правило поведения.</p>}
      {creating && <label className="block space-y-1 text-sm text-gray-600 dark:text-gray-300">Код<input value={code} onChange={(e) => setCode(e.target.value)} placeholder="например, electric_locomotive" className={inputClass}/></label>}
      {locales.map(({ id, label }) => <label key={id} className="block space-y-1 text-sm text-gray-600 dark:text-gray-300">{label}<input value={names[id]} onChange={(e) => setNames((old) => ({ ...old, [id]: e.target.value }))} className={inputClass}/></label>)}
      {kind === "statuses" && <label className="block space-y-1 text-sm text-gray-600 dark:text-gray-300">Правило статуса<select value={behavior} onChange={(e) => setBehavior(e.target.value as AssetCatalogBehavior)} className={inputClass}>{Object.entries(behaviorLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
      <label className="block space-y-1 text-sm text-gray-600 dark:text-gray-300">Цвет<select value={color} onChange={(e) => setColor(e.target.value as AssetCatalogColor)} className={inputClass}>{colors.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200"><input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)}/>Активна</label>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <footer className="flex justify-end gap-2"><button onClick={close} className="rounded-lg border px-4 py-2 text-sm dark:border-gray-700">Отмена</button><button disabled={saving} onClick={() => void save()} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{saving ? "Сохранение…" : "Сохранить"}</button></footer>
    </section></div>}
  </main>
}
