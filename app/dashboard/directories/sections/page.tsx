"use client"

import { useState, useEffect, useCallback } from "react"
import { Building2, Plus, Trash2, ArrowLeft, ChevronRight } from "@/components/ui/icons"
import Link from "next/link"
import { api, type SectionTreeNode } from "@/lib/api"
import { Button } from "@/components/ui/button"

function renderTree(items: SectionTreeNode[], depth = 0, onDelete?: (id: string) => void): React.ReactNode {
  return items.map((item) => (
    <li key={item.id} className="list-none">
      <div
        className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
        style={{ marginLeft: depth * 18 }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <ChevronRight className="h-4 w-4 text-gray-400" />
          <span className="truncate text-sm font-medium text-gray-900 dark:text-white">{item.name}</span>
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] uppercase text-gray-600 dark:bg-gray-800 dark:text-gray-300">
            {item.unit_type ?? "section"}
          </span>
        </div>
        {onDelete ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void onDelete(item.id)}
            className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
      {item.children?.length ? <ul className="mt-2 space-y-2">{renderTree(item.children, depth + 1, onDelete)}</ul> : null}
    </li>
  ))
}

export default function SectionsPage() {
  const [tree, setTree] = useState<SectionTreeNode[]>([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState("")
  const [newParentId, setNewParentId] = useState<string>("")
  const [newUnitType, setNewUnitType] = useState("section")
  const [newCode, setNewCode] = useState("")
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState("")

  const fetchSections = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.sections.tree()
      setTree(response)
      setError("")
    } catch (err) {
      console.error("Failed to fetch section hierarchy:", err)
      setError(err instanceof Error ? err.message : "Failed to load hierarchy")
      setTree([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchSections()
  }, [fetchSections])

  const handleAdd = async () => {
    const name = newName.trim()
    if (!name) {
      setError("Введите название участка")
      return
    }
    setAdding(true)
    setError("")
    try {
      await api.sections.create({
        name,
        parent_id: newParentId || null,
        unit_type: newUnitType,
        code: newCode.trim() || null,
      })
      setNewName("")
      setNewParentId("")
      setNewUnitType("section")
      setNewCode("")
      await fetchSections()
    } catch (err) {
      const message = err instanceof Error ? err.message : "An unknown error occurred"
      setError(message)
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm("Удалить этот участок? Он будет недоступен для новых записей, но существующие связи остаются.")) {
      return
    }
    try {
      await api.sections.remove(id)
      await fetchSections()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete section")
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
            Родительский узел, тип подразделения и древовидная структура.
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200">
          <Plus className="h-4 w-4" /> Добавить узел
        </h2>
        <div className="grid gap-3 md:grid-cols-5">
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Название</label>
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void handleAdd()}
              placeholder="Например: ТЧЭ-1"
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Родитель</label>
            <select
              value={newParentId}
              onChange={(event) => setNewParentId(event.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="">— корневой —</option>
              {tree.flatMap((node) => flattenTree(node)).map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Тип</label>
            <select
              value={newUnitType}
              onChange={(event) => setNewUnitType(event.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="department">department</option>
              <option value="division">division</option>
              <option value="section">section</option>
              <option value="team">team</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Код</label>
            <input
              value={newCode}
              onChange={(event) => setNewCode(event.target.value)}
              placeholder="OPTIONAL"
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Button onClick={() => void handleAdd()} disabled={adding} className="gap-2 bg-blue-600 hover:bg-blue-700">
            {adding ? <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> : <Plus className="h-4 w-4" />}
            Добавить
          </Button>
        </div>
        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <div className="flex items-center gap-2 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
          <Building2 className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">Дерево участков</span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-400">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            Загрузка...
          </div>
        ) : tree.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-500">Нет узлов. Добавьте первый раздел.</div>
        ) : (
          <ul className="space-y-2 p-4">{renderTree(tree, 0, handleDelete)}</ul>
        )}
      </div>
    </div>
  )
}

function flattenTree(node: SectionTreeNode): SectionTreeNode[] {
  return [node, ...node.children.flatMap((child) => flattenTree(child))]
}
