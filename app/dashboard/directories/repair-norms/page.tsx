"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api, type RepairNormItem, type RepairNormSet } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

const TYPE_LABELS: Record<string, string> = { wagon: "Вагон-самосвал", platform: "Платформа", tank_car: "Цистерна", diesel: "Тепловоз", locomotive: "Электровоз" }
type Section = "materials" | "spare_parts" | "lubricants"
const SECTION_LABELS: Record<Section, string> = { materials: "Материалы", spare_parts: "Запасные части", lubricants: "ГСМ" }
const BASIS_LABELS = { per_repair: "на один ремонт", per_month_per_unit: "среднемесячная, на 1 единицу" } as const
const selectCls = "h-9 rounded-md border border-input bg-transparent px-3 text-sm dark:bg-input/30"

const setKey = (s: Pick<RepairNormSet, "work_type_id" | "asset_type" | "asset_model_id" | "norm_group">) => `${s.work_type_id}|${s.asset_type}|${s.asset_model_id ?? ""}|${s.norm_group}`
const setTitle = (s: RepairNormSet) => `${s.work_type_code} · ${s.model_name ?? (s.norm_group || (TYPE_LABELS[s.asset_type] ?? s.asset_type))}`

export default function RepairNormsPage() {
  const { hasPermission } = useAuth()
  const canView = hasPermission("inventory.view")
  const canCreate = hasPermission("inventory.create")
  const canUpdate = hasPermission("inventory.update")
  const canDelete = hasPermission("inventory.delete")
  const [sets, setSets] = useState<RepairNormSet[] | null>(null)
  const [setsError, setSetsError] = useState<string | null>(null)
  const [active, setActive] = useState<RepairNormSet | null>(null)

  const loadSets = useCallback(async () => {
    setSetsError(null)
    try {
      const rows = await api.repairNorms.sets()
      setSets(rows)
      setActive((current) => (current ? rows.find((r) => setKey(r) === setKey(current)) ?? null : rows[0] ?? null))
    } catch (cause) {
      setSets(null)
      setSetsError(cause instanceof Error ? cause.message : "Не удалось загрузить нормы")
    }
  }, [])
  useEffect(() => { if (canView) void loadSets() }, [canView, loadSets])

  if (!canView) return <div className="p-8 text-sm text-gray-500" data-testid="norms-forbidden">У вас нет доступа к нормам расхода.</div>

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] space-y-6 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950" data-testid="repair-norms-page">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Нормы расхода на ремонт</h1>
        <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
          Материалы и запасные части на один вагон для каждого вида ремонта (ДР, КР). Нормы привязаны к виду ремонта и типу вагона, а не к участку.
        </p>
      </div>

      {setsError && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <span>{setsError}</span><Button variant="outline" size="sm" onClick={() => void loadSets()}>Повторить</Button>
        </div>
      )}
      {!sets && !setsError && <p className="text-sm text-gray-500">Загрузка…</p>}
      {sets && sets.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-gray-700">Норм пока нет.</div>
      )}

      <div className="flex flex-wrap gap-2">
        {(sets ?? []).map((s) => {
          const selected = active && setKey(active) === setKey(s)
          return (
            <button key={setKey(s)} type="button" aria-pressed={!!selected} data-testid="norm-set" onClick={() => setActive(s)}
              className={`rounded-xl border px-4 py-2 text-left text-sm transition-colors ${selected ? "border-blue-400 bg-blue-50 dark:bg-blue-950/30" : "border-gray-200 bg-white hover:border-blue-300 dark:border-gray-800 dark:bg-gray-900"}`}>
              <span className="block font-semibold text-gray-900 dark:text-white">{setTitle(s)}</span>
              <span className="block text-xs text-gray-500">{TYPE_LABELS[s.asset_type] ?? s.asset_type} · {s.total} строк{s.basis === "per_month_per_unit" ? " · в месяц на 1 ед." : ""}</span>
            </button>
          )
        })}
      </div>

      {active && (
        <NormTable key={setKey(active)} norm={active} canCreate={canCreate} canUpdate={canUpdate} canDelete={canDelete} onChanged={loadSets} />
      )}
    </div>
  )
}

function NormTable({ norm, canCreate, canUpdate, canDelete, onChanged }: {
  norm: RepairNormSet; canCreate: boolean; canUpdate: boolean; canDelete: boolean; onChanged: () => Promise<void>
}) {
  const [rows, setRows] = useState<RepairNormItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  const [section, setSection] = useState<"" | Section>("")
  const [editing, setEditing] = useState<RepairNormItem | "new" | null>(null)
  const requestId = useRef(0)

  const load = useCallback(async () => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const result = await api.repairNorms.items(norm, { q: q.trim() || undefined, section: section || undefined })
      if (id !== requestId.current) return // an older answer must not overwrite a newer one
      setRows(result.items)
    } catch (cause) {
      if (id !== requestId.current) return
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить строки")
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [norm, q, section])
  useEffect(() => { const t = window.setTimeout(() => void load(), q ? 250 : 0); return () => window.clearTimeout(t) }, [load, q])

  const mains = useMemo(() => rows.filter((r) => !r.parent_id), [rows])
  const refresh = async () => { await Promise.all([load(), onChanged()]) }

  const remove = async (item: RepairNormItem) => {
    const hasAlternatives = rows.some((r) => r.parent_id === item.id)
    if (!window.confirm(`Удалить строку «${item.name}»?${hasAlternatives ? "\nВместе с ней будут удалены её строки «при замене»." : ""}`)) return
    try { await api.repairNorms.remove(item.id); await refresh() } catch (cause) { window.alert(cause instanceof Error ? cause.message : "Не удалось удалить") }
  }
  const removeSet = async () => {
    if (!window.confirm(`Удалить всю норму «${setTitle(norm)}» (${norm.total} строк)? Это действие нельзя отменить.`)) return
    try { await api.repairNorms.removeSet(norm); await onChanged() } catch (cause) { window.alert(cause instanceof Error ? cause.message : "Не удалось удалить") }
  }

  return (
    <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900" data-testid="norm-table">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">{setTitle(norm)}</h2>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по наименованию…" className="h-9 w-64" aria-label="Поиск" />
        <select value={section} onChange={(e) => setSection(e.target.value as "" | Section)} className={selectCls} aria-label="Раздел">
          <option value="">Все разделы</option>
          <option value="materials">Материалы</option>
          <option value="spare_parts">Запасные части</option>
          <option value="lubricants">ГСМ</option>
        </select>
        <span className="text-xs text-gray-500">Строк: {rows.length}</span>
        <div className="ml-auto flex gap-2">
          {canCreate && <Button size="sm" onClick={() => setEditing("new")}>Добавить строку</Button>}
          {canDelete && <Button size="sm" variant="outline" onClick={() => void removeSet()}>Удалить всю норму</Button>}
        </div>
      </div>
      <p className="text-xs text-gray-500">{TYPE_LABELS[norm.asset_type] ?? norm.asset_type}{norm.norm_group ? ` · ${norm.norm_group}` : ""} · норма {BASIS_LABELS[norm.basis]}{norm.source_file ? ` · источник: ${norm.source_file}` : ""}</p>

      {error && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <span>{error}</span><Button variant="outline" size="sm" onClick={() => void load()}>Повторить</Button>
        </div>
      )}

      <div className="max-h-[70vh] overflow-auto rounded-lg border border-gray-200 dark:border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-gray-50 text-xs text-gray-500 dark:bg-gray-800">
            <tr>
              <th className="p-2">№</th><th className="p-2">Раздел</th><th className="p-2">Узел</th><th className="p-2">Наименование</th><th className="p-2">Ед.</th>
              <th className="p-2 text-right">Кол-во</th><th className="p-2">Как в файле</th><th className="p-2">Примечание</th>
              {(canUpdate || canDelete) && <th className="p-2 text-right">Действия</th>}
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 && <tr><td colSpan={9} className="p-6 text-center text-gray-500">Загрузка…</td></tr>}
            {!loading && !error && rows.length === 0 && <tr><td colSpan={9} className="p-6 text-center text-gray-500">Ничего не найдено</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-gray-100 dark:border-gray-800" data-testid="norm-row">
                <td className="p-2 tabular-nums text-gray-500">{r.seq}</td>
                <td className="p-2 text-xs text-gray-500">{SECTION_LABELS[r.section]}</td>
                <td className="p-2 text-xs text-gray-500">{r.group_name ?? ""}</td>
                <td className={`p-2 ${r.parent_id ? "pl-8 text-gray-600 dark:text-gray-300" : "font-medium"}`}>{r.parent_id ? "↳ " : ""}{r.name}</td>
                <td className="p-2">{r.unit ?? "—"}</td>
                <td className="p-2 text-right font-semibold tabular-nums">{r.quantity === null ? "—" : Number(r.quantity).toLocaleString("ru-RU", { maximumFractionDigits: 3 })}</td>
                <td className="p-2 text-gray-500">{r.quantity_text}</td>
                <td className="p-2 text-xs text-gray-500">{r.note ?? ""}</td>
                {(canUpdate || canDelete) && (
                  <td className="p-2 text-right whitespace-nowrap">
                    {canUpdate && <Button size="sm" variant="outline" className="mr-2" onClick={() => setEditing(r)}>Изменить</Button>}
                    {canDelete && <Button size="sm" variant="outline" onClick={() => void remove(r)}>Удалить</Button>}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && <ItemDialog norm={norm} item={editing === "new" ? null : editing} mains={mains} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await refresh() }} />}
    </section>
  )
}

function ItemDialog({ norm, item, mains, onClose, onSaved }: {
  norm: RepairNormSet; item: RepairNormItem | null; mains: RepairNormItem[]; onClose: () => void; onSaved: () => Promise<void>
}) {
  const [name, setName] = useState(item?.name ?? "")
  const [unit, setUnit] = useState(item?.unit ?? "")
  const [quantityText, setQuantityText] = useState(item?.quantity_text ?? "")
  const [section, setSection] = useState<Section>(item?.section ?? "materials")
  const [groupName, setGroupName] = useState(item?.group_name ?? "")
  const [note, setNote] = useState(item?.note ?? "")
  const [parentId, setParentId] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const save = async () => {
    if (!name.trim() || !quantityText.trim()) { setError("Заполните наименование и количество."); return }
    setBusy(true)
    setError(null)
    try {
      if (item) {
        await api.repairNorms.update(item.id, { name: name.trim(), unit: unit.trim() || null, quantity_text: quantityText.trim(), section, group_name: groupName.trim() || null, note: note.trim() || null })
      } else {
        await api.repairNorms.create({
          work_type_id: norm.work_type_id, asset_type: norm.asset_type, asset_model_id: norm.asset_model_id, norm_group: norm.norm_group, basis: norm.basis, section,
          group_name: groupName.trim() || null, name: name.trim(), unit: unit.trim() || null, quantity_text: quantityText.trim(), parent_id: parentId || null, note: note.trim() || null,
        })
      }
      await onSaved()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить")
      setBusy(false)
    }
  }
  const label = "mt-3 block text-xs font-medium text-gray-600 dark:text-gray-300"
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose} role="dialog" aria-modal="true" data-testid="norm-dialog">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl dark:bg-gray-900" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-gray-900 dark:text-white">{item ? "Изменить строку" : "Новая строка"} · {setTitle(norm)}</h3>
        <label className={label}>Наименование</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" />
        <div className="grid grid-cols-2 gap-3">
          <div><label className={label}>Единица</label><Input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="кг, шт., м…" className="mt-1" /></div>
          <div><label className={label}>Количество</label><Input value={quantityText} onChange={(e) => setQuantityText(e.target.value)} placeholder="1200 или 12/1,44" className="mt-1" /></div>
        </div>
        <p className="mt-1 text-xs text-gray-500">В таблице «Кол-во» берётся первое число (для «12/1,44» это 12); запись сохраняется как введена.</p>
        <label className={label}>Раздел</label>
        <select value={section} onChange={(e) => setSection(e.target.value as Section)} className={`${selectCls} mt-1 w-full`}>
          <option value="materials">Материалы</option>
          <option value="spare_parts">Запасные части</option>
          <option value="lubricants">ГСМ</option>
        </select>
        <label className={label}>Узел (необязательно)</label>
        <Input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="например, «Дизел цилиндр блоги»" className="mt-1" />
        {!item && (
          <>
            <label className={label}>Это замена для строки (необязательно)</label>
            <select value={parentId} onChange={(e) => setParentId(e.target.value)} className={`${selectCls} mt-1 w-full`}>
              <option value="">— основная строка —</option>
              {mains.map((m) => <option key={m.id} value={m.id}>{m.seq}. {m.name.slice(0, 60)}</option>)}
            </select>
          </>
        )}
        <label className={label}>Примечание</label>
        <Input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1" />
        {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={busy}>Отмена</Button>
          <Button onClick={() => void save()} disabled={busy}>{busy ? "Сохранение…" : "Сохранить"}</Button>
        </div>
      </div>
    </div>
  )
}
