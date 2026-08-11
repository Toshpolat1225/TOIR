"use client"

import { useState, useEffect, useCallback } from "react"
import { Building2, Plus, Trash2, ArrowLeft } from "lucide-react"
import Link from "next/link"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"

type SectionRow = { id: string; name: string; created_at: string }

export default function SectionsPage() {
  const [list, setList] = useState<SectionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState("")
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState("")

  const fetchSections = useCallback(async () => {
    setLoading(true)
    const { data, error: e } = await supabase
      .from("sections")
      .select("id,name,created_at")
      .order("name", { ascending: true })
    if (!e && data) setList(data as SectionRow[])
    else setList([])
    setLoading(false)
  }, [])

  useEffect(() => { fetchSections() }, [fetchSections])

  const handleAdd = async () => {
    const name = newName.trim()
    if (!name) {
      setError("Введите название участка")
      return
    }
    setAdding(true)
    setError("")
    const { error: e } = await supabase.from("sections").insert({ name })
    if (e) {
      if (e.code === "23505") setError("Участок с таким названием уже есть")
      else setError(e.message)
      setAdding(false)
      return
    }
    setNewName("")
    fetchSections()
    setAdding(false)
  }

  const handleDelete = async (id: string) => {
    if (!confirm("Удалить этот участок? Пользователи и наряды с этим участком останутся, но выбор участка будет недоступен для новых записей.")) return
    const { error: e } = await supabase.from("sections").delete().eq("id", id)
    if (!e) fetchSections()
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/directories"
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-gray-500" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Building2 className="w-7 h-7 text-green-500" />
            Участки
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Справочник участков для нарядов и пользователей</p>
        </div>
      </div>

      {/* Добавить участок */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-4 flex items-center gap-2">
          <Plus className="w-4 h-4"/> Добавить участок
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Название участка</label>
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAdd()}
              placeholder="Например: Участок № 1, ТЧЭ-1 Лихоборы"
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <Button onClick={handleAdd} disabled={adding} className="gap-2 bg-blue-600 hover:bg-blue-700">
            {adding ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/> : <Plus className="w-4 h-4"/>}
            Добавить
          </Button>
        </div>
        {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
      </div>

      {/* Список */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center gap-2">
          <Building2 className="w-4 h-4 text-gray-500"/>
          <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">Список участков</span>
          <span className="text-xs text-gray-400 ml-2">({list.length})</span>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-12 text-gray-400 text-sm gap-2">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
            Загрузка...
          </div>
        ) : list.length === 0 ? (
          <div className="py-12 text-center text-gray-500 text-sm">
            Нет участков. Добавьте первый участок выше.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {list.map(s => (
              <li key={s.id} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <span className="text-sm font-medium text-gray-900 dark:text-white">{s.name}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(s.id)}
                  className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                >
                  <Trash2 className="w-4 h-4"/>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
