"use client"

import { useState, useEffect, useCallback } from "react"
import { Users, Plus, X, Save, Pencil, Trash2, Search, ArrowLeft, MapPin, Briefcase, Hash } from "lucide-react"
import Link from "next/link"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

interface Section {
  id: string
  name: string
}

interface Employee {
  id: string
  tab_number: string
  full_name: string
  position: string
  section_id: string | null
  location_id: string | null
  created_at: string
  section_name?: string
  location_name?: string
}

function AddEmployeeModal({
  onClose,
  onSaved,
  sections,
}: {
  onClose: () => void
  onSaved: () => void
  sections: Section[]
}) {
  const [tabNumber, setTabNumber] = useState("")
  const [fullName, setFullName] = useState("")
  const [position, setPosition] = useState("")
  const [sectionId, setSectionId] = useState("")
  const [locationId, setLocationId] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const handleSave = async () => {
    if (!tabNumber.trim() || !fullName.trim()) {
      setError("Табельный номер и ФИО обязательны")
      return
    }
    setSaving(true)
    setError("")

    const { error: insertError } = await supabase.from("employees").insert({
      tab_number: tabNumber.trim(),
      full_name: fullName.trim(),
      position: position.trim(),
      section_id: sectionId || null,
      location_id: locationId || null,
    })

    if (insertError) {
      setError(insertError.message)
      setSaving(false)
    } else {
      await onSaved()
      setSaving(false)
      onClose()
    }
  }

  const inp =
    "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const sel =
    "w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-base font-bold text-gray-900 dark:text-white">Добавить работника</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Табельный номер *
            </label>
            <input
              value={tabNumber}
              onChange={(e) => setTabNumber(e.target.value)}
              placeholder="12345"
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">ФИО *</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Иванов Иван Иванович"
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Должность</label>
            <input
              value={position}
              onChange={(e) => setPosition(e.target.value)}
              placeholder="Слесарь по ремонту подвижного состава"
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Участок</label>
            <select value={sectionId} onChange={(e) => setSectionId(e.target.value)} className={sel}>
              <option value="">— не указан —</option>
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Локация</label>
            <select value={locationId} onChange={(e) => setLocationId(e.target.value)} className={sel}>
              <option value="">— не указана —</option>
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {error && <p className="text-red-500 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-800">
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={handleSave} disabled={saving} className="gap-2 bg-blue-600 hover:bg-blue-700">
            {saving ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Добавить
          </Button>
        </div>
      </div>
    </div>
  )
}

function EditEmployeeModal({
  employee,
  onClose,
  onSaved,
  sections,
}: {
  employee: Employee
  onClose: () => void
  onSaved: () => void
  sections: Section[]
}) {
  const [tabNumber, setTabNumber] = useState(employee.tab_number)
  const [fullName, setFullName] = useState(employee.full_name)
  const [position, setPosition] = useState(employee.position)
  const [sectionId, setSectionId] = useState(employee.section_id || "")
  const [locationId, setLocationId] = useState(employee.location_id || "")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const handleSave = async () => {
    if (!tabNumber.trim() || !fullName.trim()) {
      setError("Табельный номер и ФИО обязательны")
      return
    }
    setSaving(true)
    setError("")

    const { error: updateError } = await supabase
      .from("employees")
      .update({
        tab_number: tabNumber.trim(),
        full_name: fullName.trim(),
        position: position.trim(),
        section_id: sectionId || null,
        location_id: locationId || null,
      })
      .eq("id", employee.id)

    if (updateError) {
      setError(updateError.message)
      setSaving(false)
    } else {
      await onSaved()
      setSaving(false)
      onClose()
    }
  }

  const inp =
    "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const sel =
    "w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-base font-bold text-gray-900 dark:text-white">Редактировать работника</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Табельный номер *
            </label>
            <input
              value={tabNumber}
              onChange={(e) => setTabNumber(e.target.value)}
              placeholder="12345"
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">ФИО *</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Иванов Иван Иванович"
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Должность</label>
            <input
              value={position}
              onChange={(e) => setPosition(e.target.value)}
              placeholder="Слесарь по ремонту подвижного состава"
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Участок</label>
            <select value={sectionId} onChange={(e) => setSectionId(e.target.value)} className={sel}>
              <option value="">— не указан —</option>
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Локация</label>
            <select value={locationId} onChange={(e) => setLocationId(e.target.value)} className={sel}>
              <option value="">— не указана —</option>
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {error && <p className="text-red-500 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-800">
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={handleSave} disabled={saving} className="gap-2 bg-blue-600 hover:bg-blue-700">
            {saving ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function EmployeesPage() {
  const [employees, setEmployees] = useState<Employee[]>([])
  const [sections, setSections] = useState<Section[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [filterSectionId, setFilterSectionId] = useState("")
  const [showAdd, setShowAdd] = useState(false)
  const [editing, setEditing] = useState<Employee | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const fetchSections = useCallback(async () => {
    const { data } = await supabase.from("sections").select("id, name").order("name")
    setSections((data as Section[]) ?? [])
  }, [])

  const fetchEmployees = useCallback(async () => {
    setLoading(true)
    
    try {
      // ОПТИМИЗАЦИЯ: Параллельная загрузка employees и sections
      let empQuery = supabase.from("employees").select("*").order("full_name")
      if (filterSectionId) {
        empQuery = empQuery.eq("section_id", filterSectionId)
      }

      const [empRes, secRes] = await Promise.all([
        empQuery,
        supabase.from("sections").select("id, name")
      ])

      const emps = (empRes.data as Employee[]) ?? []
      const secMap = new Map((secRes.data ?? []).map((s: Section) => [s.id, s.name]))

      setEmployees(
        emps.map((e) => ({
          ...e,
          section_name: e.section_id ? secMap.get(e.section_id) || "" : "",
          location_name: e.location_id ? secMap.get(e.location_id) || "" : "",
        }))
      )
    } catch (error) {
      console.error("Failed to fetch employees:", error)
      setEmployees([])
    } finally {
      setLoading(false)
    }
  }, [filterSectionId])

  useEffect(() => {
    fetchSections()
  }, [fetchSections])

  useEffect(() => {
    fetchEmployees()
  }, [fetchEmployees])

  const handleDelete = async (id: string) => {
    await supabase.from("employees").delete().eq("id", id)
    setDeleteConfirmId(null)
    fetchEmployees()
  }

  const filtered = employees.filter((e) => {
    const q = search.toLowerCase()
    return (
      !q ||
      e.tab_number.toLowerCase().includes(q) ||
      e.full_name.toLowerCase().includes(q) ||
      e.position.toLowerCase().includes(q) ||
      (e.location_name && e.location_name.toLowerCase().includes(q)) ||
      (e.section_name && e.section_name.toLowerCase().includes(q))
    )
  })

  return (
    <div className="p-8 space-y-6">
      {showAdd && <AddEmployeeModal onClose={() => setShowAdd(false)} onSaved={fetchEmployees} sections={sections} />}
      {editing && (
        <EditEmployeeModal
          employee={editing}
          onClose={() => setEditing(null)}
          onSaved={fetchEmployees}
          sections={sections}
        />
      )}

      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/directories"
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-gray-500" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Users className="w-7 h-7 text-blue-500" />
            Работники
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Справочник сотрудников предприятия</p>
        </div>
        <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={() => setShowAdd(true)}>
          <Plus className="w-4 h-4" /> Добавить работника
        </Button>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">Всего работников</p>
            <Users className="w-4 h-4 text-gray-400" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{employees.length}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">С участком</p>
            <Briefcase className="w-4 h-4 text-gray-400" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
            {employees.filter((e) => e.section_id).length}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">С локацией</p>
            <MapPin className="w-4 h-4 text-gray-400" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
            {employees.filter((e) => e.location).length}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">Участков</p>
            <Hash className="w-4 h-4 text-gray-400" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{sections.length}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по таб. номеру, ФИО, должности..."
            className="pl-9"
          />
        </div>
        <select
          value={filterSectionId}
          onChange={(e) => setFilterSectionId(e.target.value)}
          className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Все участки</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        {(search || filterSectionId) && (
          <button
            onClick={() => {
              setSearch("")
              setFilterSectionId("")
            }}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-gray-400 text-sm gap-3">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            Загрузка...
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Таб. номер</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">ФИО</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Должность</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Участок</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Локация</th>
                <th className="text-right px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center text-gray-400 py-10">
                    Нет работников
                  </td>
                </tr>
              ) : (
                filtered.map((emp) => (
                  <tr key={emp.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-mono text-blue-600 dark:text-blue-400">{emp.tab_number}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center text-blue-700 dark:text-blue-300 font-semibold text-sm flex-shrink-0">
                          {emp.full_name.charAt(0).toUpperCase()}
                        </div>
                        <span className="font-medium text-gray-900 dark:text-white">{emp.full_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{emp.position || "—"}</td>
                    <td className="px-4 py-3">
                      {emp.section_name ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                          {emp.section_name}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {emp.location_name ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                          {emp.location_name}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => setEditing(emp)}
                          className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors"
                        >
                          <Pencil className="w-3.5 h-3.5" /> Изменить
                        </button>
                        {deleteConfirmId === emp.id ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleDelete(emp.id)}
                              className="text-xs font-medium text-red-600 hover:text-red-800 px-2 py-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30"
                            >
                              Да
                            </button>
                            <button
                              onClick={() => setDeleteConfirmId(null)}
                              className="text-xs font-medium text-gray-500 hover:text-gray-700 px-2 py-1"
                            >
                              Нет
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setDeleteConfirmId(emp.id)}
                            className="inline-flex items-center gap-1.5 text-xs font-medium text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 px-2 py-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" /> Удалить
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-600">
        Показано {filtered.length} из {employees.length} работников
        {filterSectionId && sections.find((s) => s.id === filterSectionId)
          ? ` (фильтр: ${sections.find((s) => s.id === filterSectionId)?.name})`
          : ""}
      </p>
    </div>
  )
}
