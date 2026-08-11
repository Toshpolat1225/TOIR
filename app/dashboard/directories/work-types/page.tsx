"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Wrench, Plus, X, Save, Pencil, Trash2, ArrowLeft, Package,
  ChevronDown, ChevronRight, ListTodo, Search
} from "lucide-react"
import Link from "next/link"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

interface WorkType {
  id: string
  code: string
  name: string
  description: string
  unit_type: "locomotive" | "wagon"
  sort_order: number
}

interface WorkSubtask {
  id: string
  work_type_id: string
  name: string
  description: string
  sort_order: number
}

interface WorkTypeTmc {
  id: string
  work_type_id: string
  name: string
  inv_no: string
  unit: string
  qty: number
  note: string
  sort_order: number
}

interface NomenclatureItem {
  id: string
  name: string
  code: string
  unit: string
  department_id: string | null
}

const UNITS = ["шт.", "кг.", "м.", "л.", "уп.", "рул.", "кан.", "к-т"]

function AddWorkTypeModal({
  onClose,
  onSaved,
}: {
  onClose: () => void
  onSaved: () => void
}) {
  const [code, setCode] = useState("")
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [unitType, setUnitType] = useState<"locomotive" | "wagon">("locomotive")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const handleSave = async () => {
    if (!code.trim() || !name.trim()) {
      setError("Код и название обязательны")
      return
    }
    setSaving(true)
    setError("")

    const { error: insertError } = await supabase.from("work_types").insert({
      code: code.trim().toUpperCase(),
      name: name.trim(),
      description: description.trim(),
      unit_type: unitType,
    })

    if (insertError) {
      if (insertError.code === "23505") {
        setError("Вид работ с таким кодом уже существует")
      } else {
        setError(insertError.message)
      }
      setSaving(false)
    } else {
      await onSaved()
      setSaving(false)
      onClose()
    }
  }

  const inp = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const sel = "w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-base font-bold text-gray-900 dark:text-white">Добавить вид работ</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Код *</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="ТО-1, ТР-2, КР..."
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Название *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Техническое обслуживание №1"
              className={inp}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Описание вида работ..."
              rows={2}
              className={inp + " resize-none"}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Тип ТПС</label>
            <select value={unitType} onChange={(e) => setUnitType(e.target.value as "locomotive" | "wagon")} className={sel}>
              <option value="locomotive">Локомотив</option>
              <option value="wagon">Вагон</option>
            </select>
          </div>

          {error && <p className="text-red-500 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-800">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={handleSave} disabled={saving} className="gap-2 bg-blue-600 hover:bg-blue-700">
            {saving ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Plus className="w-4 h-4" />}
            Добавить
          </Button>
        </div>
      </div>
    </div>
  )
}

function SubtaskRow({
  subtask,
  onUpdate,
  onDelete,
}: {
  subtask: WorkSubtask
  onUpdate: (s: WorkSubtask) => void
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(subtask.name)

  const handleSave = () => {
    if (name.trim()) {
      onUpdate({ ...subtask, name: name.trim() })
    }
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 py-1">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          autoFocus
          className="flex-1 border border-blue-400 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 focus:outline-none"
        />
        <button onClick={handleSave} className="p-1 text-green-600 hover:bg-green-50 rounded">
          <Save className="w-3.5 h-3.5" />
        </button>
        <button onClick={() => { setName(subtask.name); setEditing(false) }} className="p-1 text-gray-400 hover:bg-gray-100 rounded">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 py-1 group">
      <span className="flex-1 text-sm text-gray-700 dark:text-gray-300">{subtask.name}</span>
      <button onClick={() => setEditing(true)} className="p-1 text-gray-400 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity">
        <Pencil className="w-3 h-3" />
      </button>
      <button onClick={onDelete} className="p-1 text-gray-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity">
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  )
}

function TmcRow({
  tmc,
  onUpdate,
  onDelete,
}: {
  tmc: WorkTypeTmc
  onUpdate: (t: WorkTypeTmc) => void
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(tmc.name)
  const [invNo, setInvNo] = useState(tmc.inv_no)
  const [unit, setUnit] = useState(tmc.unit)
  const [qty, setQty] = useState(String(tmc.qty))
  const [note, setNote] = useState(tmc.note)

  const handleSave = () => {
    if (name.trim()) {
      onUpdate({ ...tmc, name: name.trim(), inv_no: invNo.trim(), unit, qty: Number(qty) || 1, note: note.trim() })
    }
    setEditing(false)
  }

  if (editing) {
    return (
      <tr className="bg-blue-50/50 dark:bg-blue-950/20">
        <td className="px-2 py-1">
          <input value={name} onChange={(e) => setName(e.target.value)} className="w-full border border-blue-400 rounded px-2 py-1 text-xs" placeholder="Наименование" />
        </td>
        <td className="px-2 py-1">
          <input value={invNo} onChange={(e) => setInvNo(e.target.value)} className="w-full border border-gray-300 rounded px-2 py-1 text-xs font-mono" placeholder="МТР-00000" />
        </td>
        <td className="px-2 py-1">
          <select value={unit} onChange={(e) => setUnit(e.target.value)} className="w-full border border-gray-300 rounded px-1 py-1 text-xs">
            {UNITS.map(u => <option key={u}>{u}</option>)}
          </select>
        </td>
        <td className="px-2 py-1">
          <input type="number" min="0" value={qty} onChange={(e) => setQty(e.target.value)} className="w-full border border-gray-300 rounded px-2 py-1 text-xs" />
        </td>
        <td className="px-2 py-1">
          <input value={note} onChange={(e) => setNote(e.target.value)} className="w-full border border-gray-300 rounded px-2 py-1 text-xs" placeholder="Примечание" />
        </td>
        <td className="px-2 py-1 text-center">
          <button onClick={handleSave} className="p-1 text-green-600 hover:bg-green-50 rounded"><Save className="w-3.5 h-3.5" /></button>
          <button onClick={() => setEditing(false)} className="p-1 text-gray-400 hover:bg-gray-100 rounded"><X className="w-3.5 h-3.5" /></button>
        </td>
      </tr>
    )
  }

  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/50 group">
      <td className="px-2 py-1.5 text-xs text-gray-900 dark:text-white">{tmc.name}</td>
      <td className="px-2 py-1.5 text-xs font-mono text-gray-500">{tmc.inv_no || "—"}</td>
      <td className="px-2 py-1.5 text-xs text-gray-500 text-center">{tmc.unit}</td>
      <td className="px-2 py-1.5 text-xs text-gray-900 dark:text-white text-center font-medium">{tmc.qty}</td>
      <td className="px-2 py-1.5 text-xs text-gray-400">{tmc.note || "—"}</td>
      <td className="px-2 py-1.5 text-center">
        <button onClick={() => setEditing(true)} className="p-1 text-gray-400 hover:text-blue-600 opacity-0 group-hover:opacity-100"><Pencil className="w-3 h-3" /></button>
        <button onClick={onDelete} className="p-1 text-gray-400 hover:text-red-600 opacity-0 group-hover:opacity-100"><Trash2 className="w-3 h-3" /></button>
      </td>
    </tr>
  )
}

function NomenclatureCombobox({
  value,
  onChange,
  onSelect,
  nomenclature,
}: {
  value: string
  onChange: (v: string) => void
  onSelect: (item: NomenclatureItem) => void
  nomenclature: NomenclatureItem[]
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(value)

  useEffect(() => { setQuery(value) }, [value])

  const filtered = query.length === 0
    ? nomenclature.slice(0, 50)
    : nomenclature.filter(i =>
        i.name.toLowerCase().includes(query.toLowerCase()) ||
        i.code.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 50)

  return (
    <div className="relative w-full">
      <input
        value={query}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        onChange={e => { setQuery(e.target.value); onChange(e.target.value); setOpen(true) }}
        placeholder="Выберите из справочника или введите..."
        className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-xs bg-white dark:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full max-h-48 overflow-auto bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl">
          {filtered.map(item => (
            <button
              key={item.id}
              type="button"
              onMouseDown={e => {
                e.preventDefault()
                onSelect(item)
                setQuery(item.name)
                setOpen(false)
              }}
              className="w-full text-left px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 transition-colors flex items-center gap-2"
            >
              <span className="flex-1 text-xs text-gray-900 dark:text-white truncate">{item.name}</span>
              <span className="text-[10px] font-mono text-gray-400">{item.code}</span>
              <span className="text-[10px] text-gray-400">{item.unit}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function WorkTypeCard({
  workType,
  subtasks,
  tmcItems,
  onDelete,
  onUpdate,
  onSubtasksChange,
  onTmcChange,
  nomenclature,
}: {
  workType: WorkType
  subtasks: WorkSubtask[]
  tmcItems: WorkTypeTmc[]
  onDelete: () => void
  onUpdate: (wt: WorkType) => void
  onSubtasksChange: (subtasks: WorkSubtask[]) => void
  onTmcChange: (tmc: WorkTypeTmc[]) => void
  nomenclature: NomenclatureItem[]
}) {
  const [expanded, setExpanded] = useState(false)
  const [newSubtask, setNewSubtask] = useState("")
  const [addingSubtask, setAddingSubtask] = useState(false)
  const [addingTmc, setAddingTmc] = useState(false)
  const [newTmc, setNewTmc] = useState({ name: "", inv_no: "", unit: "шт.", qty: "1", note: "" })

  const handleSelectNomenclature = (item: NomenclatureItem) => {
    setNewTmc({
      ...newTmc,
      name: item.name,
      inv_no: item.code,
      unit: item.unit || "шт.",
    })
  }

  const handleAddSubtask = async () => {
    if (!newSubtask.trim()) return
    setAddingSubtask(true)
    const { data, error } = await supabase
      .from("work_subtasks")
      .insert({ work_type_id: workType.id, name: newSubtask.trim(), sort_order: subtasks.length })
      .select()
      .single()
    if (!error && data) {
      onSubtasksChange([...subtasks, data as WorkSubtask])
    }
    setNewSubtask("")
    setAddingSubtask(false)
  }

  const handleUpdateSubtask = async (updated: WorkSubtask) => {
    await supabase.from("work_subtasks").update({ name: updated.name }).eq("id", updated.id)
    onSubtasksChange(subtasks.map(s => s.id === updated.id ? updated : s))
  }

  const handleDeleteSubtask = async (id: string) => {
    await supabase.from("work_subtasks").delete().eq("id", id)
    onSubtasksChange(subtasks.filter(s => s.id !== id))
  }

  const handleAddTmc = async () => {
    if (!newTmc.name.trim()) return
    const { data, error } = await supabase
      .from("work_type_tmc")
      .insert({
        work_type_id: workType.id,
        name: newTmc.name.trim(),
        inv_no: newTmc.inv_no.trim(),
        unit: newTmc.unit,
        qty: Number(newTmc.qty) || 1,
        note: newTmc.note.trim(),
        sort_order: tmcItems.length,
      })
      .select()
      .single()
    if (!error && data) {
      onTmcChange([...tmcItems, data as WorkTypeTmc])
    }
    setNewTmc({ name: "", inv_no: "", unit: "шт.", qty: "1", note: "" })
    setAddingTmc(false)
  }

  const handleUpdateTmc = async (updated: WorkTypeTmc) => {
    await supabase.from("work_type_tmc").update({
      name: updated.name,
      inv_no: updated.inv_no,
      unit: updated.unit,
      qty: updated.qty,
      note: updated.note,
    }).eq("id", updated.id)
    onTmcChange(tmcItems.map(t => t.id === updated.id ? updated : t))
  }

  const handleDeleteTmc = async (id: string) => {
    await supabase.from("work_type_tmc").delete().eq("id", id)
    onTmcChange(tmcItems.filter(t => t.id !== id))
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
        onClick={() => setExpanded(!expanded)}
      >
        <button className="p-1">
          {expanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
        </button>
        <div className="w-14 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
          <span className="text-xs font-bold text-white">{workType.code}</span>
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 dark:text-white text-sm">{workType.name}</p>
          {workType.description && (
            <p className="text-xs text-gray-500 truncate">{workType.description}</p>
          )}
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
          workType.unit_type === "wagon"
            ? "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
            : "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300"
        }`}>
          {workType.unit_type === "wagon" ? "Вагон" : "Локомотив"}
        </span>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span className="flex items-center gap-1"><ListTodo className="w-3 h-3" />{subtasks.length}</span>
          <span className="flex items-center gap-1"><Package className="w-3 h-3" />{tmcItems.length}</span>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {expanded && (
        <div className="border-t border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-2 divide-x divide-gray-200 dark:divide-gray-700">
            {/* Подзадачи */}
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
                  <ListTodo className="w-3.5 h-3.5" /> Подзадачи
                </h4>
                <span className="text-xs text-gray-400">{subtasks.length} шт.</span>
              </div>

              <div className="space-y-1 mb-3 max-h-48 overflow-y-auto">
                {subtasks.length === 0 && (
                  <p className="text-xs text-gray-400 py-2">Нет подзадач</p>
                )}
                {subtasks.map((s) => (
                  <SubtaskRow
                    key={s.id}
                    subtask={s}
                    onUpdate={handleUpdateSubtask}
                    onDelete={() => handleDeleteSubtask(s.id)}
                  />
                ))}
              </div>

              <div className="flex gap-2">
                <input
                  value={newSubtask}
                  onChange={(e) => setNewSubtask(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddSubtask()}
                  placeholder="Новая подзадача..."
                  className="flex-1 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <Button size="sm" onClick={handleAddSubtask} disabled={addingSubtask || !newSubtask.trim()}>
                  <Plus className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>

            {/* ТМЦ */}
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
                  <Package className="w-3.5 h-3.5" /> Шаблон ТМЦ
                </h4>
                <span className="text-xs text-gray-400">{tmcItems.length} поз.</span>
              </div>

              <div className="max-h-48 overflow-y-auto mb-3">
                {tmcItems.length === 0 && !addingTmc && (
                  <p className="text-xs text-gray-400 py-2">Нет позиций ТМЦ</p>
                )}
                {tmcItems.length > 0 && (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="text-left px-2 py-1 text-gray-500 font-medium">Наименование</th>
                        <th className="text-left px-2 py-1 text-gray-500 font-medium">Инв. №</th>
                        <th className="text-center px-2 py-1 text-gray-500 font-medium">Ед.</th>
                        <th className="text-center px-2 py-1 text-gray-500 font-medium">Кол.</th>
                        <th className="text-left px-2 py-1 text-gray-500 font-medium">Прим.</th>
                        <th className="w-16"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {tmcItems.map((t) => (
                        <TmcRow
                          key={t.id}
                          tmc={t}
                          onUpdate={handleUpdateTmc}
                          onDelete={() => handleDeleteTmc(t.id)}
                        />
                      ))}
                    </tbody>
                  </table>
                )}

                {addingTmc && (
                  <div className="border border-blue-300 rounded-lg p-3 bg-blue-50/50 dark:bg-blue-950/20 space-y-2 mt-2">
                    <div>
                      <label className="block text-[10px] font-medium text-gray-500 mb-1">Наименование ТМЦ (из справочника)</label>
                      <NomenclatureCombobox
                        value={newTmc.name}
                        onChange={(v) => setNewTmc({ ...newTmc, name: v })}
                        onSelect={handleSelectNomenclature}
                        nomenclature={nomenclature}
                      />
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                      <div>
                        <label className="block text-[10px] font-medium text-gray-500 mb-1">Код</label>
                        <input
                          value={newTmc.inv_no}
                          onChange={(e) => setNewTmc({ ...newTmc, inv_no: e.target.value })}
                          placeholder="Код"
                          className="w-full border border-gray-300 rounded px-2 py-1 text-xs font-mono bg-gray-50"
                          readOnly
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-medium text-gray-500 mb-1">Ед. изм.</label>
                        <select
                          value={newTmc.unit}
                          onChange={(e) => setNewTmc({ ...newTmc, unit: e.target.value })}
                          className="w-full border border-gray-300 rounded px-1 py-1 text-xs"
                        >
                          {UNITS.map(u => <option key={u}>{u}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[10px] font-medium text-gray-500 mb-1">Кол-во</label>
                        <input
                          type="number"
                          min="0"
                          value={newTmc.qty}
                          onChange={(e) => setNewTmc({ ...newTmc, qty: e.target.value })}
                          placeholder="1"
                          className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-medium text-gray-500 mb-1">Примечание</label>
                        <input
                          value={newTmc.note}
                          onChange={(e) => setNewTmc({ ...newTmc, note: e.target.value })}
                          placeholder="—"
                          className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="outline" onClick={() => { setAddingTmc(false); setNewTmc({ name: "", inv_no: "", unit: "шт.", qty: "1", note: "" }) }}>Отмена</Button>
                      <Button size="sm" onClick={handleAddTmc} disabled={!newTmc.name.trim()}>Добавить</Button>
                    </div>
                  </div>
                )}
              </div>

              {!addingTmc && (
                <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => setAddingTmc(true)}>
                  <Plus className="w-3.5 h-3.5" /> Добавить ТМЦ
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function WorkTypesPage() {
  const [workTypes, setWorkTypes] = useState<WorkType[]>([])
  const [subtasksMap, setSubtasksMap] = useState<Record<string, WorkSubtask[]>>({})
  const [tmcMap, setTmcMap] = useState<Record<string, WorkTypeTmc[]>>({})
  const [nomenclature, setNomenclature] = useState<NomenclatureItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [search, setSearch] = useState("")
  const [filterUnitType, setFilterUnitType] = useState("")

  const fetchNomenclature = useCallback(async () => {
    const { data } = await supabase
      .from("nomenclature")
      .select("id, name, code, unit, department_id")
      .order("name")
    setNomenclature((data as NomenclatureItem[]) ?? [])
  }, [])

  const fetchData = useCallback(async () => {
    setLoading(true)

    const { data: wtData } = await supabase
      .from("work_types")
      .select("*")
      .order("sort_order")
      .order("code")

    const types = (wtData as WorkType[]) ?? []
    setWorkTypes(types)

    if (types.length > 0) {
      const ids = types.map(t => t.id)

      const { data: stData } = await supabase
        .from("work_subtasks")
        .select("*")
        .in("work_type_id", ids)
        .order("sort_order")

      const stMap: Record<string, WorkSubtask[]> = {}
      for (const st of (stData ?? []) as WorkSubtask[]) {
        if (!stMap[st.work_type_id]) stMap[st.work_type_id] = []
        stMap[st.work_type_id].push(st)
      }
      setSubtasksMap(stMap)

      const { data: tmcData } = await supabase
        .from("work_type_tmc")
        .select("*")
        .in("work_type_id", ids)
        .order("sort_order")

      const tMap: Record<string, WorkTypeTmc[]> = {}
      for (const t of (tmcData ?? []) as WorkTypeTmc[]) {
        if (!tMap[t.work_type_id]) tMap[t.work_type_id] = []
        tMap[t.work_type_id].push(t)
      }
      setTmcMap(tMap)
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    fetchNomenclature()
  }, [fetchData, fetchNomenclature])

  const handleDelete = async (id: string) => {
    if (!confirm("Удалить этот вид работ? Все подзадачи и ТМЦ будут удалены.")) return
    await supabase.from("work_types").delete().eq("id", id)
    setWorkTypes(workTypes.filter(w => w.id !== id))
  }

  const filtered = workTypes.filter(wt => {
    const q = search.toLowerCase()
    const matchSearch = !q || wt.code.toLowerCase().includes(q) || wt.name.toLowerCase().includes(q)
    const matchType = !filterUnitType || wt.unit_type === filterUnitType
    return matchSearch && matchType
  })

  const locoCount = workTypes.filter(w => w.unit_type === "locomotive").length
  const wagonCount = workTypes.filter(w => w.unit_type === "wagon").length

  return (
    <div className="p-8 space-y-6">
      {showAdd && <AddWorkTypeModal onClose={() => setShowAdd(false)} onSaved={fetchData} />}

      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/directories"
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-gray-500" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Wrench className="w-7 h-7 text-amber-500" />
            Виды работ и ТМЦ
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Шаблоны видов работ с подзадачами и списками ТМЦ
          </p>
        </div>
        <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={() => setShowAdd(true)}>
          <Plus className="w-4 h-4" /> Добавить вид работ
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500">Всего видов работ</p>
            <Wrench className="w-4 h-4 text-gray-400" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{workTypes.length}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-blue-200 dark:border-blue-800 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500">Для локомотивов</p>
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Лок.</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{locoCount}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-purple-200 dark:border-purple-800 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500">Для вагонов</p>
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">Ваг.</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{wagonCount}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по коду или названию..."
            className="pl-9"
          />
        </div>
        <select
          value={filterUnitType}
          onChange={(e) => setFilterUnitType(e.target.value)}
          className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Все типы ТПС</option>
          <option value="locomotive">Локомотивы</option>
          <option value="wagon">Вагоны</option>
        </select>
        {(search || filterUnitType) && (
          <button
            onClick={() => { setSearch(""); setFilterUnitType("") }}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-32 text-gray-400 text-sm gap-3">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          Загрузка...
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-12 text-center">
          <Wrench className="w-12 h-12 mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">Нет видов работ</p>
          <p className="text-sm text-gray-400 mt-1">Добавьте первый вид работ</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((wt) => (
            <WorkTypeCard
              key={wt.id}
              workType={wt}
              subtasks={subtasksMap[wt.id] ?? []}
              tmcItems={tmcMap[wt.id] ?? []}
              onDelete={() => handleDelete(wt.id)}
              onUpdate={(updated) => setWorkTypes(workTypes.map(w => w.id === updated.id ? updated : w))}
              onSubtasksChange={(subtasks) => setSubtasksMap({ ...subtasksMap, [wt.id]: subtasks })}
              onTmcChange={(tmc) => setTmcMap({ ...tmcMap, [wt.id]: tmc })}
              nomenclature={nomenclature}
            />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400">
        Показано {filtered.length} из {workTypes.length} видов работ
      </p>
    </div>
  )
}
