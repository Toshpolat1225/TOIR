"use client"

import { MapPin, Radio, CheckCircle, AlertTriangle, XCircle, Wrench } from "@/components/ui/icons"
import {
  LOCOMOTIVE_TYPES, intervalCode, intervalKind, intervalTitle,
  type ScheduleItem,
} from "@/lib/maintenance-view"

/* ── Colour and icon per kind of equipment ───────────────────────────────────── */

type AssetStyle = { gradient: string; soft: string; text: string; ring: string; label: string }

export const ASSET_TYPE_STYLE: Record<string, AssetStyle> = {
  locomotive: { gradient: "from-blue-400 to-blue-600", soft: "bg-blue-50 dark:bg-blue-950/40", text: "text-blue-700 dark:text-blue-300", ring: "border-blue-200 dark:border-blue-900", label: "Локомотив" },
  diesel: { gradient: "from-orange-400 to-orange-600", soft: "bg-orange-50 dark:bg-orange-950/40", text: "text-orange-700 dark:text-orange-300", ring: "border-orange-200 dark:border-orange-900", label: "Тепловоз" },
  wagon: { gradient: "from-purple-400 to-purple-600", soft: "bg-purple-50 dark:bg-purple-950/40", text: "text-purple-700 dark:text-purple-300", ring: "border-purple-200 dark:border-purple-900", label: "Вагон" },
  tank_car: { gradient: "from-teal-400 to-teal-600", soft: "bg-teal-50 dark:bg-teal-950/40", text: "text-teal-700 dark:text-teal-300", ring: "border-teal-200 dark:border-teal-900", label: "Цистерна" },
  platform: { gradient: "from-slate-400 to-slate-600", soft: "bg-slate-50 dark:bg-slate-800/40", text: "text-slate-700 dark:text-slate-300", ring: "border-slate-200 dark:border-slate-700", label: "Платформа" },
  special_self_propelled: { gradient: "from-rose-400 to-rose-600", soft: "bg-rose-50 dark:bg-rose-950/40", text: "text-rose-700 dark:text-rose-300", ring: "border-rose-200 dark:border-rose-900", label: "Спецтехника" },
}
const FALLBACK_STYLE: AssetStyle = {
  gradient: "from-gray-400 to-gray-600", soft: "bg-gray-50 dark:bg-gray-800/40", text: "text-gray-700 dark:text-gray-300",
  ring: "border-gray-200 dark:border-gray-700", label: "Техника",
}
export const assetStyle = (type: string | null | undefined): AssetStyle =>
  (type && ASSET_TYPE_STYLE[type]) || FALLBACK_STYLE

function Svg({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={className} aria-hidden="true">
      {children}
    </svg>
  )
}

/** Electric locomotive = bolt, diesel = fuel drop, wagon = boxcar, tank car = tank, platform = flatbed. */
export function AssetTypeIcon({ type, className = "h-5 w-5" }: { type: string | null | undefined; className?: string }) {
  switch (type) {
    case "locomotive":
      return <Svg className={className}><path d="M13 2 4 14h7l-1 8 9-12h-7z" /></Svg>
    case "diesel":
      return <Svg className={className}><path d="M12 2.5c3 4 6 7 6 11a6 6 0 0 1-12 0c0-4 3-7 6-11z" /></Svg>
    case "wagon":
      return <Svg className={className}><rect x="2" y="5" width="20" height="11" rx="1.5" /><path d="M2 10.5h20M9 5v11M15 5v11" /><circle cx="7" cy="19" r="1.6" /><circle cx="17" cy="19" r="1.6" /></Svg>
    case "tank_car":
      return <Svg className={className}><rect x="2.5" y="7" width="19" height="8" rx="4" /><path d="M7 15v2M17 15v2" /><circle cx="7" cy="19" r="1.6" /><circle cx="17" cy="19" r="1.6" /></Svg>
    case "platform":
      return <Svg className={className}><path d="M2 11h20M4 11v3M20 11v3" /><circle cx="7" cy="17.5" r="1.8" /><circle cx="17" cy="17.5" r="1.8" /></Svg>
    case "special_self_propelled":
      return <Svg className={className}><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" /></Svg>
    default:
      return <Svg className={className}><rect x="3" y="6" width="18" height="12" rx="2" /></Svg>
  }
}

/** Coloured tile with the equipment-kind icon. */
export function EquipmentAvatar({ item, size = "md" }: { item: ScheduleItem; size?: "sm" | "md" | "lg" | "xl" }) {
  const style = assetStyle(item.asset_type)
  const box = { sm: "h-9 w-9 rounded-lg", md: "h-11 w-11 rounded-xl", lg: "h-12 w-12 rounded-xl", xl: "h-14 w-14 rounded-xl" }[size]
  const icon = { sm: "h-4 w-4", md: "h-5 w-5", lg: "h-6 w-6", xl: "h-7 w-7" }[size]
  return (
    <span title={item.asset_type_name ?? style.label}
      className={`flex flex-shrink-0 items-center justify-center bg-gradient-to-br text-white shadow-md ${style.gradient} ${box}`}>
      <AssetTypeIcon type={item.asset_type} className={icon} />
    </span>
  )
}

/* ── Chips ──────────────────────────────────────────────────────────────────── */

export function AssetTypeChip({ item }: { item: ScheduleItem }) {
  const style = assetStyle(item.asset_type)
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${style.soft} ${style.text} ${style.ring}`}>
      <AssetTypeIcon type={item.asset_type} className="h-3 w-3" />
      {item.asset_type_name ?? style.label}
    </span>
  )
}

export function SectionChip({ name, onClick }: { name: string; onClick?: () => void }) {
  const cls = "inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-300"
  return onClick ? (
    <button type="button" title={"Фильтр по участку"} onClick={(event) => { event.stopPropagation(); onClick() }}
      className={`${cls} hover:bg-indigo-100 dark:hover:bg-indigo-900/50`}>
      <MapPin className="h-3 w-3" />{name}
    </button>
  ) : (
    <span className={cls}><MapPin className="h-3 w-3" />{name}</span>
  )
}

const STATUS_CHIP: Record<string, { cls: string; Icon: React.ElementType }> = {
  operational: { cls: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300", Icon: CheckCircle },
  maintenance: { cls: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300", Icon: Wrench },
  repair: { cls: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-900 dark:bg-orange-950/40 dark:text-orange-300", Icon: AlertTriangle },
  out_of_service: { cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300", Icon: XCircle },
}

/** State of the machine itself (in service / in maintenance / repair / withdrawn). */
export function AssetStatusChip({ item }: { item: ScheduleItem }) {
  if (!item.asset_status) return null
  const chip = STATUS_CHIP[item.asset_status] ?? STATUS_CHIP.operational
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${chip.cls}`}>
      <chip.Icon className="h-3 w-3" />
      {item.asset_status_name ?? item.asset_status}
    </span>
  )
}

/** Wialon link state; only meaningful for locomotives (wagons have no tracker). */
export function OnlineChip({ item }: { item: ScheduleItem }) {
  if (!item.asset_type || !LOCOMOTIVE_TYPES.has(item.asset_type) || item.asset_online === null || item.asset_online === undefined) return null
  return item.asset_online ? (
    <span className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
      <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" /></span>
      <Radio className="h-3 w-3" />{"Wialon онлайн"}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-0.5 text-[11px] font-semibold text-gray-500 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-400">
      <Radio className="h-3 w-3 opacity-60" />{"Нет связи"}
    </span>
  )
}

/* ── Maintenance interval chip (ТО-1, ТР-2, СР, КР) ────────────────────────────── */

function IntervalIcon({ type, className = "h-3 w-3" }: { type: string; className?: string }) {
  switch (intervalKind(type)) {
    case "to":
      return <Svg className={className}><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z" /></Svg>
    case "tr":
      return <Svg className={className}><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" /></Svg>
    case "sr":
      return <Svg className={className}><path d="M12 3 3 8l9 5 9-5z" /><path d="m3 13 9 5 9-5" /></Svg>
    case "kr":
      return <Svg className={className}><path d="M3 21V10l6 4v-4l6 4V6h6v15z" /></Svg>
    default:
      return <Svg className={className}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Svg>
  }
}

/** Filled chip with the interval's own colour, an icon for its family and the full name on hover. */
export function IntervalChip({ type, color, large = false }: { type: string; color: string; large?: boolean }) {
  return (
    <span title={intervalTitle(type)} style={{ backgroundColor: color }}
      className={`inline-flex items-center gap-1 rounded-lg font-bold text-white shadow-sm ${large ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-[11px]"}`}>
      <IntervalIcon type={type} className={large ? "h-3.5 w-3.5" : "h-3 w-3"} />
      {intervalCode(type)}
    </span>
  )
}
