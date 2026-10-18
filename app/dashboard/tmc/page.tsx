/* eslint-disable @typescript-eslint/no-explicit-any */
"use client"

import { useState, useEffect, useCallback } from "react"
import { useSectionView } from "@/lib/section-view-context"
import { api } from "@/lib/api"
import { useDebouncedValue } from "@/lib/use-debounced-value"
import { Package, Plus, Printer, Eye, CheckCircle, Clock, FileText, List, Search, X, Save, Pencil, Trash2 } from "@/components/ui/icons"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

type NomenclatureRow = {
  id: string
  name: string
  code: string | null
  unit: string
  department_id: string
  department_name: string
  localized_name?: string
  localized_department_name?: string
}

type TmcItem = {
  no: number
  name: string
  invNo: string
  unit: string
  qty: number
  price: number
  note: string
}

type TmcDoc = {
  id: string
  docNo: string
  date: string
  workOrderId: string
  loco: string
  workType: string
  depot: string
  warehouse: string
  issuedBy?: string
  acceptedBy?: string
  chief?: string
  status: "draft" | "issued" | "closed"
  items: TmcItem[]
}


const statusConfig = {
  draft:  { label: "Черновик", class: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300", icon: FileText },
  issued: { label: "Выдано", class: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400", icon: Clock },
  closed: { label: "Закрыто", class: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400", icon: CheckCircle },
}

const UNITS = ["шт.", "кг", "л", "м", "м²", "рул.", "кан.", "уп.", "к-т", "ед."]

function AddNomenclatureModal({
  open,
  onClose,
  sections,
  departments,
  effectiveSection,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  sections: { id: string; name: string; department_id: string | null }[]
  departments: { id: string; name: string }[]
  effectiveSection: string | null
  onSaved: () => void
}) {
  const [departmentId, setDepartmentId] = useState("")
  const [name, setName] = useState("")
  const [code, setCode] = useState("")
  const [unit, setUnit] = useState("шт.")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const reset = () => {
    setDepartmentId("")
    setName("")
    setCode("")
    setUnit("шт.")
    setError("")
  }

  useEffect(() => {
    if (open && sections.length) {
      const defaultDepartmentId = effectiveSection
        ? sections.find((section) => section.name === effectiveSection)?.department_id ?? ""
        : ""
      const selectedDepartmentId = departments.some(
        (department) => department.id === defaultDepartmentId
      )
        ? defaultDepartmentId
        : ""
      setDepartmentId(selectedDepartmentId)
    }
  }, [open, effectiveSection, sections, departments])

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    const trimName = name.trim()
    if (!trimName) {
      setError("Укажите наименование")
      return
    }
    if (!departments.some((department) => department.id === departmentId)) {
      setError("Выберите подразделение")
      return
    }
    setSaving(true)
    try {
      const newNomenclature = await api.nomenclature.create({
        department_id: departmentId,
        name: trimName,
        code: code.trim() || undefined,
        unit: unit.trim() || "шт.",
      });

      if (!newNomenclature.id) {
        throw new Error("Запись не вернулась из БД");
      }

      await onSaved();
      handleClose();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "An unknown error occurred";
      if (errorMessage.includes("already exists")) {
        setError("Номенклатура с таким названием уже существует в этом подразделении.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={handleClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-xl shadow-xl w-full max-w-md border border-gray-200 dark:border-gray-800"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Добавить номенклатуру</h2>
          <button type="button" onClick={handleClose} className="p-1 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-600" aria-label="Закрыть">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Подразделение *</label>
            <select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
              required
              disabled={departments.length === 0}
            >
              <option value="">{departments.length === 0 ? "Нет подразделений" : "— Выберите подразделение —"}</option>
              {departments.map((department) => (
                <option key={department.id} value={department.id}>{department.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Наименование *</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Наименование ТМЦ"
              className="h-10"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Код / артикул</label>
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Необязательно"
              className="h-10 font-mono"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Единица измерения</label>
            <select
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
            >
              {UNITS.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>
          {error && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}
          <div className="flex gap-2 pt-2">
            <Button type="submit" className="gap-2 bg-blue-600 hover:bg-blue-700" disabled={saving}>
              <Save className="w-4 h-4" />
              {saving ? "Сохранение..." : "Сохранить"}
            </Button>
            <Button type="button" variant="outline" onClick={handleClose}>Отмена</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EditNomenclatureModal({
  open,
  onClose,
  row,
  departments,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  row: NomenclatureRow | null
  departments: { id: string; name: string }[]
  onSaved: () => void
}) {
  const [departmentId, setDepartmentId] = useState("")
  const [name, setName] = useState("")
  const [code, setCode] = useState("")
  const [unit, setUnit] = useState("шт.")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (open && row) {
      setDepartmentId(row.department_id)
      setName(row.name)
      setCode(row.code ?? "")
      setUnit(row.unit ?? "шт.")
      setError("")
    }
  }, [open, row])

  const handleClose = () => {
    onClose()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!row) return
    setError("")
    const trimName = name.trim()
    if (!trimName) {
      setError("Укажите наименование")
      return
    }
    if (!departmentId) {
      setError("Выберите участок")
      return
    }
    setSaving(true)
    try {
      await api.nomenclature.update(row.id, {
        department_id: departmentId,
        name: trimName,
        code: code.trim() || undefined,
        unit: unit.trim() || "шт.",
      });
      await onSaved()
      handleClose()
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "An unknown error occurred";
      if (errorMessage.includes("already exists")) {
        setError("Номенклатура с таким названием уже существует в этом участке.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setSaving(false)
    }
  }

  if (!open || !row) return null
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={handleClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-xl shadow-xl w-full max-w-md border border-gray-200 dark:border-gray-800"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Редактировать номенклатуру</h2>
          <button type="button" onClick={handleClose} className="p-1 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Участок *</label>
            <select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
              required
            >
              <option value="">— Выберите участок —</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Наименование *</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="h-10" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Код / артикул</label>
            <Input value={code} onChange={(e) => setCode(e.target.value)} className="h-10 font-mono" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Ед. изм.</label>
            <select value={unit} onChange={(e) => setUnit(e.target.value)} className="w-full h-10 px-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm">
              {UNITS.map((u) => (<option key={u} value={u}>{u}</option>))}
            </select>
          </div>
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          <div className="flex gap-2 pt-2">
            <Button type="submit" className="gap-2 bg-blue-600 hover:bg-blue-700" disabled={saving}>
              <Save className="w-4 h-4" />{saving ? "Сохранение..." : "Сохранить"}
            </Button>
            <Button type="button" variant="outline" onClick={handleClose}>Отмена</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

function PrintDocument({ doc, onClose }: { doc: TmcDoc; onClose: () => void }) {
  const total = doc.items.reduce((s, i) => s + i.qty * i.price, 0)

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-start justify-center overflow-auto py-8 px-4">
      <div className="bg-white w-full max-w-4xl rounded-lg shadow-2xl">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-gray-200 bg-gray-50 rounded-t-lg print:hidden">
          <span className="text-sm font-medium text-gray-700">Предпросмотр документа</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => window.print()} className="gap-1.5">
              <Printer className="w-3.5 h-3.5" /> Печать
            </Button>
            <Button size="sm" variant="ghost" onClick={onClose}>Закрыть</Button>
          </div>
        </div>

        {/* 1C-style document */}
        <div className="p-8 font-mono text-sm text-black" id="print-area">
          {/* Header */}
          <div className="text-center mb-4">
            <div className="text-xs text-gray-500 mb-1">Унифицированная форма № М-11</div>
            <h1 className="text-base font-bold uppercase tracking-wide">ТРЕБОВАНИЕ-НАКЛАДНАЯ</h1>
            <div className="flex justify-center gap-8 mt-1 text-xs">
              <span>№ <span className="font-semibold border-b border-black px-4">{doc.docNo}</span></span>
              <span>от <span className="font-semibold border-b border-black px-4">{doc.date}</span></span>
            </div>
          </div>

          {/* Org info table */}
          <table className="w-full border border-black border-collapse text-xs mb-3">
            <tbody>
              <tr>
                <td className="border border-black px-2 py-1 w-40 text-gray-500">Организация</td>
                <td className="border border-black px-2 py-1 font-semibold" colSpan={3}>
                  АО «Российские железные дороги» / {doc.depot}
                </td>
              </tr>
              <tr>
                <td className="border border-black px-2 py-1 text-gray-500">Наряд-заказ</td>
                <td className="border border-black px-2 py-1 font-semibold">{doc.workOrderId}</td>
                <td className="border border-black px-2 py-1 text-gray-500">Локомотив</td>
                <td className="border border-black px-2 py-1 font-semibold">{doc.loco}</td>
              </tr>
              <tr>
                <td className="border border-black px-2 py-1 text-gray-500">Вид работ</td>
                <td className="border border-black px-2 py-1" colSpan={3}>{doc.workType}</td>
              </tr>
              <tr>
                <td className="border border-black px-2 py-1 text-gray-500">Склад-отправитель</td>
                <td className="border border-black px-2 py-1" colSpan={3}>{doc.warehouse}</td>
              </tr>
            </tbody>
          </table>

          {/* TMC items table */}
          <table className="w-full border border-black border-collapse text-xs mb-3">
            <thead>
              <tr className="bg-gray-100">
                <th className="border border-black px-2 py-1.5 text-center w-8">№ п/п</th>
                <th className="border border-black px-2 py-1.5 text-left">Наименование ТМЦ</th>
                <th className="border border-black px-2 py-1.5 text-center w-28">Инв. номер / Код</th>
                <th className="border border-black px-2 py-1.5 text-center w-16">Ед. изм.</th>
                <th className="border border-black px-2 py-1.5 text-center w-16">Кол-во</th>
                <th className="border border-black px-2 py-1.5 text-center w-24">Цена, сум</th>
                <th className="border border-black px-2 py-1.5 text-center w-24">Сумма, сум</th>
                <th className="border border-black px-2 py-1.5 text-left">Примечание</th>
              </tr>
            </thead>
            <tbody>
              {doc.items.map((item) => (
                <tr key={item.no}>
                  <td className="border border-black px-2 py-1 text-center">{item.no}</td>
                  <td className="border border-black px-2 py-1">{item.name}</td>
                  <td className="border border-black px-2 py-1 text-center font-mono">{item.invNo}</td>
                  <td className="border border-black px-2 py-1 text-center">{item.unit}</td>
                  <td className="border border-black px-2 py-1 text-center">{item.qty}</td>
                  <td className="border border-black px-2 py-1 text-right">{item.price.toFixed(2)}</td>
                  <td className="border border-black px-2 py-1 text-right font-semibold">
                    {(item.qty * item.price).toFixed(2)}
                  </td>
                  <td className="border border-black px-2 py-1 text-gray-500">{item.note}</td>
                </tr>
              ))}
              {/* Total row */}
              <tr className="font-bold bg-gray-50">
                <td className="border border-black px-2 py-1 text-center" colSpan={6}>ИТОГО:</td>
                <td className="border border-black px-2 py-1 text-right">{total.toFixed(2)}</td>
                <td className="border border-black px-2 py-1"></td>
              </tr>
            </tbody>
          </table>

          {/* Signatures */}
          <div className="grid grid-cols-3 gap-6 mt-6 text-xs">
            <div>
              <p className="text-gray-500 mb-1">Отпустил (кладовщик):</p>
              <div className="border-b border-black pb-1 mb-1 min-h-[20px]"></div>
              <p className="text-gray-500">{doc.issuedBy}</p>
            </div>
            <div>
              <p className="text-gray-500 mb-1">Получил (исполнитель):</p>
              <div className="border-b border-black pb-1 mb-1 min-h-[20px]"></div>
              <p className="text-gray-500">{doc.acceptedBy}</p>
            </div>
            <div>
              <p className="text-gray-500 mb-1">Утвердил (руководитель):</p>
              <div className="border-b border-black pb-1 mb-1 min-h-[20px]"></div>
              <p className="text-gray-500">{doc.chief}</p>
            </div>
          </div>

          <div className="mt-6 text-xs text-gray-400 text-center">
            Документ сформирован в системе управления техническим обслуживанием ЖД • {doc.date}
          </div>
        </div>
      </div>
    </div>
  )
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromRow(r: any): TmcDoc {
  return {
    id:          r.id,
    docNo:       r.doc_no,
    date:        r.doc_date,
    workOrderId: r.work_order_number ?? r.work_order_id ?? "",
    loco:        r.loco,
    workType:    r.localized_work_type ?? r.work_type,
    depot:       r.depot,
    warehouse:   r.warehouse,
    issuedBy:    r.issued_by,
    acceptedBy:  r.accepted_by,
    chief:       r.chief,
    status:      r.status,
    items:       (r.items ?? []).map((item: any, index: number) => ({
      no: index + 1,
      name: item.localized_nomenclature_name ?? item.name,
      invNo: item.inv_no ?? "",
      unit: item.unit ?? "",
      qty: Number(item.qty ?? 0),
      price: Number(item.price ?? 0),
      note: item.note ?? "",
    })),
  }
}

export default function TmcPage() {
  const { effectiveSection } = useSectionView()
  const [docs,     setDocs]     = useState<TmcDoc[]>([])
  const [docsTotal, setDocsTotal] = useState(0)
  const [docsOffset, setDocsOffset] = useState(0)
  const [docsSearch, setDocsSearch] = useState("")
  const [docsStatus, setDocsStatus] = useState<"" | "draft" | "issued" | "closed">("")
  const [docsDateFrom, setDocsDateFrom] = useState("")
  const [docsDateTo, setDocsDateTo] = useState("")
  const debouncedDocsSearch = useDebouncedValue(docsSearch.trim())
  const [docsError, setDocsError] = useState<string | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState<TmcDoc | null>(null)
  const [nomenclature, setNomenclature] = useState<NomenclatureRow[]>([])
  const [nomenclatureLoading, setNomenclatureLoading] = useState(true)
  const [nomenclatureSearch, setNomenclatureSearch] = useState("")
  const debouncedNomenclatureSearch = useDebouncedValue(nomenclatureSearch.trim())
  const [addNomenclatureOpen, setAddNomenclatureOpen] = useState(false)
  const [sections, setSections] = useState<{ id: string; name: string; department_id: string | null }[]>([])
  const [departments, setDepartments] = useState<{ id: string; name: string }[]>([])
  const [filterDepartmentId, setFilterDepartmentId] = useState<string | null>(null)
  const [editNomenclatureRow, setEditNomenclatureRow] = useState<NomenclatureRow | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [nomenclatureActionError, setNomenclatureActionError] = useState("")

  const fetchDocs = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.tmcDocuments.list({
        limit: 50,
        offset: docsOffset,
        sort_by: "created_at",
        sort_order: "desc",
        q: debouncedDocsSearch || undefined,
        status: docsStatus || undefined,
        date_from: docsDateFrom || undefined,
        date_to: docsDateTo || undefined,
      });
      setDocs(response.items.map(fromRow));
      setDocsTotal(response.total)
      setDocsError(null)
    } catch (error) {
      setDocsError(error instanceof Error ? error.message : "Не удалось загрузить документы ТМЦ")
      setDocs([])
    } finally {
      setLoading(false)
    }
  }, [debouncedDocsSearch, docsDateFrom, docsDateTo, docsOffset, docsStatus])

  const fetchNomenclature = useCallback(async () => {
    setNomenclatureLoading(true)
    try {
      const params: Parameters<typeof api.nomenclature.list>[0] = {
        limit: 1000,
        sort_by: "name",
        sort_order: "asc",
        q: debouncedNomenclatureSearch || undefined,
      }
      if (filterDepartmentId) {
        params.department_id = filterDepartmentId
      } else if (effectiveSection) {
        const section = sections.find((item) => item.name === effectiveSection)
        if (!section?.department_id) {
          setNomenclature([])
          return
        }
        params.department_id = section.department_id
      }

      const response = await api.nomenclature.list(params);
      setNomenclature(response.items)

    } catch (error) {
      console.error("Failed to fetch nomenclature:", error)
      setNomenclature([])
    } finally {
      setNomenclatureLoading(false)
    }
  }, [debouncedNomenclatureSearch, effectiveSection, filterDepartmentId, sections])

  const fetchDepartments = useCallback(async () => {
    try {
      const response = await api.departments.list({ limit: 1000, sort_by: 'name' });
      setDepartments(response.items.map((item) => ({ ...item, name: item.localized_name ?? item.name })));
    } catch (error) {
      console.error("Failed to fetch departments:", error);
      setDepartments([]);
    }
  }, [])

  const fetchSections = useCallback(async () => {
    try {
      const response = await api.sections.list({ limit: 1000, sort_by: "name" })
      setSections(response.items.map((item) => ({ ...item, name: item.localized_name ?? item.name })))
    } catch (error) {
      console.error("Failed to fetch sections:", error);
      setSections([]);
    }
  }, [])

  useEffect(() => { fetchDocs() }, [fetchDocs])
  useEffect(() => { fetchNomenclature() }, [fetchNomenclature])
  useEffect(() => { fetchSections() }, [fetchSections])
  useEffect(() => { fetchDepartments() }, [fetchDepartments])

  const filteredNomenclature = nomenclature
  const availableDepartments = departments

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-400 text-sm gap-3">
      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
      Загрузка документов ТМЦ...
    </div>
  )

  return (
    <div className="p-8 space-y-6">
      {selected && <PrintDocument doc={selected} onClose={() => setSelected(null)} />}
      <AddNomenclatureModal
        open={addNomenclatureOpen}
        onClose={() => setAddNomenclatureOpen(false)}
        sections={sections}
        departments={availableDepartments}
        effectiveSection={effectiveSection}
        onSaved={fetchNomenclature}
      />
      <EditNomenclatureModal
        open={!!editNomenclatureRow}
        onClose={() => setEditNomenclatureRow(null)}
        row={editNomenclatureRow}
        departments={availableDepartments}
        onSaved={fetchNomenclature}
      />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">ТМЦ — Требования-накладные</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Учёт материально-технических ценностей на ремонт и ТО
          </p>
        </div>
        <Button className="gap-2 bg-blue-600 hover:bg-blue-700">
          <Plus className="w-4 h-4" />
          Новая накладная
        </Button>
      </div>

      {/* Summary cards */}
      <p className="text-xs text-gray-500">Статусные карточки показывают результаты текущей страницы списка.</p>
      <div className="grid grid-cols-3 gap-4">
        {(["draft", "issued", "closed"] as const).map((s) => {
          const cfg = statusConfig[s]
          const count = docs.filter((d) => d.status === s).length
          return (
            <div key={s} className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
              s === "draft" ? "bg-gray-50 border-gray-200 dark:bg-gray-900 dark:border-gray-700" :
              s === "issued" ? "bg-amber-50 border-amber-200 dark:bg-amber-950 dark:border-amber-800" :
              "bg-green-50 border-green-200 dark:bg-green-950 dark:border-green-800"
            }`}>
              <cfg.icon className={`w-5 h-5 ${
                s === "draft" ? "text-gray-400" : s === "issued" ? "text-amber-600" : "text-green-600"
              }`} />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">{cfg.label}</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white">{count}</p>
              </div>
            </div>
          )
        })}
      </div>

      {/* Documents list */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <Input type="search" maxLength={200} value={docsSearch} onChange={(event) => { setDocsSearch(event.target.value); setDocsOffset(0) }} placeholder="Поиск по номеру, наряду, ОС или материалу" aria-label="Поиск документов ТМЦ" className="min-w-56 flex-1" />
        <select value={docsStatus} onChange={(event) => { setDocsStatus(event.target.value as typeof docsStatus); setDocsOffset(0) }} aria-label="Статус документа ТМЦ" className="h-9 rounded-lg border border-gray-200 bg-white px-3 text-sm dark:border-gray-700 dark:bg-gray-800">
          <option value="">Все статусы</option><option value="draft">Черновик</option><option value="issued">Выдан</option><option value="closed">Закрыт</option>
        </select>
        <label className="text-xs text-gray-500">С даты<input type="date" value={docsDateFrom} onChange={(event) => { setDocsDateFrom(event.target.value); setDocsOffset(0) }} className="ml-2 rounded border border-gray-200 bg-white px-2 py-1 text-sm dark:border-gray-700 dark:bg-gray-800" /></label>
        <label className="text-xs text-gray-500">По дату<input type="date" value={docsDateTo} onChange={(event) => { setDocsDateTo(event.target.value); setDocsOffset(0) }} className="ml-2 rounded border border-gray-200 bg-white px-2 py-1 text-sm dark:border-gray-700 dark:bg-gray-800" /></label>
        {(docsSearch || docsStatus || docsDateFrom || docsDateTo) && <button type="button" onClick={() => { setDocsSearch(""); setDocsStatus(""); setDocsDateFrom(""); setDocsDateTo(""); setDocsOffset(0) }} className="text-sm text-blue-600 hover:underline">Сбросить фильтры</button>}
        <span className="text-xs text-gray-500">Найдено: {docsTotal}</span>
      </div>
      {docsError && (
        <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          Не удалось загрузить документы ТМЦ: {docsError}
        </div>
      )}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              {["Номер документа", "Дата", "Наряд-заказ", "Локомотив", "Вид работ", "Позиций ТМЦ", "Сумма, сум", "Статус", ""].map((h) => (
                <th key={h} className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {docs.length === 0 ? <tr><td colSpan={9} className="px-5 py-12 text-center text-sm text-gray-500">{docsError ? "Не удалось загрузить документы" : "Документы не найдены"}</td></tr> : docs.map((doc) => {
              const cfg = statusConfig[doc.status]
              const total = doc.items.reduce((s, i) => s + i.qty * i.price, 0)
              return (
                <tr key={doc.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-md bg-blue-50 dark:bg-blue-950 flex items-center justify-center">
                        <Package className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                      </div>
                      <span className="text-sm font-mono font-semibold text-gray-900 dark:text-white">{doc.docNo}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-sm text-gray-600 dark:text-gray-300">{doc.date}</td>
                  <td className="px-5 py-4 text-sm font-medium text-blue-600 dark:text-blue-400">{doc.workOrderId}</td>
                  <td className="px-5 py-4 text-sm font-medium text-gray-900 dark:text-white">{doc.loco}</td>
                  <td className="px-5 py-4 text-sm text-gray-600 dark:text-gray-300 max-w-[200px]">
                    <span className="line-clamp-1">{doc.workType}</span>
                  </td>
                  <td className="px-5 py-4 text-sm text-center text-gray-900 dark:text-white font-semibold">
                    {doc.items.length}
                  </td>
                  <td className="px-5 py-4 text-sm font-semibold text-gray-900 dark:text-white font-mono">
                    {total.toLocaleString("ru-RU", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-5 py-4">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${cfg.class}`}>
                      <cfg.icon className="w-3 h-3" />
                      {cfg.label}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5 text-xs h-7"
                      onClick={() => setSelected(doc)}
                    >
                      <Eye className="w-3 h-3" />
                      Открыть
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 px-5 py-3 text-sm text-gray-500 dark:border-gray-800">
          <span>Показано {docsTotal === 0 ? 0 : docsOffset + 1}–{Math.min(docsOffset + docs.length, docsTotal)} из {docsTotal}</span>
          <div className="flex gap-2">
            <Button variant="outline" disabled={docsOffset === 0} onClick={() => setDocsOffset(Math.max(0, docsOffset - 50))}>Назад</Button>
            <Button variant="outline" disabled={docsOffset + 50 >= docsTotal} onClick={() => setDocsOffset(docsOffset + 50)}>Далее</Button>
          </div>
        </div>
      </div>
      {/* Справочник номенклатуры ТМЦ (из импорта по участкам) */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <List className="w-5 h-5 text-gray-500 dark:text-gray-400" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Справочник номенклатуры ТМЦ</h2>
            </div>
            <select
              value={filterDepartmentId ?? ""}
              onChange={(e) => setFilterDepartmentId(e.target.value || null)}
              className="h-9 px-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
            >
              <option value="">Все подразделения</option>
              {availableDepartments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <Button type="button" size="sm" className="gap-1.5 bg-blue-600 hover:bg-blue-700" onClick={() => setAddNomenclatureOpen(true)}>
              <Plus className="w-4 h-4" />
              Добавить номенклатуру
            </Button>
          </div>
          <div className="relative w-64 sm:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Поиск по наименованию или коду..."
              value={nomenclatureSearch}
              onChange={(e) => setNomenclatureSearch(e.target.value)}
              className="pl-9 h-9 text-sm bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
            />
          </div>
        </div>
        {nomenclatureActionError && (
          <p className="px-5 py-3 text-sm text-red-600 dark:text-red-400">
            {nomenclatureActionError}
          </p>
        )}
        <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
          {nomenclatureLoading ? (
            <div className="flex items-center justify-center py-16 text-gray-400 text-sm gap-2">
              <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              Загрузка номенклатуры...
            </div>
          ) : filteredNomenclature.length === 0 ? (
            <div className="py-16 text-center text-gray-500 dark:text-gray-400 text-sm">
              {nomenclature.length === 0
                ? "Нет данных. Запустите импорт из Excel (скрипт import_nomenclature.py)."
                : "Ничего не найдено по запросу."}
            </div>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50 dark:bg-gray-800/50 sticky top-0 z-10">
                <tr>
                  {["Наименование", "Код", "Ед. изм.", "Подразделение", "Действия"].map((h) => (
                    <th
                      key={h}
                      className="text-left px-5 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {filteredNomenclature.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td className="px-5 py-3 text-sm text-gray-900 dark:text-white">{r.localized_name ?? r.name}</td>
                    <td className="px-5 py-3 text-sm font-mono text-gray-600 dark:text-gray-300">{r.code || "—"}</td>
                    <td className="px-5 py-3 text-sm text-gray-600 dark:text-gray-400">{r.unit}</td>
                    <td className="px-5 py-3 text-sm text-gray-600 dark:text-gray-400">{r.localized_department_name ?? r.department_name}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-8 w-8 p-0 text-gray-500 hover:text-blue-600"
                          onClick={() => setEditNomenclatureRow(r)}
                          title="Изменить"
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                        {deleteConfirmId === r.id ? (
                          <span className="flex items-center gap-1 text-xs">
                            <button
                              type="button"
                              className="text-red-600 font-medium"
                              onClick={async () => {
                                setNomenclatureActionError("")
                                try {
                                  await api.nomenclature.remove(r.id)
                                  await fetchNomenclature()
                                  setDeleteConfirmId(null)
                                } catch (error) {
                                  setNomenclatureActionError(
                                    error instanceof Error ? error.message : "Не удалось удалить номенклатуру"
                                  )
                                }
                              }}
                            >
                              Да
                            </button>
                            <button type="button" className="text-gray-500" onClick={() => setDeleteConfirmId(null)}>Нет</button>
                          </span>
                        ) : (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-8 w-8 p-0 text-gray-500 hover:text-red-600"
                            onClick={() => setDeleteConfirmId(r.id)}
                            title="Удалить"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {!nomenclatureLoading && filteredNomenclature.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-200 dark:border-gray-800 text-xs text-gray-500 dark:text-gray-400">
            Показано {filteredNomenclature.length}
            {filterDepartmentId || effectiveSection ? " по участку" : " всего"}
          </div>
        )}
      </div>

      {/* Info block */}
      <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-xl p-4 flex gap-3">
        <Package className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-semibold text-blue-900 dark:text-blue-200">Шаблон требования-накладной</p>
          <p className="text-blue-700 dark:text-blue-400 mt-0.5">
            Каждая накладная содержит: наименование ТМЦ, инвентарный номер, единицу измерения, количество, цену и сумму.
            Нажмите «Открыть» для просмотра и печати документа в формате, совместимом с 1С.
          </p>
        </div>
      </div>
    </div>
  )
}
