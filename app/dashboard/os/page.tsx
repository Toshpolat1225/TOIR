"use client"

import Link from "next/link"
import { useState, useEffect, useCallback, useRef } from "react"
import { useRealtime } from "@/lib/use-realtime"
import { useDebouncedValue } from "@/lib/use-debounced-value"
import {
  api,
  type FixedAssetCreate,
  type FixedAssetUpdate,
  type FixedAsset as ApiFixedAsset,
  type AssetModel,
  type AssetSource,
  type AssetSourceLink,
  type UnifiedAsset,
  type WialonUnit,
  type WialonUnitDetail,
  type GtkFixedAssetDetail,
  type AssetCatalogItem,
  type FixedAssetStats,
  type FixedAssetInventoryImportPreviewItem,
  type FixedAssetInventoryImportApplyRow,
} from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { useSections, type SectionData } from "@/lib/use-sections"
import {
  Train, Container, Plus, Search, X, Save, ChevronDown,
  CheckCircle, Wrench, AlertTriangle, XCircle,
  CalendarDays, SlidersHorizontal, Pencil, Building2, Hash, Radio, Trash2
} from "@/components/ui/icons"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/* ════════════════════════════════════════
   Types
════════════════════════════════════════ */
type AssetType = string
type AssetStatus = string

type FixedAsset = {
  id:           string
  name:         string   // Asset display name
  assetTypeLabel?: string
  statusLabel?: string
  assetType:    AssetType
  series:       string
  depot:        string
  sectionId:    string | null
  status:       AssetStatus
  commDate:     string   // Commissioning date
  yearBuilt:    string
  mileage:      string
  lastMaint:    string
  nextMaint:    string
  invNumber:    string   // Fixed-asset inventory number
  initialCost:  string   // Initial cost
  owner:        string
  wialonId:     string | null
  /** Mileage synchronized from Wialon. */
  wialonLastSync?: string | null
  wialonOnline?: boolean
  source: UnifiedAsset["source"]
  unitId: string | null
  wialonMileage: string
  engineHours: string
  speed: string
  lastMessageAt: string | null
  suspectAbsolute: boolean
  orgUnitId: string | null
}

/* ════════════════════════════════════════
   Catalogs
════════════════════════════════════════ */
const statusConfig: Record<string, { label: string; icon: React.ElementType; cls: string; dot: string }> = {
  operational:    { label: "В эксплуатации", icon: CheckCircle,   cls: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",   dot: "bg-green-500" },
  maintenance:    { label: "На ТО",          icon: Wrench,        cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",   dot: "bg-amber-500" },
  repair:         { label: "Ремонт",         icon: AlertTriangle, cls: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400", dot: "bg-orange-500" },
  out_of_service: { label: "Выведен",        icon: XCircle,       cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",           dot: "bg-red-500" },
}

function PassportAndLinks({ assetId, canWrite, sections, types, onUpdated }: {
  assetId: string
  canWrite: boolean
  sections: SectionData[]
  types: AssetCatalogItem[]
  onUpdated: (asset?: ApiFixedAsset) => void
}) {
  const [asset, setAsset] = useState<ApiFixedAsset | null>(null)
  const [models, setModels] = useState<AssetModel[]>([])
  const [links, setLinks] = useState<AssetSourceLink[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [assetResult, modelResult, linksResult] = await Promise.all([
        api.fixedAssets.get(assetId),
        api.fixedAssets.models({ limit: 1000, offset: 0 }),
        api.fixedAssets.links(assetId, true),
      ])
      setAsset(assetResult)
      setModels(modelResult.items)
      setLinks(linksResult.items)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить паспорт и связи.")
    } finally {
      setLoading(false)
    }
  }, [assetId])

  useEffect(() => { void load() }, [load])

  const update = (changes: Partial<ApiFixedAsset>) => {
    setAsset((current) => current ? { ...current, ...changes } : current)
  }
  const fieldCls = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
  const model = models.find((item) => item.id === asset?.model_id)
  const modelOptions = models.filter((item) => item.asset_type === asset?.asset_type)

  const savePassport = async () => {
    if (!asset) return
    if (!asset.inv_number.trim()) {
      setError("Инвентарный номер обязателен.")
      return
    }
    setSaving(true)
    setError("")
    try {
      const original = await api.fixedAssets.get(assetId)
      if (asset.org_unit_id !== original.org_unit_id &&
          !window.confirm("Подтвердите изменение участка основного средства.")) return
      const updated = await api.fixedAssets.update(assetId, {
        asset_type: asset.asset_type,
        model_id: asset.model_id,
        number: asset.number?.trim() || null,
        serial_number: asset.serial_number?.trim() || null,
        inv_number: asset.inv_number.trim(),
        accounting_inv_number: asset.accounting_inv_number?.trim() || null,
        commissioned_at: asset.commissioned_at,
        year_built: asset.year_built,
        org_unit_id: asset.org_unit_id,
        decommissioned_at: asset.decommissioned_at,
      })
      setAsset(updated)
      onUpdated(updated)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Не удалось сохранить паспорт.")
    } finally {
      setSaving(false)
    }
  }

  const changeLink = async (source: AssetSource) => {
    const current = links.find((item) => item.source === source && item.status === "active")
    try {
      setError("")
      if (current) {
        if (!window.confirm(`Отвязать источник «${sourceLabels[source]}»? История связи сохранится.`)) return
        await api.fixedAssets.unlinkSource(assetId, source)
      } else {
        const externalId = window.prompt(`Введите внешний ID для источника «${sourceLabels[source]}».`)
        if (externalId === null || !externalId.trim()) return
        await api.fixedAssets.linkSource(assetId, { source, external_id: externalId.trim() })
      }
      await refreshLinks()
      const updatedAsset = await api.fixedAssets.get(assetId)
      setAsset((currentAsset) => currentAsset ? {
        ...currentAsset,
        wialon_id: updatedAsset.wialon_id,
        gtk_id: updatedAsset.gtk_id,
      } : currentAsset)
      onUpdated(updatedAsset)
    } catch (linkError) {
      setError(linkError instanceof Error ? linkError.message : "Не удалось изменить связь с источником.")
    }
  }

  const refreshLinks = async () => {
    try {
      const updatedLinks = await api.fixedAssets.links(assetId, true)
      setLinks(updatedLinks.items)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить историю связей.")
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-blue-200 bg-blue-50/60 p-4 dark:border-blue-900 dark:bg-blue-950/20">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">Паспорт</h3>
          {canWrite && asset && <Button size="sm" onClick={savePassport} disabled={loading || saving}>
            {saving ? "Сохранение..." : "Сохранить паспорт"}
          </Button>}
        </div>
        {loading && <p className="text-sm text-gray-500">Загрузка паспорта...</p>}
        {asset && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-gray-500">Тип
              <select className={fieldCls} value={asset.asset_type} disabled={!canWrite} onChange={(event) => {
                const nextType = event.target.value
                update({
                  asset_type: nextType,
                  ...(model && model.asset_type !== nextType ? { model_id: null } : {}),
                })
              }}>
                {types.map((item) => <option key={item.code} value={item.code}>{item.names.ru || item.code}</option>)}
              </select>
            </label>
            <label className="text-xs text-gray-500">Модель
              <select className={fieldCls} value={asset.model_id ?? ""} disabled={!canWrite} onChange={(event) => update({ model_id: event.target.value || null })}>
                <option value="">Не выбрана</option>
                {modelOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                {model && !modelOptions.some((item) => item.id === model.id) && <option value={model.id}>{model.name}</option>}
              </select>
            </label>
            <label className="text-xs text-gray-500">Номер
              <input className={fieldCls} value={asset.number ?? ""} disabled={!canWrite} onChange={(event) => update({ number: event.target.value || null })}/>
            </label>
            <label className="text-xs text-gray-500">Серийный номер
              <input className={fieldCls} value={asset.serial_number ?? ""} disabled={!canWrite} onChange={(event) => update({ serial_number: event.target.value || null })}/>
            </label>
            <label className="text-xs text-gray-500">Инвентарный номер
              <input className={fieldCls} value={asset.inv_number} disabled={!canWrite} onChange={(event) => update({ inv_number: event.target.value })}/>
              {asset.inv_number_is_provisional && <span className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300">временный</span>}
            </label>
            <label className="text-xs text-gray-500">Бухгалтерский инв. номер (1С)
              <input className={fieldCls} value={asset.accounting_inv_number ?? ""} disabled={!canWrite} onChange={(event) => update({ accounting_inv_number: event.target.value || null })}/>
            </label>
            <label className="text-xs text-gray-500">Дата ввода в эксплуатацию
              <input type="date" className={fieldCls} value={asset.commissioned_at ?? ""} disabled={!canWrite} onChange={(event) => update({ commissioned_at: event.target.value || null })}/>
            </label>
            <label className="text-xs text-gray-500">Год постройки
              <input type="number" min="1900" max={new Date().getFullYear()} className={fieldCls} value={asset.year_built ?? ""} disabled={!canWrite} onChange={(event) => update({ year_built: event.target.value ? Number(event.target.value) : null })}/>
            </label>
            <label className="text-xs text-gray-500">Участок
              <select className={fieldCls} value={asset.org_unit_id ?? ""} disabled={!canWrite} onChange={(event) => update({ org_unit_id: event.target.value || null })}>
                <option value="">Не указан</option>
                {sections.map((section) => <option key={section.id} value={section.id}>{section.localized_name || section.name}</option>)}
              </select>
            </label>
            <label className="text-xs text-gray-500">Дата списания
              <input type="date" className={fieldCls} value={asset.decommissioned_at ?? ""} disabled={!canWrite} onChange={(event) => update({ decommissioned_at: event.target.value || null })}/>
            </label>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800/40">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 dark:text-white">Источники</h3>
          <button type="button" className="text-xs text-blue-700 underline dark:text-blue-300" onClick={() => void refreshLinks()}>Обновить историю</button>
        </div>
        <div className="space-y-3">
          {sourceOrder.map((source) => {
            const sourceLinks = links.filter((item) => item.source === source)
            const active = sourceLinks.find((item) => item.status === "active")
            return <div key={source} className="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{sourceLabels[source]}</p>
                  <p className="text-xs text-gray-500">{active ? `${active.external_name || "ID"} · ${active.external_id}` : "Не привязан"}</p>
                </div>
                {canWrite && <Button size="sm" variant="outline" onClick={() => void changeLink(source)}>{active ? "Отвязать" : "Привязать"}</Button>}
              </div>
              {sourceLinks.length > 0 && <ul className="mt-2 space-y-1 border-t border-gray-100 pt-2 text-xs text-gray-500 dark:border-gray-800">
                {sourceLinks.map((item) => <li key={item.id}>
                  {item.external_name || item.external_id} · {item.status === "active" ? "активна" : "завершена"} · {new Date(item.linked_at).toLocaleString("ru-RU")}
                </li>)}
              </ul>}
            </div>
          })}
        </div>
      </section>
      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

const sourceOrder: AssetSource[] = ["wialon", "gtk", "vesavoy", "onec"]
const sourceLabels: Record<AssetSource, string> = {
  wialon: "Wialon",
  gtk: "GTK",
  vesavoy: "Весовой",
  onec: "1С",
}

/* ════════════════════════════════════════
   Modals
════════════════════════════════════════ */

/* ════════════════════════════════════════
   View and edit modal
════════════════════════════════════════ */
function AssetModal({ asset, onClose, onSave, onDelete, sections, sectionsData, types, statuses, canWrite, onUpdated }: {
  asset: FixedAsset
  onClose: () => void
  onSave: (a: FixedAsset) => void
  onDelete?: (a: FixedAsset) => void
  sections: string[]
  sectionsData: SectionData[]
  types: AssetCatalogItem[]
  statuses: AssetCatalogItem[]
  canWrite: boolean
  onUpdated: (asset?: ApiFixedAsset) => void
}) {
  const [editing,      setEditing]      = useState(false)
  const [commDate,     setCommDate]     = useState(asset.commDate)
  const [status,       setStatus]       = useState(asset.status)
  const [depot,        setDepot]        = useState(asset.depot)
  const [mileage,      setMileage]      = useState(asset.mileage)
  const [lastMaint,    setLastMaint]    = useState(asset.lastMaint)
  const [nextMaint,    setNextMaint]    = useState(asset.nextMaint)
  const [initialCost,  setInitialCost]  = useState(asset.initialCost)
  const [owner,        setOwner]        = useState(asset.owner)
  const [wialonId, setWialonId] = useState(asset.wialonId ?? "")
  const [unitSearch, setUnitSearch] = useState("")
  const [availableUnits, setAvailableUnits] = useState<WialonUnit[]>([])
  const [wialonDetail, setWialonDetail] = useState<WialonUnitDetail | null>(null)
  const [unitLoadError, setUnitLoadError] = useState("")
  const [gtkDetail, setGtkDetail] = useState<GtkFixedAssetDetail | null>(null)
  const [gtkLoadState, setGtkLoadState] = useState<"loading" | "linked" | "unlinked" | "error">("loading")

  useEffect(() => {
    let active = true
    api.wialon.listUnits({ linked: false, limit: 1000, offset: 0 })
      .then((response) => { if (active) setAvailableUnits(response.items) })
      .catch(() => { if (active) setUnitLoadError("Не удалось загрузить список свободных единиц Wialon.") })
    if (asset.wialonId) {
      api.wialon.getUnit(asset.wialonId)
        .then((detail) => { if (active) setWialonDetail(detail) })
        .catch(() => { if (active) setUnitLoadError("Не удалось загрузить сведения Wialon.") })
    }
    return () => { active = false }
  }, [asset.wialonId])

  useEffect(() => {
    let active = true
    api.fixedAssets.get(asset.id)
      .then((fixedAsset) => {
        if (!active) return
        if (!fixedAsset.gtk_id) {
          setGtkLoadState("unlinked")
          return
        }
        return api.gtk.fixedAssetDetail(asset.id)
          .then((detail) => {
            if (active) {
              setGtkDetail(detail)
              setGtkLoadState("linked")
            }
          })
      })
      .catch(() => {
        if (active) setGtkLoadState("error")
      })
    return () => { active = false }
  }, [asset.id])

  const st = statusConfig[status] || { label: asset.statusLabel || status, icon: CheckCircle, cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300", dot: "bg-blue-500" }
  const typeLabels: Record<string, { label: string; gradient: string; Icon: React.ElementType }> = {
    locomotive: { label: "Локомотив", gradient: "bg-gradient-to-r from-blue-600 to-blue-700", Icon: Train },
    diesel:     { label: "Тепловоз",  gradient: "bg-gradient-to-r from-orange-600 to-orange-700", Icon: Train },
    wagon:      { label: "Вагон",     gradient: "bg-gradient-to-r from-purple-600 to-purple-700", Icon: Container },
  }
  const typeInfo = typeLabels[asset.assetType] || typeLabels.locomotive
  const matchingUnits = availableUnits.filter((unit) =>
    `${unit.name} ${unit.unit_id}`.toLocaleLowerCase().includes(unitSearch.trim().toLocaleLowerCase()),
  )

  const handleModalUpdated = (updatedAsset?: ApiFixedAsset) => {
    onUpdated(updatedAsset)
    void (updatedAsset ? Promise.resolve(updatedAsset) : api.fixedAssets.get(asset.id)).then(async (current) => {
      setWialonId(current.wialon_id ?? "")
      if (current.wialon_id) {
        try {
          setWialonDetail(await api.wialon.getUnit(current.wialon_id))
        } catch {
          setUnitLoadError("Не удалось обновить сведения Wialon.")
        }
      } else {
        setWialonDetail(null)
      }
      if (current.gtk_id) {
        try {
          setGtkDetail(await api.gtk.fixedAssetDetail(asset.id))
          setGtkLoadState("linked")
        } catch {
          setGtkLoadState("error")
        }
      } else {
        setGtkDetail(null)
        setGtkLoadState("unlinked")
      }
    }).catch(() => {
      setGtkLoadState("error")
      setUnitLoadError("Не удалось обновить связь с источником.")
    })
  }

  const handleSave = () => {
    onSave({ ...asset, commDate, status, depot, mileage, lastMaint, nextMaint, initialCost, owner, wialonId: wialonId || null })
    setEditing(false)
  }

  const fieldCls = (edit: boolean) =>
    edit
      ? "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
      : "w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800/60 rounded-lg text-gray-700 dark:text-gray-300 border border-transparent"

  const selCls = fieldCls(true) + " appearance-none pr-8 cursor-pointer"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className={`flex items-center justify-between px-6 py-4 rounded-t-2xl ${typeInfo.gradient} text-white flex-shrink-0`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
              <typeInfo.Icon className="w-5 h-5"/>
            </div>
            <div>
              <p className="text-xs opacity-80 font-medium">
                {asset.assetTypeLabel || typeInfo.label} {asset.series && `· ${asset.series}`}
              </p>
              <p className="text-lg font-bold leading-tight">{asset.name}</p>
              {asset.invNumber && <p className="text-xs opacity-70">Инв. № {asset.invNumber}</p>}
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/20 transition-colors">
            <X className="w-5 h-5"/>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Series and depot summary */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-3 text-center">
              <p className="text-[10px] text-gray-400 uppercase tracking-widest mb-1">Серия</p>
              <p className="font-bold text-sm text-gray-900 dark:text-white">{asset.series}</p>
            </div>
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-3 text-center">
              <p className="text-[10px] text-gray-400 uppercase tracking-widest mb-1">Год постройки</p>
              <p className="font-bold text-sm text-gray-900 dark:text-white">{asset.yearBuilt}</p>
            </div>
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-3 text-center">
              <p className="text-[10px] text-gray-400 uppercase tracking-widest mb-1">Пробег (км)</p>
              <p className="font-bold text-sm text-gray-900 dark:text-white">{asset.mileage}</p>
            </div>
          </div>

          <PassportAndLinks
            assetId={asset.id}
            canWrite={canWrite}
            sections={sectionsData}
            types={types}
            onUpdated={handleModalUpdated}
          />

          {/* Highlighted commissioning date */}
          <div className="rounded-xl border-2 border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <CalendarDays className="w-4 h-4 text-blue-600 dark:text-blue-400"/>
              <p className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wide">
                Дата ввода в эксплуатацию
              </p>
            </div>
            {editing ? (
              <input type="text" value={commDate} onChange={e => setCommDate(e.target.value)}
                placeholder="ДД.ММ.ГГГГ"
                className="w-full border-2 border-blue-300 dark:border-blue-700 rounded-lg px-3 py-2 text-sm font-semibold bg-white dark:bg-gray-800 text-blue-700 dark:text-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            ) : (
              <p className="text-xl font-bold text-blue-700 dark:text-blue-300">{commDate || "—"}</p>
            )}
          </div>

          {/* Main fields */}
          <div className="grid grid-cols-2 gap-4">

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Статус</p>
              {editing ? (
                <div className="relative">
                  <select value={status} onChange={e => setStatus(e.target.value as AssetStatus)} className={selCls}>
                    
                    
                    
                    
                  {statuses.map((item) => <option key={item.code} value={item.code}>{item.names.ru || item.code}</option>)}</select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
                </div>
              ) : (
                <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg ${st.cls}`}>
                  <st.icon className="w-3.5 h-3.5"/>{asset.statusLabel || st.label}
                </span>
              )}
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Владелец</p>
              {editing ? (
                <input value={owner} onChange={e => setOwner(e.target.value)} className={fieldCls(true)}/>
              ) : (
                <p className={fieldCls(false)}>{owner}</p>
              )}
            </div>

            <div className="col-span-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Депо / участок</p>
              {editing ? (
                <div className="relative">
                  <select value={depot} onChange={e => setDepot(e.target.value)} className={selCls}>
                    {[...new Set([...sections, depot].filter(Boolean))].sort().map(d => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
                </div>
              ) : (
                <p className={fieldCls(false)}>{depot}</p>
              )}
            </div>

            <div className="col-span-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Wialon</p>
              {editing ? (
                <div className="space-y-2">
                  <Input value={unitSearch} onChange={(event) => setUnitSearch(event.target.value)} placeholder="Поиск по названию или ID Wialon"/>
                  <select value={wialonId} onChange={(event) => setWialonId(event.target.value)} className={selCls}>
                    <option value="">Не привязан / Отвязать</option>
                    {asset.wialonId && !availableUnits.some((unit) => unit.unit_id === asset.wialonId) && (
                      <option value={asset.wialonId}>{asset.wialonId} (текущая привязка)</option>
                    )}
                    {matchingUnits.map((unit) => (
                      <option key={unit.unit_id} value={unit.unit_id}>{unit.name} · {unit.unit_id}</option>
                    ))}
                  </select>
                </div>
              ) : (
                <p className={fieldCls(false)}>{asset.wialonId || "Не привязан"}</p>
              )}
              {unitLoadError && <p role="alert" className="mt-1 text-xs text-red-600">{unitLoadError}</p>}
            </div>

            {asset.wialonId && (
              <div className="col-span-2 rounded-xl border border-blue-200 dark:border-blue-900 bg-blue-50/70 dark:bg-blue-950/20 p-3">
                <p className="text-xs font-semibold text-blue-700 dark:text-blue-300 mb-2">Данные Wialon</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <p>Пробег: <b>{(wialonDetail?.cnm ?? asset.wialonMileage) || "—"} км</b></p>
                  <p>Моточасы: <b>{(wialonDetail?.cneh ?? asset.engineHours) || "—"}</b></p>
                  <p>Скорость: <b>{(wialonDetail?.speed ?? asset.speed) || "—"} км/ч</b></p>
                  <p>Последнее сообщение: <b>{wialonDetail?.last_message_at ? new Date(wialonDetail.last_message_at).toLocaleString("ru-RU") : asset.lastMessageAt ? new Date(asset.lastMessageAt).toLocaleString("ru-RU") : "—"}</b></p>
                </div>
                {wialonDetail?.suspect_absolute && <p className="mt-2 text-xs font-medium text-amber-700 dark:text-amber-300">⚠ Подозрительное значение счётчика</p>}
              </div>
            )}

            <div className="col-span-2 rounded-xl border border-slate-200 dark:border-gray-700 bg-slate-50 dark:bg-gray-800/50 p-3">
              <p className="text-xs font-semibold text-slate-700 dark:text-gray-200 mb-2">Данные GTK</p>
              {gtkLoadState === "loading" && <p className="text-xs text-gray-500">Загрузка данных GTK…</p>}
              {gtkLoadState === "error" && <p role="alert" className="text-xs text-red-600 dark:text-red-400">Не удалось загрузить данные GTK.</p>}
              {gtkLoadState === "unlinked" && <p className="text-xs text-gray-500">Объект не привязан к GTK.</p>}
              {gtkDetail && (
                <div className="space-y-3 text-xs text-gray-700 dark:text-gray-300">
                  <p>
                    <span className="text-gray-500">GTK ID:</span>{" "}
                    <b>{gtkDetail.gtk_id}</b>
                    {" · "}
                    {gtkDetail.kind === "locomotive" ? "Локомотив" : "Вагон"}
                    {" · "}
                    <b>{gtkDetail.gtk_object.name || "—"}</b>
                  </p>
                  <div>
                    <p className="font-semibold mb-1">Текущий состав</p>
                    {gtkDetail.current_trains.length === 0 ? (
                      <p className="text-gray-500">Сейчас не входит в состав.</p>
                    ) : gtkDetail.current_trains.map((train) => (
                      <p key={train.gtk_id}>
                        {train.number || train.title || `Состав ${train.gtk_id}`} · {train.carriages.length} ваг.
                      </p>
                    ))}
                  </div>
                  {gtkDetail.kind === "carriage" && (
                    <div>
                      <p className="font-semibold mb-1">Последние начисления пробега</p>
                      {gtkDetail.recent_mileage_logs.length === 0 ? (
                        <p className="text-gray-500">Начислений пока нет.</p>
                      ) : (
                        <ul className="space-y-1">
                          {gtkDetail.recent_mileage_logs.map((log) => (
                            <li key={log.id}>
                              {Number(log.km).toLocaleString("ru-RU")} км · состав {log.train_gtk_id}
                              {" · "}
                              {new Date(log.period_from).toLocaleDateString("ru-RU")}–{new Date(log.period_to).toLocaleDateString("ru-RU")}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Номер вагона</p>
              {editing ? (
                <input value={initialCost} onChange={e => setInitialCost(e.target.value)} className={fieldCls(true)} placeholder="33-9909"/>
              ) : (
                <p className={fieldCls(false)}>{initialCost}</p>
              )}
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Пробег (км)</p>
              {editing ? (
                <input value={mileage} onChange={e => setMileage(e.target.value)} className={fieldCls(true)}/>
              ) : (
                <>
                  <p className={fieldCls(false)}>{mileage || "—"}</p>
                  {(asset.assetType === "locomotive" || asset.assetType === "diesel") && asset.wialonOnline && asset.wialonLastSync && (
                    <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
                      <Radio className="w-3 h-3"/> Актуальные данные с Wialon · обновлено {new Date(asset.wialonLastSync).toLocaleString("ru-RU")}
                    </p>
                  )}
                </>
              )}
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Последнее ТО</p>
              {editing ? (
                <input value={lastMaint} onChange={e => setLastMaint(e.target.value)} className={fieldCls(true)} placeholder="ДД.ММ.ГГГГ"/>
              ) : (
                <p className={fieldCls(false)}>{lastMaint}</p>
              )}
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Следующее ТО</p>
              {editing ? (
                <input value={nextMaint} onChange={e => setNextMaint(e.target.value)} className={fieldCls(true)} placeholder="ДД.ММ.ГГГГ"/>
              ) : (
                <p className={fieldCls(false)}>{nextMaint}</p>
              )}
            </div>

          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0 rounded-b-2xl">
          <span className="text-xs text-gray-400">Инв. №: <span className="font-mono font-semibold text-gray-600 dark:text-gray-300">{asset.invNumber}</span></span>
          <div className="flex gap-3 items-center">
            {onDelete && (
              <Button
                type="button"
                variant="outline"
                className="gap-2 text-red-600 border-red-200 hover:bg-red-50 hover:border-red-300 dark:text-red-400 dark:border-red-800 dark:hover:bg-red-950/50"
                onClick={() => {
                  if (confirm(`Удалить оборудование «${asset.name}» из реестра? Это действие нельзя отменить.`)) {
                    onDelete(asset)
                  }
                }}
              >
                <Trash2 className="w-4 h-4"/> Удалить
              </Button>
            )}
            <Button variant="outline" onClick={onClose}>Закрыть</Button>
            {!editing && canWrite ? (
              <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={() => setEditing(true)}>
                <Pencil className="w-4 h-4"/> Редактировать
              </Button>
            ) : editing && canWrite ? (
              <Button className="gap-2 bg-green-600 hover:bg-green-700" onClick={handleSave}>
                <Save className="w-4 h-4"/> Сохранить
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════
   New asset modal
════════════════════════════════════════ */
function AddAssetModal({ onClose, onSave, sections, types, statuses, wialonUnit }: {
  onClose: () => void
  onSave: (a: FixedAsset, wialonUnit?: WialonUnit) => void
  sections: string[]
  types: AssetCatalogItem[]
  statuses: AssetCatalogItem[]
  wialonUnit?: WialonUnit
}) {
  const [assetType,   setAssetType]   = useState<AssetType>(wialonUnit ? "" : types[0]?.code || "locomotive")
  const [name,        setName]        = useState(wialonUnit?.name ?? "")  // Main asset name
  const [series,      setSeries]      = useState("")
  const [depot,       setDepot]       = useState(sections[0] ?? "")
  const [commDate,    setCommDate]    = useState("")
  const [yearBuilt,   setYearBuilt]   = useState("")
  const [initialCost, setInitialCost] = useState("")
  const [invNumber,   setInvNumber]   = useState(wialonUnit ? `WIALON-${wialonUnit.unit_id}` : "")  // Inventory number
  const [owner,       setOwner]       = useState("РЖД")
  const [error,       setError]       = useState("")
  const [wialonId, setWialonId] = useState(wialonUnit?.unit_id ?? "")
  const [unitSearch, setUnitSearch] = useState("")
  const [availableUnits, setAvailableUnits] = useState<WialonUnit[]>([])
  const [unitLoadError, setUnitLoadError] = useState("")

  useEffect(() => {
    if (wialonUnit) return
    let active = true
    api.wialon.listUnits({ linked: false, limit: 1000, offset: 0 })
      .then((response) => { if (active) setAvailableUnits(response.items) })
      .catch(() => { if (active) setUnitLoadError("Не удалось загрузить список свободных единиц Wialon.") })
    return () => { active = false }
  }, [wialonUnit])

  useEffect(() => {
    if (wialonUnit) return
    if (types.length && !types.some((item) => item.code === assetType)) setAssetType(types[0].code)
  }, [types, assetType, wialonUnit])
  const matchingUnits = availableUnits.filter((unit) =>
    `${unit.name} ${unit.unit_id}`.toLocaleLowerCase().includes(unitSearch.trim().toLocaleLowerCase()),
  )

  const handleSave = () => {
    if (!name.trim() || !invNumber.trim() || (!wialonUnit && !commDate.trim())) {
      setError(wialonUnit
        ? "Заполните обязательные поля: Инвентарный номер и Наименование"
        : "Заполните обязательные поля: Инвентарный номер, Наименование, Дата ввода")
      return
    }
    if (wialonUnit && assetType !== "locomotive" && assetType !== "diesel" && assetType !== "wagon") {
      setError("Выберите тип основного средства.")
      return
    }
    // Generate a unique ID.
    const generatedId = `${assetType === "locomotive" ? "LOC" : assetType === "diesel" ? "DSL" : "WAG"}-${Date.now()}`
    const newAsset: FixedAsset = {
      id: generatedId,
      name: name.trim(),
      assetType,
      series,
      depot,
      sectionId: null,
      status: statuses.find((item) => item.behavior === "operational")?.code || statuses[0]?.code || "operational",
      commDate: commDate.trim(),
      yearBuilt,
      mileage: "0",
      lastMaint: "—",
      nextMaint: "—",
      invNumber: invNumber.trim(),
      initialCost,
      owner,
      wialonId: wialonId || null,
      source: "toir",
      unitId: wialonId || null,
      wialonMileage: String(wialonUnit?.cnm ?? ""),
      engineHours: String(wialonUnit?.cneh ?? ""),
      speed: String(wialonUnit?.speed ?? ""),
      lastMessageAt: wialonUnit?.last_message_at ?? null,
      suspectAbsolute: wialonUnit?.suspect_absolute ?? false,
      orgUnitId: null,
    }
    onSave(newAsset, wialonUnit)
  }

  const lbl = "block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1"
  const inp = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const sel = inp + " appearance-none pr-8 cursor-pointer"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">

        <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-green-600 to-green-700 text-white">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center">
              <Plus className="w-5 h-5"/>
            </div>
            <div>
              <p className="text-xs text-green-200">{wialonUnit ? "Создание из Wialon" : "Основные средства"}</p>
              <p className="text-base font-bold">Добавить новый объект ОС</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/20 transition-colors">
            <X className="w-5 h-5"/>
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Type */}
          <div>
            <p className={lbl}>Тип объекта</p>
            <select required value={assetType} onChange={(event) => setAssetType(event.target.value)} className={sel}>
              {wialonUnit && <option value="" disabled>Выберите тип</option>}
              {types.map((item) => <option key={item.code} value={item.code}>{item.names.ru || item.code}</option>)}
            </select>
            <div className="flex gap-2">
              <button onClick={() => setAssetType("locomotive")}
                className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-semibold border-2 transition-all ${
                  assetType === "locomotive" ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-600" : "border-gray-200 dark:border-gray-700 text-gray-500"
                }`}>
                <Train className="w-4 h-4"/> Локомотив
              </button>
              <button onClick={() => setAssetType("diesel")}
                className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-semibold border-2 transition-all ${
                  assetType === "diesel" ? "border-orange-500 bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300 dark:border-orange-600" : "border-gray-200 dark:border-gray-700 text-gray-500"
                }`}>
                <Train className="w-4 h-4"/> Тепловоз
              </button>
              <button onClick={() => setAssetType("wagon")}
                className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-semibold border-2 transition-all ${
                  assetType === "wagon" ? "border-purple-500 bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300 dark:border-purple-600" : "border-gray-200 dark:border-gray-700 text-gray-500"
                }`}>
                <Container className="w-4 h-4"/> Вагон
              </button>
            </div>
          </div>

          <div>
            <label className={lbl}>Наименование (номер) <span className="text-red-500">*</span></label>
            <input value={name} onChange={e => setName(e.target.value)} className={inp} placeholder="Вагон-самосвал 12345 / ЧС7-042"/>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={lbl}>Серия / Модель</label>
              <input value={series} onChange={e => setSeries(e.target.value)} className={inp} placeholder="ЧС7, 61-4440..."/>
            </div>
            <div>
              <label className={lbl}>Инвентарный номер</label>
              <input value={invNumber} onChange={e => setInvNumber(e.target.value)} className={inp} placeholder="ОС-12345"/>
            </div>
          </div>

          {/* Required commissioning date */}
          <div className="rounded-xl border-2 border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-3">
            <label className="flex items-center gap-2 text-xs font-bold text-blue-700 dark:text-blue-400 mb-2">
            <CalendarDays className="w-3.5 h-3.5"/> Дата ввода в эксплуатацию {!wialonUnit && <span className="text-red-500">*</span>}
            </label>
            <input value={commDate} onChange={e => setCommDate(e.target.value)} className={inp + " border-blue-300 dark:border-blue-700 focus:ring-blue-500 font-semibold"} placeholder="ДД.ММ.ГГГГ"/>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={lbl}>Год постройки</label>
              <input value={yearBuilt} onChange={e => setYearBuilt(e.target.value)} className={inp} placeholder="2015"/>
            </div>
            <div>
              <label className={lbl}>Первоначальная стоимость (сум)</label>
                <input type="number" min="0" step="0.01" value={initialCost} onChange={e => setInitialCost(e.target.value)} className={inp}/>
            </div>
          </div>

          <div>
            <label className={lbl}>Депо / Участок</label>
            <div className="relative">
              <select value={depot} onChange={e => setDepot(e.target.value)} className={sel}>
                {sections.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
            </div>
          </div>

          <div>
            <label className={lbl}>Wialon (необязательно)</label>
            {wialonUnit ? (
              <Input value={`${wialonUnit.name} · ${wialonUnit.unit_id}`} readOnly />
            ) : (
              <div className="space-y-2">
                <Input value={unitSearch} onChange={(event) => setUnitSearch(event.target.value)} placeholder="Поиск по названию или ID Wialon"/>
                <select value={wialonId} onChange={(event) => setWialonId(event.target.value)} className={sel}>
                  <option value="">Не привязан</option>
                  {matchingUnits.map((unit) => (
                    <option key={unit.unit_id} value={unit.unit_id}>{unit.name} · {unit.unit_id}</option>
                  ))}
                </select>
              </div>
            )}
            {unitLoadError && <p role="alert" className="mt-1 text-xs text-red-600">{unitLoadError}</p>}
          </div>

          <div>
            <label className={lbl}>Владелец</label>
            <input value={owner} onChange={e => setOwner(e.target.value)} className={inp} placeholder="РЖД, ФПК..."/>
          </div>

          {error && <p className="text-sm text-red-500 font-medium">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button className="gap-2 bg-green-600 hover:bg-green-700" onClick={handleSave}>
            <Save className="w-4 h-4"/> Добавить ОС
          </Button>
        </div>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════
   Page
════════════════════════════════════════ */
function apiDate(value: string): string | null {
  const normalized = value.trim()
  if (!normalized || normalized === "—") return null
  const match = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(normalized)
  return match ? `${match[3]}-${match[2]}-${match[1]}` : normalized
}

function fromUnified(r: UnifiedAsset): FixedAsset {
  return {
    id:               r.asset_id ?? `wialon:${r.unit_id ?? r.name}`,
    name:             r.name,
    assetType:        r.asset_type ?? "",
    series:           r.series ?? "",
    depot:            r.section ?? "",
    sectionId:        r.section_id,
    status:           r.status ?? "",
    commDate:         "",
    yearBuilt:        "",
    mileage:          String(r.mileage ?? ""),
    lastMaint:        "",
    nextMaint:        "",
    invNumber:        r.inv_number ?? "",
    initialCost:      "",
    owner:            "",
    wialonId:         r.unit_id,
    wialonLastSync:   r.last_message_at,
    wialonOnline:     r.is_online,
    source:           r.source,
    unitId:           r.unit_id,
    wialonMileage:    String(r.wialon_cnm ?? ""),
    engineHours:      String(r.wialon_cneh ?? ""),
    speed:            String(r.speed ?? ""),
    lastMessageAt:    r.last_message_at,
    suspectAbsolute:  r.suspect_absolute,
    orgUnitId:         r.org_unit_id,
  }
}

function toRow(
  a: FixedAsset
): FixedAssetUpdate & Pick<FixedAssetCreate, "inv_number" | "name" | "asset_type"> {
  return {
    inv_number:   a.invNumber,
    name:         a.name,
    asset_type:   a.assetType,
    series:       a.series || null,
    depot:        a.depot || null,
    section_id:   a.sectionId,
    status:       a.status,
    comm_date:    apiDate(a.commDate),
    year_built:   a.yearBuilt ? Number(a.yearBuilt) : null,
    mileage:      Number(a.mileage) || 0,
    last_maint_date: apiDate(a.lastMaint),
    next_maint_date: apiDate(a.nextMaint),
    initial_cost: a.initialCost ? Number(a.initialCost) : null,
    owner:        a.owner || null,
    wialon_id:    a.wialonId,
  }
}

const PAGE_SIZE = 50

export default function OsPage() {
  const { sections, sectionsData, getSectionId, hasAmbiguousSectionName } = useSections()
  const { profile } = useAuth()
  const canWrite = profile?.role === "admin" || profile?.role === "operator"
  const [assetTypes, setAssetTypes] = useState<AssetCatalogItem[]>([])
  const [assetStatuses, setAssetStatuses] = useState<AssetCatalogItem[]>([])
  const [assets,    setAssets]    = useState<FixedAsset[]>([])
  const [total,     setTotal]     = useState(0)
  const [page,      setPage]      = useState(0)
  const [loading,   setLoading]   = useState(true)
  const [selected,  setSelected]  = useState<FixedAsset | null>(null)
  const [selectedUnit, setSelectedUnit] = useState<WialonUnit | null>(null)
  const [showAdd,   setShowAdd]   = useState(false)
  const [search,    setSearch]    = useState("")
  const debouncedSearch = useDebouncedValue(search.trim())
  const [fType,     setFType]     = useState<AssetType | "">("")
  const [fSource,   setFSource]   = useState<UnifiedAsset["source"] | "">("")
  const [fSection,  setFSection]  = useState("")
  const [fStatus,   setFStatus]   = useState<AssetStatus | "">("")
  const [fBehavior, setFBehavior] = useState("")
  const [counts, setCounts] = useState<FixedAssetStats | null>(null)
  const [loadError, setLoadError] = useState("")
  const [statsError, setStatsError] = useState("")
  const [fWithoutOrgUnit, setFWithoutOrgUnit] = useState(false)
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([])
  const [showBulkOrgUnit, setShowBulkOrgUnit] = useState(false)
  const [bulkOrgUnitId, setBulkOrgUnitId] = useState("")
  const [bulkOrgUnitSaving, setBulkOrgUnitSaving] = useState(false)
  const [showInventoryImport, setShowInventoryImport] = useState(false)
  const [inventoryPreview, setInventoryPreview] = useState<FixedAssetInventoryImportPreviewItem[]>([])
  const [inventoryImportBusy, setInventoryImportBusy] = useState(false)
  const [inventoryImportError, setInventoryImportError] = useState("")
  
  // Keep the latest filters available to the realtime listener.
  const filtersRef = useRef({ page: 0, search: "", fType: "" as AssetType | "", fSource: "" as UnifiedAsset["source"] | "", fSection: "", fStatus: "" as AssetStatus | "", fBehavior: "", fWithoutOrgUnit: false })
  const realtimeRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load counters and depot names once.
  const fetchCounts = useCallback(async () => {
    try {
      const params: Parameters<typeof api.fixedAssets.stats>[0] = {};
      if (debouncedSearch) params.q = debouncedSearch;
      if (fType) params.asset_type = fType;
      if (fStatus) params.status = fStatus;
      if (fBehavior) params.status_behavior = fBehavior;
      if (fSection) params.section_id = fSection;
      const stats = await api.fixedAssets.stats(params);
      setCounts(stats);
      setStatsError("");
    } catch (error) {
      console.error("Failed to fetch asset counts:", error);
      setStatsError("Не удалось загрузить статистику основных средств.");
    }
  }, [debouncedSearch, fType, fStatus, fBehavior, fSection])

  useEffect(() => {
    void Promise.all([
      api.fixedAssetCatalogs.list("types", { limit: 500, offset: 0 }),
      api.fixedAssetCatalogs.list("statuses", { limit: 500, offset: 0 }),
    ]).then(([types, statuses]) => {
      setAssetTypes(types.items)
      setAssetStatuses(statuses.items)
    }).catch((error) => console.error("Failed to load asset catalogs:", error))
  }, [])

  const fetchAssets = useCallback(async (
    pg: number,
    q: string,
    ft: string,
    source: UnifiedAsset["source"] | "",
    fs: string,
    section = fSection,
    behavior = fBehavior,
    withoutOrgUnit = fWithoutOrgUnit,
  ) => {
    setLoading(true)
    try {
      const params: Parameters<typeof api.fixedAssets.unified>[0] = {
        limit: PAGE_SIZE,
        offset: pg * PAGE_SIZE,
        sort_by: "name",
        sort_order: "asc",
      };
      if (q) params.q = q;
      if (ft) params.asset_type = ft as AssetType;
      if (source) params.source = source;
      if (fs || behavior) params.status = (fs || behavior) as AssetStatus;
      if (section) params.section_id = section;
      if (withoutOrgUnit) params.without_org_unit = true;

      const response = await api.fixedAssets.unified(params)
      setAssets(response.items.map(fromUnified))
      setTotal(response.total);
      setLoadError("");

    } catch (e) {
      console.error("Ошибка загрузки ОС:", e)
      setAssets([])
      setTotal(0)
      setLoadError("Не удалось загрузить основные средства. Попробуйте обновить страницу.");
    } finally {
      setLoading(false)
    }
  }, [fSection, fBehavior, fWithoutOrgUnit])

  const realtimeFetchersRef = useRef({ fetchAssets, fetchCounts })

  useEffect(() => {
    realtimeFetchersRef.current = { fetchAssets, fetchCounts }
  }, [fetchAssets, fetchCounts])

  useEffect(() => { fetchCounts() }, [fetchCounts])

  // Keep the latest filters available to the realtime listener.
  useEffect(() => {
    filtersRef.current = { page, search: debouncedSearch, fType, fSource, fSection, fStatus, fBehavior, fWithoutOrgUnit }
  }, [page, debouncedSearch, fType, fSource, fSection, fStatus, fBehavior, fWithoutOrgUnit])

  // Coalesce bursts of row-level notifications into one refresh.
  useRealtime(useCallback((event) => {
    if (event.resource !== "fixed_assets") return
    if (realtimeRefreshTimerRef.current) return
    realtimeRefreshTimerRef.current = setTimeout(() => {
      realtimeRefreshTimerRef.current = null
      const filters = filtersRef.current
      const { fetchAssets: refreshAssets, fetchCounts: refreshCounts } = realtimeFetchersRef.current
      void refreshAssets(filters.page, filters.search, filters.fType, filters.fSource, filters.fStatus, filters.fSection, filters.fBehavior, filters.fWithoutOrgUnit)
      void refreshCounts()
    }, 750)
  }, []), ["fixed_assets"])

  useEffect(() => () => {
    if (realtimeRefreshTimerRef.current) clearTimeout(realtimeRefreshTimerRef.current)
  }, [])

  // Reset the page when filters change.
  useEffect(() => {
    setPage(0)
    setSelectedAssetIds([])
  }, [search, fType, fSource, fSection, fStatus, fBehavior, fWithoutOrgUnit])

  useEffect(() => {
    setSelectedAssetIds([])
  }, [page])

  useEffect(() => {
    fetchAssets(page, debouncedSearch, fType, fSource, fStatus, fSection, fBehavior)
  }, [fetchAssets, page, debouncedSearch, fType, fSource, fSection, fStatus, fBehavior]);

  const totalPages    = Math.ceil(total / PAGE_SIZE)
  const activeFilters = [fType, fSource, fSection, fStatus, fBehavior, search, fWithoutOrgUnit].filter(Boolean).length
  const clearFilters  = () => { setFType(""); setFSource(""); setFSection(""); setFStatus(""); setFBehavior(""); setFWithoutOrgUnit(false); setSearch("") }
  const selectType = (code: string) => setFType((current) => current === code ? "" : code)
  const selectBehavior = (code: string) => { setFStatus(""); setFBehavior((current) => current === code ? "" : code) }
  const filtered      = assets  // Filtering is performed by the server.
  const selectableAssetIds = filtered
    .filter((asset) => asset.source !== "wialon" && !asset.id.startsWith("wialon:"))
    .map((asset) => asset.id)
  const allPageSelected = selectableAssetIds.length > 0
    && selectableAssetIds.every((assetId) => selectedAssetIds.includes(assetId))

  const applyBulkOrgUnit = async () => {
    if (!bulkOrgUnitId || selectedAssetIds.length === 0) return
    setBulkOrgUnitSaving(true)
    try {
      await api.fixedAssets.bulkUpdateOrgUnit({
        asset_ids: selectedAssetIds,
        org_unit_id: bulkOrgUnitId,
      })
      setShowBulkOrgUnit(false)
      setSelectedAssetIds([])
      setPage(0)
      await fetchAssets(0, debouncedSearch, fType, fSource, fStatus, fSection, fBehavior, fWithoutOrgUnit)
      await fetchCounts()
    } catch (error) {
      alert("Не удалось назначить участок: " + (error instanceof Error ? error.message : "ошибка API"))
    } finally {
      setBulkOrgUnitSaving(false)
    }
  }

  const previewInventoryFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setInventoryImportBusy(true)
    setInventoryImportError("")
    setInventoryPreview([])
    try {
      const text = await file.text()
      const preview = await api.fixedAssets.previewInventoryImport({ csv_text: text })
      setInventoryPreview(preview.items)
    } catch (error) {
      setInventoryImportError(error instanceof Error ? error.message : "Не удалось проверить файл.")
    } finally {
      setInventoryImportBusy(false)
      event.target.value = ""
    }
  }

  const applyInventoryPreview = async () => {
    const rows: FixedAssetInventoryImportApplyRow[] = inventoryPreview
      .filter((row) => row.status === "ok" && row.asset_id && row.inv_number)
      .map((row) => ({
        asset_id: row.asset_id!,
        inv_number: row.inv_number!,
        accounting_inv_number: row.accounting_inv_number,
      }))
    if (rows.length === 0) return
    setInventoryImportBusy(true)
    setInventoryImportError("")
    try {
      const result = await api.fixedAssets.applyInventoryImport(rows)
      setShowInventoryImport(false)
      setInventoryPreview([])
      setSelectedAssetIds([])
      await fetchAssets(page, debouncedSearch, fType, fSource, fStatus, fSection, fBehavior, fWithoutOrgUnit)
      await fetchCounts()
      alert(`Импорт завершён. Обновлено объектов: ${result.updated}.`)
    } catch (error) {
      setInventoryImportError(error instanceof Error ? error.message : "Не удалось применить импорт.")
    } finally {
      setInventoryImportBusy(false)
    }
  }

  const handleSave = async (updated: FixedAsset) => {
    if (hasAmbiguousSectionName(updated.depot)) {
      alert("Невозможно выбрать участок: название не уникально. Выберите участок по ID.")
      return
    }
    try {
      await api.fixedAssets.update(updated.id, {
        ...toRow(updated),
        section_id: getSectionId(updated.depot) ?? updated.sectionId,
      });
      fetchAssets(page, search, fType, fSource, fStatus, fSection, fBehavior)
      fetchCounts()
      setSelected(null)
    } catch (error) {
      alert("Не удалось сохранить: " + (error instanceof Error ? error.message : "ошибка API"));
    }
  }

  const handleDelete = async (a: FixedAsset) => {
    try {
      await api.fixedAssets.remove(a.id);
      fetchAssets(page, search, fType, fSource, fStatus, fSection, fBehavior)
      fetchCounts()
      setSelected(null)
    } catch (error) {
      alert("Не удалось удалить: " + (error instanceof Error ? error.message : "ошибка API"));
    }
  }

  const handleAdd = async (a: FixedAsset, wialonUnit?: WialonUnit) => {
    if (wialonUnit) {
      if (a.assetType !== "locomotive" && a.assetType !== "diesel" && a.assetType !== "wagon") {
        alert("Выберите допустимый тип основного средства.")
        return
      }
      if (hasAmbiguousSectionName(a.depot)) {
        alert("Невозможно выбрать участок: название не уникально. Выберите участок по ID.")
        return
      }
      try {
        const sectionId = getSectionId(a.depot) ?? null
        const result = await api.wialon.createAsset(wialonUnit.unit_id, {
          inv_number: a.invNumber,
          name: a.name,
          asset_type: a.assetType,
          series: a.series || null,
          section_id: sectionId,
        })
        if (result.warning) alert(result.warning)
        setSelectedUnit(null)
        setShowAdd(false)
        await fetchAssets(0, search, fType, fSource, fStatus, fSection, fBehavior)
        await fetchCounts()
        setPage(0)
      } catch (error) {
        alert("Не удалось создать ОС из Wialon: " + (error instanceof Error ? error.message : "ошибка API"))
      }
      return
    }
    if (hasAmbiguousSectionName(a.depot)) {
      alert("Невозможно выбрать участок: название не уникально. Выберите участок по ID.")
      return
    }
    try {
      await api.fixedAssets.create({
        ...toRow(a),
        section_id: getSectionId(a.depot) ?? null,
      });
      fetchAssets(0, search, fType, fSource, fStatus, fSection, fBehavior)
      fetchCounts()
      setPage(0)
      setShowAdd(false)
    } catch (error) {
      alert("Не удалось добавить: " + (error instanceof Error ? error.message : "ошибка API"))
    }
  }

  const selCls = "appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 pr-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-400 text-sm gap-3">
      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
      Загрузка данных ОС...
    </div>
  )

  return (
    <div className="p-8 space-y-6">
      {selected && <AssetModal asset={selected} onClose={() => setSelected(null)} onSave={handleSave} onDelete={canWrite ? handleDelete : undefined} sections={sections} sectionsData={sectionsData} types={assetTypes} statuses={assetStatuses} canWrite={canWrite} onUpdated={(updatedAsset) => {
        if (updatedAsset) setSelected((current) => current ? {
          ...current,
          assetType: updatedAsset.asset_type,
          series: updatedAsset.series ?? "",
          invNumber: updatedAsset.inv_number,
          wialonId: updatedAsset.wialon_id,
        } : current)
        void fetchAssets(page, debouncedSearch, fType, fSource, fStatus, fSection, fBehavior)
        void fetchCounts()
      }}/>}
      {showAdd && canWrite && <AddAssetModal onClose={() => { setShowAdd(false); setSelectedUnit(null) }} onSave={handleAdd} sections={sections} types={assetTypes} statuses={assetStatuses} wialonUnit={selectedUnit ?? undefined}/>}
      {showBulkOrgUnit && canWrite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="bulk-org-unit-title">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl dark:bg-gray-900">
            <h2 id="bulk-org-unit-title" className="text-lg font-semibold text-gray-900 dark:text-white">Назначить участок</h2>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              Будет обновлено объектов: <strong>{selectedAssetIds.length}</strong>. Участок: <strong>{sectionsData.find((section) => section.id === bulkOrgUnitId)?.localized_name || sectionsData.find((section) => section.id === bulkOrgUnitId)?.name || "не выбран"}</strong>.
            </p>
            <select value={bulkOrgUnitId} onChange={(event) => setBulkOrgUnitId(event.target.value)} className={`${selCls} mt-4 w-full`}>
              <option value="">Выберите участок</option>
              {sectionsData.map((section) => <option key={section.id} value={section.id}>{section.localized_name || section.name}</option>)}
            </select>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowBulkOrgUnit(false)} disabled={bulkOrgUnitSaving}>Отмена</Button>
              <Button onClick={() => void applyBulkOrgUnit()} disabled={!bulkOrgUnitId || bulkOrgUnitSaving}>
                {bulkOrgUnitSaving ? "Сохранение..." : "Подтвердить"}
              </Button>
            </div>
          </div>
        </div>
      )}
      {showInventoryImport && canWrite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="inventory-import-title">
          <div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-xl bg-white p-5 shadow-xl dark:bg-gray-900">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="inventory-import-title" className="text-lg font-semibold text-gray-900 dark:text-white">Импорт инв. номеров</h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">CSV: столбцы asset_id или name, inv_number, accounting_inv_number (необязательно).</p>
              </div>
              <Button variant="outline" onClick={() => setShowInventoryImport(false)} disabled={inventoryImportBusy}>Закрыть</Button>
            </div>
            <label className="mt-4 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Выберите CSV-файл
              <input className="mt-2 block w-full text-sm" type="file" accept=".csv,text/csv" onChange={(event) => void previewInventoryFile(event)} disabled={inventoryImportBusy}/>
            </label>
            {inventoryImportBusy && <p className="mt-3 text-sm text-gray-500">Проверка данных...</p>}
            {inventoryImportError && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{inventoryImportError}</p>}
            {inventoryPreview.length > 0 && (
              <>
                <div className="mt-4 overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-gray-50 text-xs uppercase text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                      <tr>{["Строка","Результат","Основное средство","Инв. номер","Бухгалтерский номер","Комментарий"].map((heading) => <th key={heading} className="px-3 py-2">{heading}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {inventoryPreview.map((row) => <tr key={row.row_number}>
                        <td className="px-3 py-2">{row.row_number}</td>
                        <td className="px-3 py-2">{row.status === "ok" ? "Готово" : row.status === "not_found" ? "Не найдено" : row.status === "ambiguous" ? "Неоднозначно" : row.status === "duplicate" ? "Дубликат" : "Пусто"}</td>
                        <td className="px-3 py-2">{row.asset_name || row.asset_id || "—"}</td>
                        <td className="px-3 py-2">{row.inv_number || "—"}</td>
                        <td className="px-3 py-2">{row.accounting_inv_number || "—"}</td>
                        <td className="px-3 py-2">{row.message}</td>
                      </tr>)}
                    </tbody>
                  </table>
                </div>
                <div className="mt-4 flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setInventoryPreview([])} disabled={inventoryImportBusy}>Сбросить</Button>
                  <Button onClick={() => void applyInventoryPreview()} disabled={inventoryImportBusy || !inventoryPreview.some((row) => row.status === "ok")}>
                    Подтвердить импорт ({inventoryPreview.filter((row) => row.status === "ok").length})
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Page header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Основные средства</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Реестр подвижного состава — локомотивы и вагоны</p>
        </div>
        <div className="flex items-center gap-2">
          {profile?.role !== "master" && <Link href="/dashboard/os/wialon" className="rounded-lg border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 dark:border-blue-900 dark:text-blue-300 dark:hover:bg-blue-950/40">Данные Wialon</Link>}
          {canWrite && <Button variant="outline" onClick={() => { setShowInventoryImport(true); setInventoryImportError(""); setInventoryPreview([]) }}>Импорт инв. номеров</Button>}
          {canWrite && <Button className="gap-2 bg-green-600 hover:bg-green-700" onClick={() => setShowAdd(true)}>
            <Plus className="w-4 h-4"/> Добавить ОС
          </Button>}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
        <button type="button" aria-pressed={!fType && !fBehavior} onClick={() => { setFType(""); setFStatus(""); setFBehavior("") }} className={`text-left rounded-xl border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${!fType && !fBehavior ? "border-blue-500 bg-blue-50 dark:bg-blue-950/40" : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-blue-400"}`}>
          <div className="flex justify-between"><Hash className="w-4 h-4 text-blue-500"/><span className="text-2xl font-bold text-gray-900 dark:text-white">{counts?.total ?? "—"}</span></div><p className="mt-2 text-xs font-medium text-gray-600 dark:text-gray-300">Всего объектов</p>
        </button>
        {assetTypes.map((item) => <button type="button" key={item.code} aria-pressed={fType === item.code} onClick={() => selectType(item.code)} className={`text-left rounded-xl border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${fType === item.code ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40" : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-indigo-400"}`}><div className="flex justify-between"><Train className="w-4 h-4 text-indigo-500"/><span className="text-2xl font-bold text-gray-900 dark:text-white">{counts?.by_asset_type[item.code] ?? 0}</span></div><p className="mt-2 text-xs font-medium text-gray-600 dark:text-gray-300">{item.names.ru || item.code}</p></button>)}
        {[{code:"operational",label:"В эксплуатации",Icon:CheckCircle},{code:"maintenance",label:"На ТО",Icon:Wrench},{code:"repair",label:"В ремонте",Icon:Wrench},{code:"out_of_service",label:"Выведены из ОС",Icon:XCircle}].map(({code,label,Icon}) => <button type="button" key={code} aria-pressed={fBehavior === code} onClick={() => selectBehavior(code)} className={`text-left rounded-xl border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${fBehavior === code ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40" : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-emerald-400"}`}><div className="flex justify-between"><Icon className="w-4 h-4 text-emerald-600"/><span className="text-2xl font-bold text-gray-900 dark:text-white">{counts?.by_status_behavior[code] ?? 0}</span></div><p className="mt-2 text-xs font-medium text-gray-600 dark:text-gray-300">{label}</p></button>)}
        {assetStatuses.map((item) => <button type="button" key={item.code} aria-pressed={fStatus === item.code} onClick={() => { setFBehavior(""); setFStatus((current) => current === item.code ? "" : item.code) }} className={`text-left rounded-xl border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${fStatus === item.code ? "border-violet-500 bg-violet-50 dark:bg-violet-950/40" : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-violet-400"}`}><div className="flex justify-between"><CheckCircle className="w-4 h-4 text-violet-600"/><span className="text-2xl font-bold text-gray-900 dark:text-white">{counts?.by_status[item.code] ?? 0}</span></div><p className="mt-2 text-xs font-medium text-gray-600 dark:text-gray-300">{item.names.ru || item.code}</p></button>)}
        {sectionsData.map((section) => <button type="button" key={section.id} aria-pressed={fSection === section.id} onClick={() => setFSection((current) => current === section.id ? "" : section.id)} className={`text-left rounded-xl border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${fSection === section.id ? "border-amber-500 bg-amber-50 dark:bg-amber-950/40" : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-amber-400"}`}><div className="flex justify-between"><Building2 className="w-4 h-4 text-amber-600"/><span className="text-2xl font-bold text-gray-900 dark:text-white">{counts?.by_section[section.id] ?? 0}</span></div><p className="mt-2 truncate text-xs font-medium text-gray-600 dark:text-gray-300">{section.localized_name || section.name}</p></button>)}
      </div>

      {/* Filters */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"/>
            <Input placeholder="Поиск по инвентарному номеру, наименованию, серии..." className="pl-9"
              value={search} onChange={e => setSearch(e.target.value)}/>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <SlidersHorizontal className="w-4 h-4"/><span>Фильтры:</span>
          </div>

          {/* Type */}
          <div className="relative">
            <select value={fType} onChange={e => setFType(e.target.value as AssetType | "")} className={selCls}>
              <option value="">Все типы</option>
              
              
              
            {assetTypes.map((item) => <option key={item.code} value={item.code}>{item.names.ru || item.code}</option>)}</select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
            {fType && <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-blue-600 rounded-full text-[9px] text-white flex items-center justify-center font-bold">✓</span>}
          </div>

          {/* Source */}
          <div className="relative">
            <select aria-label="Источник" value={fSource} onChange={(event) => setFSource(event.target.value as UnifiedAsset["source"] | "")} className={selCls}>
              <option value="">Все источники</option>
              <option value="toir">ТОИР</option>
              <option value="wialon">Wialon</option>
              <option value="both">ТОИР + Wialon</option>
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
          </div>

          {/* Section */}
          <div className="relative">
            <select aria-label="Участок" value={fSection} onChange={e => setFSection(e.target.value)} className={selCls}>
              <option value="">Все участки</option>
              {sectionsData.map(section => <option key={section.id} value={section.id}>{section.localized_name || section.name}</option>)}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
          </div>

          <label className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 dark:border-gray-600 dark:text-gray-300">
            <input type="checkbox" checked={fWithoutOrgUnit} onChange={(event) => setFWithoutOrgUnit(event.target.checked)} />
            Без участка
          </label>

          {/* Status */}
          <div className="relative">
            <select value={fStatus} onChange={e => setFStatus(e.target.value as AssetStatus | "")} className={selCls}>
              <option value="">Все статусы</option>
              
              
              
              
            {assetStatuses.map((item) => <option key={item.code} value={item.code}>{item.names.ru || item.code}</option>)}</select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
            {fStatus && <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-blue-600 rounded-full text-[9px] text-white flex items-center justify-center font-bold">✓</span>}
          </div>

          {activeFilters > 0 && (
            <button onClick={clearFilters}
              className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 font-medium px-2.5 py-1.5 rounded-lg hover:bg-red-50 transition-colors border border-red-200 dark:border-red-800">
              <X className="w-3.5 h-3.5"/> Сбросить ({activeFilters})
            </button>
          )}
          <div className="ml-auto text-xs text-gray-400">
            Найдено: <span className="font-semibold text-gray-700 dark:text-gray-300">{total}</span>
          </div>
        </div>
      </div>

      {(loadError || statsError) && <div role="alert" className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{loadError || statsError}</div>}
      {canWrite && selectedAssetIds.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-900 dark:bg-blue-950/30">
          <span className="text-sm text-blue-800 dark:text-blue-200">Выбрано основных средств: {selectedAssetIds.length}</span>
          <Button onClick={() => { setBulkOrgUnitId(""); setShowBulkOrgUnit(true) }}>Назначить участок</Button>
        </div>
      )}
      {/* Table */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              {canWrite && <th className="px-3 py-3.5"><input type="checkbox" aria-label="Выбрать все основные средства на странице" checked={allPageSelected} disabled={selectableAssetIds.length === 0} onChange={() => setSelectedAssetIds((current) => allPageSelected ? current.filter((id) => !selectableAssetIds.includes(id)) : Array.from(new Set([...current, ...selectableAssetIds])))} /></th>}
              {["Источник","Тип","Наименование / Номер","Участок","Пробег ТОИР, км","Пробег Wialon, км","Моточасы","Скорость","Связь","Статус / действие"].map((heading) => (
                <th key={heading} className="text-left px-4 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap">{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {filtered.length === 0 && (
              <tr><td colSpan={canWrite ? 11 : 10} className="px-5 py-12 text-center text-sm text-gray-400">
                <Search className="w-8 h-8 mx-auto mb-2 opacity-30"/>
                Ничего не найдено
              </td></tr>
            )}
            {filtered.map((a) => {
              const st = statusConfig[a.status] || { label: a.statusLabel || a.status || "—", icon: CheckCircle, cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300", dot: "bg-blue-500" }
              const typeConfig: Record<string, { label: string; cls: string; Icon: React.ElementType }> = {
                locomotive: { label: "Локомотив", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300", Icon: Train },
                diesel: { label: "Тепловоз", cls: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300", Icon: Train },
                wagon: { label: "Вагон", cls: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300", Icon: Container },
              }
              const tc = typeConfig[a.assetType] || { label: a.assetTypeLabel || a.assetType || "—", cls: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300", Icon: Container }
              const stale = !a.lastMessageAt || Date.now() - new Date(a.lastMessageAt).getTime() > 24 * 60 * 60 * 1000
              const connection = stale ? "Давно" : a.wialonOnline ? "Онлайн" : "Нет связи"
              const sourceLabel = a.source === "both" ? "ТОИР + Wialon" : a.source === "wialon" ? "Wialon" : "ТОИР"
              const orgUnit = sectionsData.find((section) => section.id === a.orgUnitId)
              const rowUnit: WialonUnit | null = a.unitId ? {
                unit_id: a.unitId,
                name: a.name,
                cnm: a.wialonMileage || null,
                cneh: a.engineHours || null,
                speed: a.speed || null,
                last_message_at: a.lastMessageAt,
                is_online: a.wialonOnline ?? false,
                suspect_absolute: a.suspectAbsolute,
                linked_asset: null,
                counter_state: null,
                rejected_count: 0,
              } : null
              const isSelectable = canWrite && a.source !== "wialon" && !a.id.startsWith("wialon:")
              return (
                <tr key={a.id} onClick={a.source !== "wialon" ? () => setSelected(a) : undefined}
                  className={`hover:bg-blue-50/40 dark:hover:bg-blue-950/20 transition-colors ${a.source !== "wialon" ? "cursor-pointer" : ""}`}>
                  {canWrite && <td className="px-3 py-3.5" onClick={(event) => event.stopPropagation()}>{isSelectable ? <input type="checkbox" aria-label={`Выбрать ${a.name}`} checked={selectedAssetIds.includes(a.id)} onChange={(event) => setSelectedAssetIds((current) => event.target.checked ? [...current, a.id] : current.filter((id) => id !== a.id))} /> : "—"}</td>}
                  <td className="px-4 py-3.5">
                    <span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-semibold ${a.source === "both" ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300" : a.source === "wialon" ? "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300" : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"}`}>{sourceLabel}</span>
                  </td>
                  <td className="px-4 py-3.5"><span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-md ${tc.cls}`}><tc.Icon className="w-3 h-3"/>{tc.label}</span></td>
                  <td className="px-4 py-3.5">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{a.name}{a.suspectAbsolute && <span className="ml-2 text-amber-600 dark:text-amber-400" title="Подозрительное значение Wialon">⚠</span>}</p>
                    {(a.invNumber || a.unitId) && <p className="text-xs text-gray-400 truncate max-w-[220px]">{a.invNumber ? `Инв. № ${a.invNumber}` : `ID ${a.unitId}`}</p>}
                  </td>
                  <td className="px-4 py-3.5 text-xs text-gray-600 dark:text-gray-300">{orgUnit?.localized_name || orgUnit?.name || a.depot || "—"}</td>
                  <td className="px-4 py-3.5 text-sm text-gray-700 dark:text-gray-200">{a.source !== "wialon" ? a.mileage || "—" : "—"}</td>
                  <td className="px-4 py-3.5 text-sm text-gray-700 dark:text-gray-200">{a.unitId ? a.wialonMileage || "—" : "—"}</td>
                  <td className="px-4 py-3.5 text-sm text-gray-700 dark:text-gray-200">{a.unitId ? a.engineHours || "—" : "—"}</td>
                  <td className="px-4 py-3.5 text-sm text-gray-700 dark:text-gray-200">{a.unitId ? `${a.speed || "0"} км/ч` : "—"}</td>
                  <td className="px-4 py-3.5">
                    {a.unitId ? <span className={`inline-flex items-center gap-1 text-xs font-medium ${a.wialonOnline ? "text-emerald-600 dark:text-emerald-400" : stale ? "text-amber-600 dark:text-amber-400" : "text-gray-500 dark:text-gray-400"}`}><Radio className="w-3 h-3"/>{connection}</span> : "—"}
                  </td>
                  <td className="px-4 py-3.5">
                    {a.source === "wialon" ? (
                      canWrite && rowUnit ? <Button size="sm" className="whitespace-nowrap" onClick={(event) => { event.stopPropagation(); setSelectedUnit(rowUnit); setShowAdd(true) }}>Создать ОС</Button> : "—"
                    ) : (
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${st.cls}`}><st.icon className="w-3 h-3"/>{a.statusLabel || st.label}</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/30">
            <p className="text-xs text-gray-500">
              Страница <span className="font-semibold">{page + 1}</span> из <span className="font-semibold">{totalPages}</span>
              {" "}· Записей: <span className="font-semibold">{total}</span>
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(0)}
                disabled={page === 0}
                className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >«</button>
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >‹ Назад</button>

              {/* Page numbers */}
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const start = Math.max(0, Math.min(page - 2, totalPages - 5))
                const p = start + i
                return (
                  <button key={p} onClick={() => setPage(p)}
                    className={`w-8 h-7 text-xs rounded border transition-colors ${
                      p === page
                        ? "bg-blue-600 border-blue-600 text-white font-semibold"
                        : "border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
                    }`}
                  >{p + 1}</button>
                )
              })}

              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >Вперёд ›</button>
              <button
                onClick={() => setPage(totalPages - 1)}
                disabled={page >= totalPages - 1}
                className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >»</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
