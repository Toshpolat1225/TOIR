"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ArrowLeft, Building2, ChevronRight, Pencil, Plus, RotateCcw, Search } from "@/components/ui/icons"
import Link from "next/link"
import { api, type SectionTreeNode } from "@/lib/api"
import { useLocale } from "@/lib/i18n"
import { Button } from "@/components/ui/button"

type UnitType = "department" | "division" | "section" | "team"
type UnitNames = Record<"ru" | "uz-Latn" | "uz-Cyrl", string>

const unitTypes: UnitType[] = ["department", "division", "section", "team"]
const typeLabels: Record<UnitType, string> = {
  department: "Подразделение",
  division: "Дирекция",
  section: "Участок",
  team: "Бригада",
}
const allowedParentTypes: Record<UnitType, UnitType[]> = {
  department: [],
  division: ["department", "division"],
  section: ["department", "division", "section"],
  team: ["division", "section", "team"],
}

function flattenTree(items: SectionTreeNode[]): SectionTreeNode[] {
  return items.flatMap((item) => [item, ...flattenTree(item.children ?? [])])
}

function collectDescendants(item: SectionTreeNode): Set<string> {
  return new Set([item.id, ...flattenTree(item.children ?? []).map((child) => child.id)])
}

function renderTree(
  items: SectionTreeNode[],
  locale: string,
  depth: number,
  onEdit: (item: SectionTreeNode) => void,
  onArchive: (item: SectionTreeNode) => void,
  onRestore: (item: SectionTreeNode) => void,
): React.ReactNode {
  return items.map((item) => {
    const type = (item.unit_type ?? "section") as UnitType
    const name = item.translations?.[locale as keyof UnitNames] ?? item.localized_name ?? item.name
    return (
      <li key={item.id} className="list-none">
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
          style={{ marginLeft: depth * 18 }}
        >
          <div className="flex min-w-0 items-center gap-2">
            <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
            <span className="truncate text-sm font-medium text-gray-900 dark:text-white">{name}</span>
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600 dark:bg-gray-800 dark:text-gray-300">
              {typeLabels[type] ?? type}
            </span>
            {item.code && <span className="text-xs text-gray-500">{item.code}</span>}
            {item.is_archived && <span className="text-xs text-amber-600">Архив</span>}
            {item.is_active === false && <span className="text-xs text-gray-500">Неактивно</span>}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => onEdit(item)} aria-label="Изменить">
              <Pencil className="h-4 w-4" />
            </Button>
            {item.is_archived ? (
              <Button variant="ghost" size="sm" onClick={() => onRestore(item)}>
                <RotateCcw className="mr-1 h-4 w-4" /> Восстановить
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onArchive(item)}
                className="text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-900/20"
              >
                В архив
              </Button>
            )}
          </div>
        </div>
        {item.children?.length ? (
          <ul className="mt-2 space-y-2">
            {renderTree(item.children, locale, depth + 1, onEdit, onArchive, onRestore)}
          </ul>
        ) : null}
      </li>
    )
  })
}

export default function SectionsPage() {
  const { locale } = useLocale()
  const [tree, setTree] = useState<SectionTreeNode[]>([])
  const [parentOptions, setParentOptions] = useState<SectionTreeNode[]>([])
  const [loading, setLoading] = useState(true)
  const [names, setNames] = useState<UnitNames>({ ru: "", "uz-Latn": "", "uz-Cyrl": "" })
  const [parentId, setParentId] = useState("")
  const [unitType, setUnitType] = useState<UnitType>("section")
  const [code, setCode] = useState("")
  const [isActive, setIsActive] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [query, setQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState("")
  const [activeFilter, setActiveFilter] = useState("")
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState("")

  const fetchSections = useCallback(async () => {
    setLoading(true)
    try {
      const [filtered, selectable] = await Promise.all([
        api.sections.tree({
          include_archived: showArchived,
          q: query.trim() || undefined,
          unit_type: typeFilter || undefined,
          is_active: activeFilter === "" ? undefined : activeFilter === "active",
        }),
        api.sections.tree(),
      ])
      setTree(filtered)
      setParentOptions(selectable)
      setError("")
    } catch (err) {
      console.error("Failed to fetch section hierarchy:", err)
      setError(err instanceof Error ? err.message : "Не удалось загрузить структуру")
      setTree([])
      setParentOptions([])
    } finally {
      setLoading(false)
    }
  }, [activeFilter, query, showArchived, typeFilter])

  useEffect(() => {
    void fetchSections()
  }, [fetchSections])

  const selectableParents = useMemo(() => {
    const editingItem = editingId
      ? flattenTree(parentOptions).find((item) => item.id === editingId)
      : undefined
    const excluded = editingItem ? collectDescendants(editingItem) : new Set<string>()
    return flattenTree(parentOptions).filter((item) =>
      item.id !== editingId
      && !excluded.has(item.id)
      && !item.is_archived
      && allowedParentTypes[unitType].includes((item.unit_type ?? "section") as UnitType),
    )
  }, [editingId, parentOptions, unitType])

  const resetForm = () => {
    setNames({ ru: "", "uz-Latn": "", "uz-Cyrl": "" })
    setParentId("")
    setUnitType("section")
    setCode("")
    setIsActive(true)
    setEditingId(null)
  }

  const handleEdit = (item: SectionTreeNode) => {
    setEditingId(item.id)
    setNames({
      ru: item.translations?.ru ?? item.name,
      "uz-Latn": item.translations?.["uz-Latn"] ?? "",
      "uz-Cyrl": item.translations?.["uz-Cyrl"] ?? "",
    })
    setParentId(item.parent_id ?? "")
    setUnitType((item.unit_type ?? "section") as UnitType)
    setCode(item.code ?? "")
    setIsActive(item.is_active !== false)
    setError("")
  }

  const handleSave = async () => {
    const translations: UnitNames = {
      ru: names.ru.trim(),
      "uz-Latn": names["uz-Latn"].trim(),
      "uz-Cyrl": names["uz-Cyrl"].trim(),
    }
    if (Object.values(translations).some((name) => !name)) {
      setError("Заполните названия на русском и двух узбекских языках")
      return
    }

    setSaving(true)
    setError("")
    try {
      const data = {
        name: translations.ru,
        parent_id: parentId || null,
        unit_type: unitType,
        code: code.trim() || null,
        translations,
        is_active: isActive,
      }
      if (editingId) {
        await api.sections.update(editingId, data)
      } else {
        await api.sections.create(data)
      }
      resetForm()
      await fetchSections()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить подразделение")
    } finally {
      setSaving(false)
    }
  }

  const handleArchive = async (item: SectionTreeNode) => {
    if (!confirm("Переместить подразделение в архив? Исторические записи сохранят эту связь.")) return
    try {
      await api.sections.remove(item.id)
      await fetchSections()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось архивировать подразделение")
    }
  }

  const handleRestore = async (item: SectionTreeNode) => {
    try {
      await api.sections.update(item.id, { is_archived: false })
      await fetchSections()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось восстановить подразделение")
    }
  }

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/directories" className="rounded-lg p-2 transition-colors hover:bg-gray-100 dark:hover:bg-gray-800">
          <ArrowLeft className="h-5 w-5 text-gray-500" />
        </Link>
        <div className="flex-1">
          <h1 className="flex items-center gap-3 text-2xl font-bold text-gray-900 dark:text-white">
            <Building2 className="h-7 w-7 text-green-500" />
            Динамическая иерархия участков
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Многоуровневая структура с названиями на трех языках.
          </p>
        </div>
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200">
          <Plus className="h-4 w-4" /> {editingId ? "Изменить подразделение" : "Добавить подразделение"}
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {([
            ["ru", "Название на русском"],
            ["uz-Latn", "O‘zbekcha (lotin)"],
            ["uz-Cyrl", "Ўзбекча (кирилл)"],
          ] as const).map(([language, label]) => (
            <label key={language} className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {label}
              <input
                value={names[language]}
                onChange={(event) => setNames((current) => ({ ...current, [language]: event.target.value }))}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              />
            </label>
          ))}
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Родительское подразделение
            <select
              value={parentId}
              onChange={(event) => setParentId(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="">— корневой узел —</option>
              {selectableParents.map((item) => (
                <option key={item.id} value={item.id}>
                  [{typeLabels[(item.unit_type ?? "section") as UnitType]}]
                  {item.translations?.[locale as keyof UnitNames] ?? item.localized_name ?? item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Тип
            <select
              value={unitType}
              onChange={(event) => {
                const nextType = event.target.value as UnitType
                setUnitType(nextType)
                if (parentId && !allowedParentTypes[nextType].some((type) =>
                  selectableParents.some((parent) => parent.id === parentId && parent.unit_type === type),
                )) {
                  setParentId("")
                }
              }}
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              {unitTypes.map((type) => <option key={type} value={type}>{typeLabels[type]}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Код
            <input
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
          </label>
          <label className="flex items-center gap-2 self-end pb-2 text-sm text-gray-600 dark:text-gray-300">
            <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
            Активно
          </label>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Button onClick={() => void handleSave()} disabled={saving} className="gap-2 bg-blue-600 hover:bg-blue-700">
            <Plus className="h-4 w-4" /> {saving ? "Сохранение..." : editingId ? "Сохранить" : "Добавить"}
          </Button>
          {editingId && <Button variant="ghost" onClick={resetForm}>Отмена</Button>}
        </div>
        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="grid gap-3 md:grid-cols-[1fr_200px_180px_auto]">
          <label className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Поиск по названию или переводу"
              className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm dark:border-gray-600 dark:bg-gray-800"
            />
          </label>
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800">
            <option value="">Все типы</option>
            {unitTypes.map((type) => <option key={type} value={type}>{typeLabels[type]}</option>)}
          </select>
          <select value={activeFilter} onChange={(event) => setActiveFilter(event.target.value)} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800">
            <option value="">Любой статус</option>
            <option value="active">Активные</option>
            <option value="inactive">Неактивные</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
            <input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} />
            Показать архив
          </label>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <div className="flex items-center gap-2 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
          <Building2 className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">Дерево участков</span>
        </div>
        {loading ? (
          <div className="py-12 text-center text-sm text-gray-400">Загрузка...</div>
        ) : tree.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-500">Нет подразделений для выбранного фильтра.</div>
        ) : (
          <ul className="space-y-2 p-4">
            {renderTree(tree, locale, 0, handleEdit, handleArchive, handleRestore)}
          </ul>
        )}
      </section>
    </div>
  )
}
