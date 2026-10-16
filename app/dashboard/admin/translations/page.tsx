"use client"

import { useCallback, useEffect, useState } from "react"
import { api, type TranslationEntity, type TranslationEntry, type TranslationLocale } from "@/lib/api"
import { useLocale } from "@/lib/i18n"

const ENTITIES: { id: TranslationEntity; label: string }[] = [
  { id: "asset_type", label: "Тип ОС" },
  { id: "asset_status", label: "Статус ОС" },
  { id: "department", label: "Подразделение" },
  { id: "section", label: "Участок" },
  { id: "work_type", label: "Вид работ" },
  { id: "work_subtask", label: "Подзадача" },
  { id: "nomenclature", label: "Номенклатура ТМЦ" },
]

const LOCALES: { id: TranslationLocale; label: string }[] = [
  { id: "uz-Latn", label: "O‘zbekcha — lotin" },
  { id: "uz-Cyrl", label: "Ўзбекча — кирилл" },
  { id: "ru", label: "Русский" },
]

export default function TranslationAdminPage() {
  const { t } = useLocale()
  const [entity, setEntity] = useState<TranslationEntity>("section")
  const [rows, setRows] = useState<TranslationEntry[]>([])
  const [drafts, setDrafts] = useState<Record<string, Partial<Record<TranslationLocale, string>>>>({})
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const result = await api.translations.list(entity, { limit: 1000, offset: 0 })
      setRows(result.items)
      setDrafts(Object.fromEntries(result.items.map((row) => [row.id, { ...row.translations }])))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("Не удалось загрузить переводы"))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [entity, t])

  useEffect(() => { void load() }, [load])

  const updateDraft = (id: string, locale: TranslationLocale, value: string) => {
    setDrafts((current) => ({
      ...current,
      [id]: { ...current[id], [locale]: value },
    }))
  }

  const save = async (row: TranslationEntry) => {
    setSavingId(row.id)
    setError("")
    setNotice("")
    try {
      for (const locale of LOCALES) {
        const nextValue = drafts[row.id]?.[locale.id]?.trim() ?? ""
        const oldValue = row.translations[locale.id]
        if (nextValue) await api.translations.set(entity, row.id, locale.id, nextValue)
        else if (oldValue) await api.translations.remove(entity, row.id, locale.id)
      }
      setNotice(t("Перевод сохранён"))
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("Ошибка загрузки"))
    } finally {
      setSavingId(null)
    }
  }

  return (
    <main className="space-y-6 p-6 md:p-8">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("Переводы")}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("Управление переводами справочников")}</p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="translation-entity">{t("Тип данных")}</label>
        <select
          id="translation-entity"
          className="rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900"
          value={entity}
          onChange={(event) => setEntity(event.target.value as TranslationEntity)}
        >
          {ENTITIES.map((item) => <option value={item.id} key={item.id}>{t(item.label)}</option>)}
        </select>
      </div>

      {error && <div role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</div>}
      {notice && <div role="status" className="rounded-md border border-green-300 bg-green-50 p-3 text-sm text-green-700 dark:border-green-900 dark:bg-green-950/30 dark:text-green-300">{notice}</div>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <table className="w-full min-w-[920px] border-collapse text-sm">
          <thead className="bg-gray-50 text-left dark:bg-gray-800/60">
            <tr>
              <th className="p-3 font-semibold">{t("Исходное название")}</th>
              {LOCALES.map((locale) => <th className="p-3 font-semibold" key={locale.id}>{locale.label}</th>)}
              <th className="p-3 font-semibold">{t("Действия")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {loading && <tr><td colSpan={5} className="p-8 text-center text-gray-500">{t("Загрузка...")}</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-gray-500">{t("Нет данных")}</td></tr>}
            {!loading && rows.map((row) => (
              <tr key={row.id}>
                <td className="max-w-64 p-3 align-top">
                  <div className="font-medium text-gray-900 dark:text-white">{row.source_name}</div>
                  <div className="mt-1 text-xs text-gray-400">{row.id}</div>
                </td>
                {LOCALES.map((locale) => (
                  <td className="min-w-52 p-3 align-top" key={locale.id}>
                    <input
                      value={drafts[row.id]?.[locale.id] ?? ""}
                      onChange={(event) => updateDraft(row.id, locale.id, event.target.value)}
                      aria-label={`${locale.label}: ${row.source_name}`}
                      placeholder={t("Перевод не задан")}
                      className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-950"
                    />
                    {row.missing_locales.includes(locale.id) && <span className="mt-1 block text-xs text-amber-700 dark:text-amber-400">{t("Перевод не задан")}</span>}
                  </td>
                ))}
                <td className="p-3 align-top">
                  <button
                    type="button"
                    onClick={() => void save(row)}
                    disabled={savingId === row.id}
                    className="rounded-md bg-blue-600 px-3 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {savingId === row.id ? t("Ожидание") : t("Сохранить перевод")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!loading && rows.length > 0 && <p className="text-xs text-gray-500">{rows.length} / 1000</p>}
    </main>
  )
}
