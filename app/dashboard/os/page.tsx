"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { supabase } from "@/lib/supabase"
import { useSections } from "@/lib/use-sections"
import {
  Train, Container, Plus, Search, X, Save, ChevronDown,
  CheckCircle, Wrench, AlertTriangle, XCircle,
  CalendarDays, SlidersHorizontal, Pencil, Building2, Hash, Radio, Trash2
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/* ════════════════════════════════════════
   ТИПЫ
════════════════════════════════════════ */
type AssetType = "locomotive" | "wagon" | "diesel"
type AssetStatus = "operational" | "maintenance" | "repair" | "out_of_service"

type FixedAsset = {
  id:           string   // инвентарный номер
  name:         string   // наименование
  assetType:    AssetType
  series:       string
  depot:        string
  status:       AssetStatus
  commDate:     string   // дата ввода в эксплуатацию
  yearBuilt:    string
  mileage:      string
  lastMaint:    string
  nextMaint:    string
  invNumber:    string   // инвентарный номер ОС
  initialCost:  string   // первоначальная стоимость (сум)
  owner:        string
  /** Пробег синхронизирован из Wialon */
  wialonLastSync?: string | null
  wialonOnline?: boolean
}

/* ════════════════════════════════════════
   СПРАВОЧНИКИ
════════════════════════════════════════ */
const statusConfig: Record<AssetStatus, { label: string; icon: React.ElementType; cls: string; dot: string }> = {
  operational:    { label: "В эксплуатации", icon: CheckCircle,   cls: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",   dot: "bg-green-500" },
  maintenance:    { label: "На ТО",          icon: Wrench,        cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",   dot: "bg-amber-500" },
  repair:         { label: "Ремонт",         icon: AlertTriangle, cls: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400", dot: "bg-orange-500" },
  out_of_service: { label: "Выведен",        icon: XCircle,       cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",           dot: "bg-red-500" },
}

/* ════════════════════════════════════════
   МОДАЛЫ
════════════════════════════════════════ */

/* ════════════════════════════════════════
   МОДАЛ ПРОСМОТРА / РЕДАКТИРОВАНИЯ
════════════════════════════════════════ */
function AssetModal({ asset, onClose, onSave, onDelete, sections }: {
  asset: FixedAsset
  onClose: () => void
  onSave: (a: FixedAsset) => void
  onDelete?: (a: FixedAsset) => void
  sections: string[]
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

  const st = statusConfig[status]
  const typeLabels: Record<string, { label: string; gradient: string; Icon: React.ElementType }> = {
    locomotive: { label: "Локомотив", gradient: "bg-gradient-to-r from-blue-600 to-blue-700", Icon: Train },
    diesel:     { label: "Тепловоз",  gradient: "bg-gradient-to-r from-orange-600 to-orange-700", Icon: Train },
    wagon:      { label: "Вагон",     gradient: "bg-gradient-to-r from-purple-600 to-purple-700", Icon: Container },
  }
  const typeInfo = typeLabels[asset.assetType] || typeLabels.locomotive

  const handleSave = () => {
    onSave({ ...asset, commDate, status, depot, mileage, lastMaint, nextMaint, initialCost, owner })
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

        {/* Шапка */}
        <div className={`flex items-center justify-between px-6 py-4 rounded-t-2xl ${typeInfo.gradient} text-white flex-shrink-0`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
              <typeInfo.Icon className="w-5 h-5"/>
            </div>
            <div>
              <p className="text-xs opacity-80 font-medium">
                {typeInfo.label} {asset.series && `· ${asset.series}`}
              </p>
              <p className="text-lg font-bold leading-tight">{asset.name}</p>
              {asset.invNumber && <p className="text-xs opacity-70">Инв. № {asset.invNumber}</p>}
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/20 transition-colors">
            <X className="w-5 h-5"/>
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Карточка серия / депо */}
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

          {/* Дата ввода в эксплуатацию — выделена */}
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

          {/* Основные поля */}
          <div className="grid grid-cols-2 gap-4">

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Статус</p>
              {editing ? (
                <div className="relative">
                  <select value={status} onChange={e => setStatus(e.target.value as AssetStatus)} className={selCls}>
                    <option value="operational">В эксплуатации</option>
                    <option value="maintenance">На ТО</option>
                    <option value="repair">Ремонт</option>
                    <option value="out_of_service">Выведен</option>
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
                </div>
              ) : (
                <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg ${st.cls}`}>
                  <st.icon className="w-3.5 h-3.5"/>{st.label}
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
                  {(asset.assetType === "locomotive" || asset.assetType === "diesel") && asset.wialonLastSync && (
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

        {/* Подвал */}
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
            {!editing ? (
              <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={() => setEditing(true)}>
                <Pencil className="w-4 h-4"/> Редактировать
              </Button>
            ) : (
              <Button className="gap-2 bg-green-600 hover:bg-green-700" onClick={handleSave}>
                <Save className="w-4 h-4"/> Сохранить
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════
   МОДАЛ ДОБАВЛЕНИЯ НОВОГО ОС
════════════════════════════════════════ */
function AddAssetModal({ onClose, onSave, sections }: { onClose: () => void; onSave: (a: FixedAsset) => void; sections: string[] }) {
  const [assetType,   setAssetType]   = useState<AssetType>("locomotive")
  const [name,        setName]        = useState("")  // Номер/Наименование (основное поле)
  const [series,      setSeries]      = useState("")
  const [depot,       setDepot]       = useState(sections[0] ?? "")
  const [commDate,    setCommDate]    = useState("")
  const [yearBuilt,   setYearBuilt]   = useState("")
  const [initialCost, setInitialCost] = useState("")
  const [invNumber,   setInvNumber]   = useState("")  // Инвентарный номер
  const [owner,       setOwner]       = useState("РЖД")
  const [error,       setError]       = useState("")

  const handleSave = () => {
    if (!name.trim() || !commDate.trim()) {
      setError("Заполните обязательные поля: Наименование, Дата ввода")
      return
    }
    // Генерируем уникальный ID
    const generatedId = `${assetType === "locomotive" ? "LOC" : assetType === "diesel" ? "DSL" : "WAG"}-${Date.now()}`
    onSave({
      id: generatedId,
      name: name.trim(),
      assetType,
      series,
      depot,
      status: "operational",
      commDate: commDate.trim(),
      yearBuilt,
      mileage: "0",
      lastMaint: "—",
      nextMaint: "—",
      invNumber: invNumber.trim(),
      initialCost,
      owner,
    })
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
              <p className="text-xs text-green-200">Основные средства</p>
              <p className="text-base font-bold">Добавить новый объект ОС</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/20 transition-colors">
            <X className="w-5 h-5"/>
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Тип */}
          <div>
            <p className={lbl}>Тип объекта</p>
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

          {/* Дата ввода — ключевое поле */}
          <div className="rounded-xl border-2 border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-3">
            <label className="flex items-center gap-2 text-xs font-bold text-blue-700 dark:text-blue-400 mb-2">
              <CalendarDays className="w-3.5 h-3.5"/> Дата ввода в эксплуатацию <span className="text-red-500">*</span>
            </label>
            <input value={commDate} onChange={e => setCommDate(e.target.value)} className={inp + " border-blue-300 dark:border-blue-700 focus:ring-blue-500 font-semibold"} placeholder="ДД.ММ.ГГГГ"/>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={lbl}>Год постройки</label>
              <input value={yearBuilt} onChange={e => setYearBuilt(e.target.value)} className={inp} placeholder="2015"/>
            </div>
            <div>
              <label className={lbl}>Номер вагона</label>
              <input value={initialCost} onChange={e => setInitialCost(e.target.value)} className={inp} placeholder="33-9909"/>
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
   СТРАНИЦА
════════════════════════════════════════ */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromRow(r: any): FixedAsset {
  return {
    id:               r.id,
    name:             r.name,
    assetType:        r.asset_type,
    series:           r.series,
    depot:            r.depot,
    status:           r.status,
    commDate:         r.comm_date,
    yearBuilt:        r.year_built,
    mileage:          r.mileage ?? "",
    lastMaint:        r.last_maint,
    nextMaint:        r.next_maint,
    invNumber:        r.inv_number,
    initialCost:      r.initial_cost,
    owner:            r.owner,
    wialonLastSync:   r.wialon_last_sync ?? null,
    wialonOnline:     !!r.wialon_online,
  }
}

function toRow(a: FixedAsset) {
  return {
    id:           a.id,
    name:         a.name,
    asset_type:   a.assetType,
    series:       a.series,
    depot:        a.depot,
    status:       a.status,
    comm_date:    a.commDate,
    year_built:   a.yearBuilt,
    mileage:      a.mileage,
    last_maint:   a.lastMaint,
    next_maint:   a.nextMaint,
    inv_number:   a.invNumber,
    initial_cost: a.initialCost,
    owner:        a.owner,
  }
}

const PAGE_SIZE = 50

export default function OsPage() {
  const { sections } = useSections()
  const [assets,    setAssets]    = useState<FixedAsset[]>([])
  const [total,     setTotal]     = useState(0)
  const [counts,    setCounts]    = useState({ total:0, loco:0, wagon:0, operational:0, repair:0, retired:0 })
  const [page,      setPage]      = useState(0)
  const [loading,   setLoading]   = useState(true)
  const [selected,  setSelected]  = useState<FixedAsset | null>(null)
  const [showAdd,   setShowAdd]   = useState(false)
  const [search,    setSearch]    = useState("")
  const [fType,     setFType]     = useState<AssetType | "">("")
  const [fDepot,    setFDepot]    = useState("")
  const [fStatus,   setFStatus]   = useState<AssetStatus | "">("")
  const [allDepots, setAllDepots] = useState<string[]>([])
  
  // Ref для фильтров в real-time подписке (чтобы не пересоздавать канал)
  const filtersRef = useRef({ page: 0, search: "", fType: "" as AssetType | "", fDepot: "", fStatus: "" as AssetStatus | "" })

  // Загружаем счётчики и список депо один раз (оптимизированные запросы)
  const fetchCounts = useCallback(async () => {
    // Параллельные запросы для подсчёта
    const [
      { count: totalCount },
      { count: locoCount },
      { count: wagonCount },
      { count: operCount },
      { count: maintCount },
      { count: repairCount },
      { count: retiredCount },
      { data: depotsData }
    ] = await Promise.all([
      supabase.from("fixed_assets").select("*", { count: "exact", head: true }),
      supabase.from("fixed_assets").select("*", { count: "exact", head: true }).eq("asset_type", "locomotive"),
      supabase.from("fixed_assets").select("*", { count: "exact", head: true }).eq("asset_type", "wagon"),
      supabase.from("fixed_assets").select("*", { count: "exact", head: true }).eq("status", "operational"),
      supabase.from("fixed_assets").select("*", { count: "exact", head: true }).eq("status", "maintenance"),
      supabase.from("fixed_assets").select("*", { count: "exact", head: true }).eq("status", "repair"),
      supabase.from("fixed_assets").select("*", { count: "exact", head: true }).eq("status", "out_of_service"),
      supabase.from("fixed_assets").select("depot").not("depot", "is", null).not("depot", "eq", "").limit(1000)
    ])

    setCounts({
      total: totalCount ?? 0,
      loco: locoCount ?? 0,
      wagon: wagonCount ?? 0,
      operational: operCount ?? 0,
      repair: (maintCount ?? 0) + (repairCount ?? 0),
      retired: retiredCount ?? 0
    })

    // Уникальные депо
    if (depotsData) {
      const deps = [...new Set(depotsData.map((r: { depot: string }) => r.depot))].filter(Boolean).sort()
      setAllDepots(deps as string[])
    }
  }, [])

  const fetchAssets = useCallback(async (pg: number, q: string, ft: string, fd: string, fs: string) => {
    setLoading(true)
    try {
      let query = supabase
        .from("fixed_assets")
        .select("*", { count: "exact" })
        .order("created_at", { ascending: false })
        .range(pg * PAGE_SIZE, pg * PAGE_SIZE + PAGE_SIZE - 1)

      if (ft) query = query.eq("asset_type", ft)
      if (fd) query = query.eq("depot", fd)
      if (fs) query = query.eq("status", fs)
      if (q)  query = query.or(
        `name.ilike.%${q}%,series.ilike.%${q}%,inv_number.ilike.%${q}%,id.ilike.%${q}%,depot.ilike.%${q}%,owner.ilike.%${q}%`
      )

      const { data, count, error } = await query
      if (!error && data) {
        setAssets(data.map(fromRow))
        setTotal(count ?? 0)
      } else {
        setAssets([])
        setTotal(0)
      }
    } catch (e) {
      console.error("Ошибка загрузки ОС:", e)
      setAssets([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchCounts() }, [fetchCounts])

  // Обновляем ref при изменении фильтров
  useEffect(() => {
    filtersRef.current = { page, search, fType, fDepot, fStatus }
  }, [page, search, fType, fDepot, fStatus])

  // Real-time подписка на изменения в fixed_assets (используем ref для фильтров)
  useEffect(() => {
    const channel = supabase
      .channel("os_sync")
      .on("postgres_changes", { event: "*", schema: "public", table: "fixed_assets" }, () => {
        const f = filtersRef.current
        fetchAssets(f.page, f.search, f.fType, f.fDepot, f.fStatus)
        fetchCounts()
      })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [fetchAssets, fetchCounts])

  // Сброс страницы при смене фильтров
  useEffect(() => {
    setPage(0)
  }, [search, fType, fDepot, fStatus])

  useEffect(() => {
    fetchAssets(page, search, fType, fDepot, fStatus)
  }, [fetchAssets, page, search, fType, fDepot, fStatus])

  const totalPages    = Math.ceil(total / PAGE_SIZE)
  const activeFilters = [fType, fDepot, fStatus].filter(Boolean).length
  const clearFilters  = () => { setFType(""); setFDepot(""); setFStatus(""); setSearch("") }
  const filtered      = assets  // фильтрация на сервере

  const handleSave = async (updated: FixedAsset) => {
    const { error } = await supabase.from("fixed_assets").upsert(toRow(updated))
    if (!error) {
      fetchAssets(page, search, fType, fDepot, fStatus)
      fetchCounts()
    }
    setSelected(null)
  }

  const handleDelete = async (a: FixedAsset) => {
    const { error } = await supabase.from("fixed_assets").delete().eq("id", a.id)
    if (!error) {
      fetchAssets(page, search, fType, fDepot, fStatus)
      fetchCounts()
      setSelected(null)
    } else {
      alert("Не удалось удалить: " + (error.message || "ошибка БД"))
    }
  }

  const handleAdd = async (a: FixedAsset) => {
    const { error } = await supabase.from("fixed_assets").insert(toRow(a))
    if (!error) {
      fetchAssets(0, search, fType, fDepot, fStatus)
      fetchCounts()
      setPage(0)
    }
    setShowAdd(false)
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
      {selected  && <AssetModal asset={selected}  onClose={() => setSelected(null)} onSave={handleSave} onDelete={handleDelete} sections={sections}/>}
      {showAdd   && <AddAssetModal onClose={() => setShowAdd(false)} onSave={handleAdd} sections={sections}/>}

      {/* Заголовок */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Основные средства</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Реестр подвижного состава — локомотивы и вагоны</p>
        </div>
        <Button className="gap-2 bg-green-600 hover:bg-green-700" onClick={() => setShowAdd(true)}>
          <Plus className="w-4 h-4"/> Добавить ОС
        </Button>
      </div>

      {/* KPI карточки */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { label:"Всего объектов",    value: counts.total,       color:"blue",   icon: Hash },
          { label:"Локомотивы",        value: counts.loco,        color:"blue",   icon: Train },
          { label:"Вагоны",            value: counts.wagon,       color:"purple", icon: Container },
          { label:"В эксплуатации",    value: counts.operational, color:"green",  icon: CheckCircle },
          { label:"На ТО / Ремонт",    value: counts.repair,      color:"amber",  icon: Wrench },
          { label:"Выведены из ОС",    value: counts.retired,     color:"red",    icon: XCircle },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className={`bg-${color}-50 dark:bg-${color}-950/30 rounded-xl border border-${color}-200 dark:border-${color}-800 p-4`}>
            <div className="flex items-center justify-between mb-2">
              <Icon className={`w-4 h-4 text-${color}-500`}/>
              <span className={`text-2xl font-bold text-${color}-700 dark:text-${color}-300`}>{value}</span>
            </div>
            <p className={`text-xs font-medium text-${color}-600 dark:text-${color}-400 leading-tight`}>{label}</p>
          </div>
        ))}
      </div>

      {/* Фильтры */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"/>
            <Input placeholder="Поиск по номеру, наименованию, депо..." className="pl-9"
              value={search} onChange={e => setSearch(e.target.value)}/>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <SlidersHorizontal className="w-4 h-4"/><span>Фильтры:</span>
          </div>

          {/* Тип */}
          <div className="relative">
            <select value={fType} onChange={e => setFType(e.target.value as AssetType | "")} className={selCls}>
              <option value="">Все типы</option>
              <option value="locomotive">Локомотивы</option>
              <option value="diesel">Тепловозы</option>
              <option value="wagon">Вагоны</option>
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
            {fType && <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-blue-600 rounded-full text-[9px] text-white flex items-center justify-center font-bold">✓</span>}
          </div>

          {/* Депо */}
          <div className="relative">
            <select value={fDepot} onChange={e => setFDepot(e.target.value)} className={selCls}>
              <option value="">Все депо</option>
              {allDepots.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
            {fDepot && <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-blue-600 rounded-full text-[9px] text-white flex items-center justify-center font-bold">✓</span>}
          </div>

          {/* Статус */}
          <div className="relative">
            <select value={fStatus} onChange={e => setFStatus(e.target.value as AssetStatus | "")} className={selCls}>
              <option value="">Все статусы</option>
              <option value="operational">В эксплуатации</option>
              <option value="maintenance">На ТО</option>
              <option value="repair">Ремонт</option>
              <option value="out_of_service">Выведен</option>
            </select>
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

      {/* Таблица */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              {["Тип","Наименование / Номер","Дата ввода в экспл.","Депо / Участок","Год","Пробег (км)","Статус"].map(h => (
                <th key={h} className="text-left px-4 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="px-5 py-12 text-center text-sm text-gray-400">
                <Search className="w-8 h-8 mx-auto mb-2 opacity-30"/>
                Ничего не найдено
              </td></tr>
            )}
            {filtered.map(a => {
              const st = statusConfig[a.status]
              const typeConfig = {
                locomotive: { label: "Локомотив", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300", Icon: Train },
                diesel:     { label: "Тепловоз",  cls: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300", Icon: Train },
                wagon:      { label: "Вагон",     cls: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300", Icon: Container },
              }
              const tc = typeConfig[a.assetType] || typeConfig.locomotive
              return (
                <tr key={a.id} onClick={() => setSelected(a)}
                  className="hover:bg-blue-50/40 dark:hover:bg-blue-950/20 cursor-pointer transition-colors">
                  <td className="px-4 py-3.5">
                    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-md ${tc.cls}`}>
                      <tc.Icon className="w-3 h-3"/>
                      {tc.label}
                    </span>
                  </td>
                  <td className="px-4 py-3.5">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      {a.name}
                      {a.initialCost && <span className="ml-2 text-blue-600 dark:text-blue-400 font-bold">{a.initialCost}</span>}
                    </p>
                    {a.invNumber && <p className="text-xs text-gray-400 truncate max-w-[220px]">Инв. № {a.invNumber}</p>}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-1.5">
                      <CalendarDays className="w-3.5 h-3.5 text-blue-500 flex-shrink-0"/>
                      <span className="text-sm font-semibold text-blue-600 dark:text-blue-400 whitespace-nowrap">{a.commDate || "—"}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-300">
                      <Building2 className="w-3 h-3 flex-shrink-0 text-gray-400"/>
                      <span className="truncate max-w-[140px]" title={a.depot}>{a.depot}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3.5 text-sm text-gray-600 dark:text-gray-300">{a.yearBuilt}</td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">{a.mileage || "—"}</span>
                      {(a.assetType === "locomotive" || a.assetType === "diesel") && (a.wialonOnline || a.wialonLastSync) && (
                        <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400" title={a.wialonLastSync ? `Обновлено: ${new Date(a.wialonLastSync).toLocaleString("ru-RU")}` : "Данные из Wialon"}>
                          <Radio className="w-2.5 h-2.5"/> Wialon
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${st.cls}`}>
                      <st.icon className="w-3 h-3"/>{st.label}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* Пагинация */}
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

              {/* Номера страниц */}
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
