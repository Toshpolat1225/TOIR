"use client"

import { Fragment, useState, useEffect, useCallback, useRef } from "react"
import {
  api, type Employee, type MaintenanceBlockReason, type MaintenanceDecision, type MaintenanceDisruption,
  type MaintenanceDisruptionCreate, type MaintenanceKpis, type MaintenancePlan, type MaintenanceScheduleItem,
  type MileageHistory, type Section, type WorkType,
} from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import {
  AssetStatusChip, AssetTypeIcon, EquipmentAvatar, IntervalChip, OnlineChip, SectionChip, assetStyle,
} from "./_components/EquipmentBadge"
import { RescheduleDialog } from "./_components/RescheduleDialog"
import { LivePlanCard } from "./_components/LivePlanCard"
import { LiveOverview } from "./_components/LiveOverview"
import { BaselineDialog, BlockDialog, DisruptionDialog, WaiveDialog } from "./_components/PlanDialogs"
import {
  CONFIDENCE_LABEL, NEAR_THRESHOLD_PCT, NO_DEPOT, PRIORITY_CLS, buildCsv, compareEnriched, defaultSortDir, enrich,
  fmtNum, formatDate, priorityTone,
  MAX_RESCHEDULE_DAYS, clampShift, equipmentSubtitle, equipmentTitle, groupByUnit, intervalCode, intervalTitle,
  inventoryNumberOf, isInRange, isReschedulable, isTestInterval, paletteForCode, parseDate, shiftDate,
  shiftFromPixels, toIsoDate, toNum, validateRescheduleDate,
  type Enriched, type RecLevel, type SortKey, type UnitGroup,
} from "@/lib/maintenance-view"

import {
  Calendar, Wrench, CheckCircle, Clock, AlertTriangle,
  BarChart3, List, ChevronLeft, ChevronRight, Info, Plus, X, ChevronDown,
  Gauge, Bell, Filter, Search, RotateCcw, Lock
} from "@/components/ui/icons"

/* ═══════════════════════════════════════
   ДАННЫЕ
═══════════════════════════════════════ */
type Status = "upcoming" | "in_progress" | "completed" | "overdue" | "blocked"
type ScheduleItem = MaintenanceScheduleItem

type ToastNotification = {
  id: string
  type: "warning" | "error" | "success" | "info"
  title: string
  message: string
  timestamp: Date
  read: boolean
}

/* ═══════════════════════════════════════
   TOAST NOTIFICATIONS
═══════════════════════════════════════ */
function ToastContainer({ 
  notifications, 
  onDismiss 
}: { 
  notifications: ToastNotification[]
  onDismiss: (id: string) => void 
}) {
  if (notifications.length === 0) return null

  const iconMap = {
    warning: <AlertTriangle className="w-5 h-5 text-amber-500" />,
    error: <AlertTriangle className="w-5 h-5 text-red-500" />,
    success: <CheckCircle className="w-5 h-5 text-green-500" />,
    info: <Info className="w-5 h-5 text-blue-500" />,
  }

  const bgMap = {
    warning: "bg-amber-50 border-amber-200 dark:bg-amber-950 dark:border-amber-800",
    error: "bg-red-50 border-red-200 dark:bg-red-950 dark:border-red-800",
    success: "bg-green-50 border-green-200 dark:bg-green-950 dark:border-green-800",
    info: "bg-blue-50 border-blue-200 dark:bg-blue-950 dark:border-blue-800",
  }

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-md">
      {notifications.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-start gap-3 p-4 rounded-xl border shadow-lg animate-in slide-in-from-right ${bgMap[toast.type]}`}
        >
          {iconMap[toast.type]}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">{toast.title}</p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">{toast.message}</p>
          </div>
          <button
            onClick={() => onDismiss(toast.id)}
            className="p-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════
   NOTIFICATION BELL
═══════════════════════════════════════ */
function NotificationBell({
  notifications,
  onMarkAsRead,
  onMarkAllAsRead,
  onClear,
}: {
  notifications: ToastNotification[]
  onMarkAsRead: (id: string) => void
  onMarkAllAsRead: () => void
  onClear: () => void
}) {
  const locale = "ru-RU"
  const [isOpen, setIsOpen] = useState(false)
  const unreadCount = notifications.filter(n => !n.read).length
  const criticalCount = notifications.filter(n => n.type === "error" && !n.read).length

  const iconMap = {
    warning: <AlertTriangle className="w-4 h-4 text-amber-500" />,
    error: <AlertTriangle className="w-4 h-4 text-red-500" />,
    success: <CheckCircle className="w-4 h-4 text-green-500" />,
    info: <Info className="w-4 h-4 text-blue-500" />,
  }

  const bgMap = {
    warning: "bg-amber-50 dark:bg-amber-950/50",
    error: "bg-red-50 dark:bg-red-950/50",
    success: "bg-green-50 dark:bg-green-950/50",
    info: "bg-blue-50 dark:bg-blue-950/50",
  }

  const formatTime = (date: Date) => {
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    
    if (minutes < 1) return "только что"
    if (minutes < 60) return `${minutes} ${"мин. назад"}`
    if (hours < 24) return `${hours} ${"ч. назад"}`
    return date.toLocaleDateString(locale, { day: "numeric", month: "short" })
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`relative p-2.5 rounded-xl transition-all ${
          criticalCount > 0
            ? "bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400 animate-pulse"
            : unreadCount > 0
              ? "bg-amber-100 text-amber-600 dark:bg-amber-950 dark:text-amber-400"
              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
        }`}
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className={`absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-bold rounded-full ${
            criticalCount > 0 ? "bg-red-500 text-white" : "bg-amber-500 text-white"
          }`}>
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div 
            className="fixed inset-0 z-40" 
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 top-full mt-2 w-96 max-h-[500px] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 z-50 overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-bold text-gray-900 dark:text-white">{"Уведомления"}</span>
                {unreadCount > 0 && (
                  <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400">
                    {unreadCount} {"новых"}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {unreadCount > 0 && (
                  <button
                    onClick={onMarkAllAsRead}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline px-2 py-1"
                  >
                    {"Прочитать все"}
                  </button>
                )}
                {notifications.length > 0 && (
                  <button
                    onClick={onClear}
                    className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 px-2 py-1"
                  >
                    {"Очистить"}
                  </button>
                )}
              </div>
            </div>

            {/* Notifications list */}
            <div className="max-h-[400px] overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                  <Bell className="w-10 h-10 opacity-20 mb-2" />
                  <p className="text-sm">{"Нет уведомлений"}</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                  {notifications.map((notif) => (
                    <div
                      key={notif.id}
                      onClick={() => onMarkAsRead(notif.id)}
                      className={`flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50 ${
                        !notif.read ? bgMap[notif.type] : ""
                      }`}
                    >
                      <div className="flex-shrink-0 mt-0.5">
                        {iconMap[notif.type]}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <p className={`text-sm font-medium ${!notif.read ? "text-gray-900 dark:text-white" : "text-gray-600 dark:text-gray-400"}`}>
                            {notif.title}
                          </p>
                          {!notif.read && (
                            <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0 mt-1.5" />
                          )}
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">
                          {notif.message}
                        </p>
                        <p className="text-[10px] text-gray-400 mt-1">
                          {formatTime(notif.timestamp)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            {notifications.filter(n => n.type === "error").length > 0 && (
              <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-800 bg-red-50 dark:bg-red-950/30">
                <p className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />
                  {notifications.filter(n => n.type === "error").length} {"критических уведомлений требуют внимания"}
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════
   КОНФИГУРАЦИЯ ТИПОВ И СТАТУСОВ
═══════════════════════════════════════ */
const typeConfig: Record<string, { color: string; bar: string; text: string; border: string }> = {
  "ТО-1": { color:"#60a5fa", bar:"bg-blue-400",   text:"text-blue-700 dark:text-blue-300",   border:"border-blue-300" },
  "ТО-2": { color:"#3b82f6", bar:"bg-blue-500",   text:"text-blue-700 dark:text-blue-300",   border:"border-blue-400" },
  "ТО-3": { color:"#8b5cf6", bar:"bg-purple-500", text:"text-purple-700 dark:text-purple-300",border:"border-purple-400" },
  "ТР-1": { color:"#f59e0b", bar:"bg-amber-500",  text:"text-amber-700 dark:text-amber-300", border:"border-amber-400" },
  "ТР-2": { color:"#f97316", bar:"bg-orange-500", text:"text-orange-700 dark:text-orange-300",border:"border-orange-400" },
  "ТР-3": { color:"#ef4444", bar:"bg-red-500",    text:"text-red-700 dark:text-red-300",     border:"border-red-400" },
  "СР":   { color:"#dc2626", bar:"bg-red-600",    text:"text-red-700 dark:text-red-300",     border:"border-red-500" },
  "КР":   { color:"#991b1b", bar:"bg-red-800",    text:"text-red-800 dark:text-red-200",     border:"border-red-700" },
  "ВНП":  { color:"#6b7280", bar:"bg-gray-500",   text:"text-gray-700 dark:text-gray-300",   border:"border-gray-400" },
}

// The API sends "ТО-1 — ТО-1" (code — name) while the colour table is keyed by the code only.
const typeCfg = (type: string) => typeConfig[intervalCode(type)] ?? typeConfig[type] ?? paletteForCode(intervalCode(type))

const statusConfig: Record<Status, { label: string; icon: React.ElementType; cls: string; dot: string }> = {
  upcoming:    { label:"Запланировано", icon:Clock,         cls:"bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",        dot:"bg-gray-400" },
  in_progress: { label:"Выполняется",  icon:Wrench,        cls:"bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",     dot:"bg-amber-500" },
  completed:   { label:"Выполнено",    icon:CheckCircle,   cls:"bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",     dot:"bg-green-500" },
  overdue:     { label:"Просрочено",   icon:AlertTriangle, cls:"bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",             dot:"bg-red-500" },
  blocked:     { label:"Заблокировано", icon:Lock,         cls:"bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300", dot:"bg-orange-500" },
}

/* ═══════════════════════════════════════
   ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
═══════════════════════════════════════ */
function addDays(d: Date, n: number): Date {
  const r = new Date(d); r.setDate(r.getDate() + n); return r
}
function diffDays(a: Date, b: Date): number {
  return Math.floor((b.getTime() - a.getTime()) / 86400000)
}
function durationDays(h: number): number {
  return Math.max(0.5, h / 24)
}

/* ═══════════════════════════════════════
   ПРОБЕГ: подписи и стили интерфейса
   (вся логика расчёта и сортировки — в lib/maintenance-view.ts, там же её тесты)
═══════════════════════════════════════ */
const TABLE_PAGE_SIZES = [25, 50, 100, 200]
const GANTT_UNITS_PER_PAGE = 15
const GANTT_LANE_PX = 44 // bar height (40) + gap
const PREFS_KEY = "maintenance.view.v2"

const SORT_LABELS: Record<SortKey, string> = {
  mileage: "Пробег",
  remaining: "Осталось до ТО",
  progress: "Выработка интервала",
  date: "Дата ТО",
  unit: "Название",
  status: "Статус",
  urgency: "Срочность",
  priority: "Приоритет",
}

const REC_CLS: Record<RecLevel, string> = {
  critical: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300",
  warning: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300",
  info: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300",
  ok: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300",
}
const LEVEL_DOT: Record<RecLevel, string> = {
  critical: "bg-red-500", warning: "bg-amber-500", info: "bg-blue-500", ok: "bg-emerald-500",
}

const URGENCY_LABEL: Record<string, { label: string; cls: string }> = {
  high: { label: "Высокая", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  medium: { label: "Средняя", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  low: { label: "Низкая", cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300" },
}

// Only these moves are accepted by the API (maintenance.update_plan); anything else is a 409.
// A maintenance obligation is never cancelled by hand: it is blocked (reason) or, by an administrator, waived.
const PLAN_TRANSITIONS: Record<string, { to: MaintenancePlan["status"]; label: string; danger?: boolean }[]> = {
  scheduled: [
    { to: "in_progress", label: "Начать выполнение" },
  ],
  in_progress: [
    { to: "completed", label: "Завершить ТО" },
  ],
}
const PLAN_STATUS_LABEL: Record<string, string> = {
  scheduled: "Запланировано",
  in_progress: "Выполняется",
  completed: "Выполнено",
  cancelled: "Отменено",
  blocked: "Заблокировано",
  covered: "Перекрыто старшим ТО",
  waived: "Цикл пропущен",
}
const MILEAGE_SOURCE_LABEL: Record<string, string> = { wialon: "Wialon", gtk: "ГТК", manual: "Вручную" }

const assetHref = (item: ScheduleItem) =>
  `/dashboard/directories/assets?q=${encodeURIComponent(inventoryNumberOf(item))}`

function plural(n: number, forms: [string, string, string]): string {
  const mod100 = n % 100
  const mod10 = n % 10
  if (mod100 >= 11 && mod100 <= 14) return forms[2]
  if (mod10 === 1) return forms[0]
  if (mod10 >= 2 && mod10 <= 4) return forms[1]
  return forms[2]
}

const TABLE_COLUMNS: { label: string; sort?: SortKey }[] = [
  { label: "№" },
  { label: "Ед.ТПС", sort: "unit" },
  { label: "Пробег, км", sort: "mileage" },
  { label: "Вид ТО" },
  { label: "Порог ТО, км" },
  { label: "До ТО", sort: "remaining" },
  { label: "Выработка", sort: "progress" },
  { label: "Срочность", sort: "urgency" },
  { label: "Приоритет", sort: "priority" },
  { label: "Дата", sort: "date" },
  { label: "Статус", sort: "status" },
  { label: "Рекомендация" },
  { label: "Действие" },
]

/* ═══════════════════════════════════════
   КОМПОНЕНТ ДИАГРАММЫ ГАНТА
═══════════════════════════════════════ */
type DragState = { id: string; shift: number; moved: boolean; dayWidth: number; x: number; y: number; item: ScheduleItem }

function GanttChart({ items, rangeStart, rangeDays, onCreateOrder, onOpen, canReschedule = false, onReschedule }: {
  items: ScheduleItem[]
  rangeStart: Date
  rangeDays: number
  onCreateOrder?: (item: ScheduleItem) => void
  onOpen?: (item: ScheduleItem) => void
  canReschedule?: boolean
  onReschedule?: (item: ScheduleItem, toIso: string) => void
}) {
  const locale = "ru-RU"
  const today = new Date()
  const todayIso = toIsoDate(today)
  const rangeEndIso = toIsoDate(addDays(rangeStart, rangeDays - 1))

  // Drag a bar to another day. A tap without movement still opens the card.
  const [drag, setDrag] = useState<DragState | null>(null)
  const dragRef = useRef<{ id: string; startX: number; dayWidth: number; moved: boolean; shift: number } | null>(null)
  const dragId = drag?.id ?? null

  useEffect(() => {
    if (!dragId) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { dragRef.current = null; setDrag(null) }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [dragId])

  const beginDrag = (event: React.PointerEvent<HTMLDivElement>, item: ScheduleItem) => {
    if (event.button !== 0) return
    const lanes = event.currentTarget.closest("[data-gantt-lanes]") as HTMLElement | null
    if (!lanes) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const dayWidth = lanes.clientWidth / rangeDays
    dragRef.current = { id: item.id, startX: event.clientX, dayWidth, moved: false, shift: 0 }
    setDrag({ id: item.id, shift: 0, moved: false, dayWidth, x: event.clientX, y: event.clientY, item })
  }
  const moveDrag = (event: React.PointerEvent<HTMLDivElement>, item: ScheduleItem) => {
    const state = dragRef.current
    if (!state || state.id !== item.id) return
    const dx = event.clientX - state.startX
    if (!state.moved && Math.abs(dx) < 4) return // below 4 px it is still a click
    state.moved = true
    state.shift = clampShift(item.startDate.slice(0, 10), shiftFromPixels(dx, state.dayWidth), todayIso, rangeEndIso)
    setDrag({ id: item.id, shift: state.shift, moved: true, dayWidth: state.dayWidth, x: event.clientX, y: event.clientY, item })
  }
  const endDrag = (event: React.PointerEvent<HTMLDivElement>, item: ScheduleItem) => {
    const state = dragRef.current
    if (!state || state.id !== item.id) return
    dragRef.current = null
    setDrag(null)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (!state.moved) { onOpen?.(item); return }
    if (state.shift !== 0) onReschedule?.(item, shiftDate(item.startDate.slice(0, 10), state.shift))
  }
  const cancelDrag = () => { dragRef.current = null; setDrag(null) }
  const todayOffset = diffDays(rangeStart, today)
  const todayPct = (todayOffset / rangeDays) * 100

  // Заголовок с днями
  const headerDates: Date[] = []
  for (let i = 0; i <= rangeDays; i += 2) {
    headerDates.push(addDays(rangeStart, i))
  }

  // Группировка по оборудованию
  const groupedItems = items.reduce((acc, item) => {
    if (!acc[item.asset_id]) acc[item.asset_id] = []
    acc[item.asset_id].push(item)
    return acc
  }, {} as Record<string, ScheduleItem[]>)

  return (
    <div className="overflow-x-auto">
      {drag?.moved && (
        // Explicit colours: the light theme remaps bg-gray-900 to white, which made this label unreadable.
        <div className="pointer-events-none fixed z-[70] whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold shadow-xl"
          style={{ left: drag.x + 16, top: drag.y - 40, backgroundColor: "#111827", color: "#ffffff" }}>
          {drag.shift === 0
            ? "Сдвиньте на другой день"
            : `✋ ${formatDate(shiftDate(drag.item.startDate.slice(0, 10), drag.shift))} (${drag.shift > 0 ? "+" : "−"}${Math.abs(drag.shift)} дн.), отпустите для подтверждения`}
        </div>
      )}
      <div style={{ minWidth: "1100px" }}>
        
        {/* ═══ ШАПКА ТАБЛИЦЫ ═══ */}
        <div className="flex items-end border-b-2 border-gray-300 dark:border-gray-600 pb-3 mb-4">
          {/* Колонка оборудования */}
          <div className="w-[380px] flex-shrink-0">
            <div className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-1">
              {"Оборудование"}
            </div>
            <div className="text-[10px] text-gray-400">
              {"Модель и номер · вид ТО · пробег · участок"}
            </div>
          </div>
          
          {/* Шкала дат */}
          <div className="flex-1 relative h-12">
            {/* Фон для чётных/нечётных дней */}
            {headerDates.map((d, i) => {
              const leftPos = (diffDays(rangeStart, d) / rangeDays) * 100
              const nextPos = i < headerDates.length - 1 
                ? (diffDays(rangeStart, headerDates[i + 1]) / rangeDays) * 100 
                : 100
              return (
                <div 
                  key={i}
                  style={{ left: `${leftPos}%`, width: `${nextPos - leftPos}%` }}
                  className={`absolute top-0 bottom-0 ${i % 2 === 0 ? 'bg-gray-50 dark:bg-gray-800/30' : ''}`}
                />
              )
            })}
            
            {/* Даты */}
            {headerDates.map((d, i) => (
              <div 
                key={i}
                style={{ left: `${(diffDays(rangeStart, d) / rangeDays) * 100}%` }}
                className="absolute bottom-0 -translate-x-1/2 text-center"
              >
                <div className="text-[10px] text-gray-400 font-medium">
                  {new Intl.DateTimeFormat(locale, { weekday: "short" }).format(d)}
                </div>
                <div className="text-xs font-bold text-gray-700 dark:text-gray-300">
                  {d.getDate()}
                </div>
              </div>
            ))}
            
            {/* Линия «Сегодня» в шапке */}
            {todayPct >= 0 && todayPct <= 100 && (
              <div 
                style={{ left: `${todayPct}%` }}
                className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-20"
              >
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 px-1.5 py-0.5 bg-red-500 text-white text-[9px] font-bold rounded whitespace-nowrap">
                  {"Сегодня".toLocaleUpperCase(locale)}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ═══ СТРОКИ ГРАФИКА ═══ */}
        <div className="space-y-3">
          {Object.entries(groupedItems).map(([assetKey, unitItems]) => {
            const firstItem = unitItems[0]
            
            return (
              <div key={assetKey} className="group">
                {/* Карточка оборудования */}
                <div className="flex items-stretch rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden hover:shadow-lg transition-shadow">
                  
                  {/* ═══ ЛЕВАЯ ПАНЕЛЬ: Информация об оборудовании ═══ */}
                  <div className="w-[380px] flex-shrink-0 p-4 border-r border-gray-100 dark:border-gray-800 bg-gradient-to-r from-gray-50 to-white dark:from-gray-800/50 dark:to-gray-900">
                    <div className="flex items-start gap-4">
                      <div className="relative flex-shrink-0">
                        <EquipmentAvatar item={firstItem} size="xl" />
                        {unitItems.some((item) => item.status === "overdue") && (
                          <span title={"Есть просроченные работы"} className="absolute -right-1 -top-1 flex h-4 w-4">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
                            <span className="relative inline-flex h-4 w-4 rounded-full bg-red-500 ring-2 ring-white dark:ring-gray-900" />
                          </span>
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <h3 className="text-lg font-black leading-tight tracking-tight text-gray-900 dark:text-white">
                          {onOpen ? (
                            <button type="button" onClick={() => onOpen(firstItem)} title={"Открыть карточку"}
                              className="text-left hover:text-blue-600 hover:underline">
                              {equipmentTitle(firstItem)}
                            </button>
                          ) : equipmentTitle(firstItem)}
                        </h3>
                        <p className="text-xs text-gray-500">{equipmentSubtitle(firstItem)}</p>

                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {firstItem.depot && <SectionChip name={firstItem.depot} />}
                          <AssetStatusChip item={firstItem} />
                          <OnlineChip item={firstItem} />
                        </div>

                        {/* Виды ТО с понятными названиями во всплывающей подсказке */}
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {unitItems.map((item) => {
                            const cfg = typeCfg(item.type)
                            return <IntervalChip key={item.id} type={item.type} color={cfg.color} large />
                          })}
                        </div>

                        {toNum(firstItem.mileage) !== null && (
                          <div className="mt-2.5 flex flex-wrap items-center gap-2">
                            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-900/50" title={"Пробег по данным ТОИР"}>
                              <Gauge className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                              <span className="text-base font-bold text-emerald-700 dark:text-emerald-300">
                                {fmtNum(toNum(firstItem.mileage) as number)} км
                              </span>
                            </div>
                            {toNum(firstItem.remainingKm) !== null && (
                              <span title={`До ближайшего: ${intervalTitle(firstItem.type)}`} className={`text-sm font-bold px-2.5 py-1.5 rounded-lg ${
                                (toNum(firstItem.remainingKm) as number) <= 0
                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300'
                                  : (toNum(firstItem.remainingKm) as number) < 10
                                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300'
                                    : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                              }`}>
                                {(toNum(firstItem.remainingKm) as number) <= 0
                                  ? `⚠ −${fmtNum(Math.abs(toNum(firstItem.remainingKm) as number))} км`
                                  : `↓ ${fmtNum(toNum(firstItem.remainingKm) as number)} км до ${intervalCode(firstItem.type)}`}
                              </span>
                            )}
                          </div>
                        )}

                        <div className="mt-2 text-xs text-gray-500">
                          {`📅 ${formatDate(firstItem.startDate)}${firstItem.dateManual ? " ✋ вручную" : ""} · ⏱ ${firstItem.durationH} ч`}
                        </div>
                      </div>

                      {/* Кнопка создания наряда */}
                      {onCreateOrder && firstItem.entity_type !== "work_order" && (
                        <button
                          title="Открыть наряд-задание"
                          onClick={() => onCreateOrder(firstItem)}
                          className="opacity-0 group-hover:opacity-100 focus:opacity-100 transition-all flex-shrink-0 p-2 rounded-xl bg-blue-500 hover:bg-blue-600 text-white shadow-lg hover:shadow-xl hover:scale-105"
                        >
                          <Plus className="w-5 h-5"/>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* ═══ ПРАВАЯ ПАНЕЛЬ: График Ганта ═══ */}
                  <div className="flex-1 relative py-2 px-1">
                    {/* Фоновая сетка */}
                    {headerDates.map((d, i) => {
                      const leftPos = (diffDays(rangeStart, d) / rangeDays) * 100
                      return (
                        <div 
                          key={i}
                          style={{ left: `${leftPos}%` }}
                          className="absolute top-0 bottom-0 w-px bg-gray-100 dark:bg-gray-800"
                        />
                      )
                    })}
                    
                    {/* Линия «Сегодня» */}
                    {todayPct >= 0 && todayPct <= 100 && (
                      <div 
                        style={{ left: `${todayPct}%` }}
                        className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-10"
                      />
                    )}
                    
                    {/* Бары для каждого ТО */}
                    {/* Каждому виду ТО своя дорожка: бары с одной датой не должны перекрывать друг друга */}
                    <div data-gantt-lanes className="relative py-1" style={{ minHeight: `${unitItems.length * GANTT_LANE_PX + 8}px` }}>
                      {unitItems.map((item, idx) => {
                        const start = parseDate(item.startDate)
                        const days = durationDays(item.durationH)
                        const left = (diffDays(rangeStart, start) / rangeDays) * 100
                        const width = (days / rangeDays) * 100
                        const cfg = typeCfg(item.type)
                        const isOver = item.status === "overdue"
                        const isIP = item.status === "in_progress"
                        const isDone = item.status === "completed"
                        const movable = canReschedule && isReschedulable(item, true)
                        const activeDrag = drag !== null && drag.id === item.id && drag.moved ? drag : null
                        const dragging = activeDrag !== null
                        const shift = activeDrag ? activeDrag.shift : 0
                        const geometry = {
                          top: `${idx * GANTT_LANE_PX + 4}px`,
                          left: `${Math.max(0, left)}%`,
                          width: `${Math.max(Math.min(width, 100 - Math.max(0, left)), 8)}%`,
                        }

                        return (
                          <Fragment key={item.id}>
                            {/* Where the bar was: stays visible while it is being dragged */}
                            {dragging && (
                              <div aria-hidden="true" style={{ ...geometry, height: "40px" }}
                                className="absolute rounded-xl border-2 border-dashed border-gray-400/70 bg-gray-200/40 dark:bg-gray-700/30" />
                            )}
                            <div
                              style={{
                                ...geometry,
                                transform: activeDrag ? `translateX(${shift * activeDrag.dayWidth}px)` : undefined,
                                zIndex: dragging ? 40 : undefined,
                              }}
                              className="absolute"
                            >
                              <div
                                style={{ backgroundColor: cfg.color, touchAction: movable ? "none" : undefined }}
                                className={`
                                  h-10 rounded-xl flex items-center px-3 gap-2 select-none
                                  shadow-lg transition-all hover:z-20
                                  ${movable ? (dragging ? "cursor-grabbing shadow-2xl ring-2 ring-white/70" : "cursor-grab hover:shadow-xl hover:scale-105") : "cursor-pointer hover:shadow-xl hover:scale-105"}
                                  ${isDone ? 'opacity-50' : ''}
                                  ${isOver && !dragging ? 'ring-2 ring-red-400 ring-offset-2 animate-pulse' : ''}
                                  ${isIP ? 'ring-2 ring-white/50 ring-inset' : ''}
                                `}
                                role="button"
                                tabIndex={0}
                                onPointerDown={movable ? (event) => beginDrag(event, item) : undefined}
                                onPointerMove={movable ? (event) => moveDrag(event, item) : undefined}
                                onPointerUp={movable ? (event) => endDrag(event, item) : undefined}
                                onPointerCancel={movable ? cancelDrag : undefined}
                                onClick={movable ? undefined : () => onOpen?.(item)}
                                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen?.(item) } }}
                                title={`${equipmentTitle(item)} · ${equipmentSubtitle(item)}\n${intervalTitle(item.type)}\n${"Дата"}: ${formatDate(item.startDate)}${item.dateManual ? ` (перенесено вручную; рекомендовано: ${item.recommendedDate ? formatDate(item.recommendedDate) : "—"})` : ""}\n${item.mileage ? `${"Пробег"}: ${item.mileage} км\n` : ""}${movable ? "Нажмите: карточка. Потяните ✋: перенести дату" : "Нажмите, чтобы открыть карточку"}`}
                              >
                                {/* Иконка типа */}
                                {isOver && <AlertTriangle className="w-5 h-5 text-white flex-shrink-0" />}
                                {isIP && <Wrench className="w-5 h-5 text-white flex-shrink-0 animate-spin" style={{ animationDuration: '3s' }} />}
                                {item.dateManual && <span aria-label={"Перенесено вручную"} className="flex-shrink-0 text-base leading-none">✋</span>}

                                {/* Название ТО + Номер агрегата */}
                                <div className="flex flex-col min-w-0">
                                  <span className="text-sm font-black text-white drop-shadow truncate">
                                    {intervalCode(item.type)}
                                  </span>
                                  <span className="text-[10px] font-semibold text-white/80 truncate">
                                    {equipmentTitle(item)}
                                  </span>
                                </div>

                                {/* Дата если место есть */}
                                {width > 15 && (
                                  <span className="text-xs text-white/60 truncate hidden md:inline ml-auto">
                                    {item.startDate}
                                  </span>
                                )}
                              </div>
                            </div>
                          </Fragment>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* ═══ ЛЕГЕНДА ═══ */}
        <div className="mt-6 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
          <div className="flex flex-wrap items-center justify-between gap-4">
            {/* Виды работ — в кликабельной легенде над диаграммой */}
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <span aria-hidden="true">✋</span>
              {"Тяните полосу ТО, чтобы перенести дату (понадобится подтверждение)"}
            </div>

            {/* Статусы */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <div className="w-4 h-4 rounded bg-red-500 animate-pulse"/>
                <span className="text-xs text-gray-600 dark:text-gray-400">{"Просрочено"}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-1 h-4 bg-red-500 rounded"/>
                <span className="text-xs text-gray-600 dark:text-gray-400">{"Сегодня"}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Gauge className="w-4 h-4 text-emerald-500"/>
                <span className="text-xs text-gray-600 dark:text-gray-400">{"Данные графика"}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════
   QUICK ORDER MODAL  (без выхода со страницы)
═══════════════════════════════════════ */
function QuickOrderModal({ item, onClose, sections, employees, workTypes, onOrderCreated, onNotify }: {
  item: ScheduleItem
  onClose: () => void
  sections: Section[]
  employees: Employee[]
  workTypes: WorkType[]
  onOrderCreated?: () => void
  onNotify?: (n: { type: "warning" | "error" | "success" | "info"; title: string; message: string }, uniqueKey?: string, showToast?: boolean) => void
}) {

  const [section,   setSection]   = useState(item.section_id || "")
  const [executorId, setExecutorId] = useState("")
  const [workTypeId, setWorkTypeId] = useState(item.work_type_id || "")
  const [priority,  setPriority]  = useState<"critical" | "high" | "normal" | "low">("normal")
  const [note,      setNote]      = useState("")
  const [saved,     setSaved]     = useState(false)
  const [orderId,   setOrderId]   = useState("")
  const [error,     setError]     = useState("")
  const [saving, setSaving] = useState(false)
  const nextThresholdDisplay = item.nextThreshold === null
    ? null
    : Number(item.nextThreshold).toLocaleString()

  const handleSend = async () => {
    if (!section) { setError("Выберите участок для отправки наряда"); return }
    if (!executorId) { setError("Выберите исполнителя"); return }
    if (!workTypeId) { setError("Выберите вид работ для ТО"); return }
    setError("")
    setSaving(true)
    const mileageInfo = item.mileage !== null
      ? ` (пробег: ${Number(item.mileage).toLocaleString()} км, до ТО: ${item.remainingKm ?? "—"} км)`
      : ""
    try {
      const order = await api.workOrders.create({
        fixed_asset_id: item.asset_id,
        maintenance_plan_id: item.plan_id,
        maintenance_interval_id: item.interval_id,
        maintenance_trigger_mileage: item.nextThreshold,
        section_id: section,
        order_kind: "planned",
        priority: item.status === "overdue" ? "critical" : priority,
        executor_id: executorId,
        description: `${item.type} — плановое техническое обслуживание${mileageInfo}`,
        note: note.trim() || null,
        date_start: new Date(`${item.startDate}T00:00:00`).toISOString(),
        repairs: [{ work_type_id: workTypeId, items: [] }],
      })
      setOrderId(order.number)
      setSaved(true)
      onNotify?.({
        type: "success",
        title: `${"Наряд"} ${order.number} ${"создан"}`,
        message: `${item.type} ${"для"} ${item.unit} ${"отправлен на участок"} ${sections.find((row) => row.id === section)?.name ?? ""}`,
      }, undefined, true)
      onOrderCreated?.()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ошибка при создании наряда")
    } finally {
      setSaving(false)
    }
  }

  const selCls = "w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 pr-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">

        {/* Заголовок */}
        <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-blue-600 to-blue-700 text-white">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center">
              <Plus className="w-5 h-5"/>
            </div>
            <div>
              <p className="text-xs text-blue-200 font-medium">{"Открыть наряд-задание по графику"}</p>
              <p className="text-base font-bold">{item.unit} · {item.type}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/20 transition-colors">
            <X className="w-5 h-5"/>
          </button>
        </div>

        {saved ? (
          /* ── Успех ── */
          <div className="p-8 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-950 flex items-center justify-center mx-auto">
              <CheckCircle className="w-8 h-8 text-green-500"/>
            </div>
            <div>
              <p className="text-lg font-bold text-gray-900 dark:text-white">{"Наряд открыт!"}</p>
              <p className="text-sm text-gray-500 mt-1">
                {"Номер"}: <span className="font-mono font-bold text-blue-600">{orderId}</span>
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {"Участок"}: <span className="font-semibold text-gray-700 dark:text-gray-300">{section}</span>
              </p>
              {false && (
                <div className="mt-3 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800">
                  <p className="text-xs text-emerald-700 dark:text-emerald-300">
                    <Gauge className="w-3 h-3 inline mr-1" />
                    Это ТО теперь не будет показываться в графике до завершения наряда.
                  </p>
                  {nextThresholdDisplay !== null && (
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                      Следующее {item.type} запланируется при пробеге {nextThresholdDisplay} км
                    </p>
                  )}
                </div>
              )}
              <p className="text-xs text-gray-400 mt-2">
                {"Наряд появится в разделе «Запланировано» для выбранного участка."}
              </p>
            </div>
            <button onClick={onClose}
              className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors">
              {"Готово"}
            </button>
          </div>
        ) : (
          <>
            {/* Тело */}
            <div className="p-6 space-y-5">

              {/* Данные из графика (read-only) */}
              <div className={`rounded-xl border p-4 ${
                false 
                  ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800" 
                  : "bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
              }`}>
                <div className="flex items-center gap-2 mb-3">
                  <p className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">
                    {"Данные из графика ТО"}
                  </p>
                  {false && (
                    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-400">
                      <Gauge className="w-2.5 h-2.5" />
                      —
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <div>
                    <span className="text-gray-400 text-xs block">{"Единица ТПС"}</span>
                    <p className="font-semibold text-gray-900 dark:text-white">{item.unit}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-xs block">{"Вид ремонта"}</span>
                    <p className="font-bold text-blue-600 dark:text-blue-400">{item.type}</p>
                  </div>
                  {item.mileage !== null && (
                    <>
                      <div>
                        <span className="text-gray-400 text-xs block">{"Текущий пробег"}</span>
                        <p className="font-bold text-emerald-600 dark:text-emerald-400">{Number(item.mileage).toLocaleString()} км</p>
                      </div>
                      <div>
                        <span className="text-gray-400 text-xs block">{"До ТО осталось"}</span>
                        <p className={`font-bold ${
                          Number(item.remainingKm || 0) <= 0 
                            ? "text-red-600 dark:text-red-400" 
                            : "text-amber-600 dark:text-amber-400"
                        }`}>
                          {Number(item.remainingKm || 0) <= 0 
                            ? `${"Просрочено на"} ${Math.abs(Number(item.remainingKm || 0))} км`
                            : `${item.remainingKm} км`
                          }
                        </p>
                      </div>
                    </>
                  )}
                  <div>
                    <span className="text-gray-400 text-xs block">{"Дата начала"}</span>
                    <p className="font-medium text-gray-700 dark:text-gray-300">{dateToDdMmYyyy(item.startDate)}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-xs block">{"Длительность"}</span>
                    <p className="font-medium text-gray-700 dark:text-gray-300">{item.durationH} ч</p>
                  </div>
                </div>
                {item.status === "overdue" && (
                  <div className="mt-3 flex items-center gap-2 p-2 rounded-lg bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300">
                    <AlertTriangle className="w-4 h-4" />
                    <span className="text-xs font-semibold">{"Требуется срочный ремонт! Пробег превысил норматив."}</span>
                  </div>
                )}
              </div>

              {/* Выбор участка — обязательно */}
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                  {"Участок"} <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <select
                    value={section}
                    onChange={e => { setSection(e.target.value); setError("") }}
                    className={`${selCls} ${error ? "border-red-400 focus:ring-red-400" : ""}`}>
                    <option value="">{"Выберите участок..."}</option>
                    {sections.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
                </div>
                {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                  {"Вид работ"} <span className="text-red-500">*</span>
                </label>
                <select value={workTypeId} onChange={e => { setWorkTypeId(e.target.value); setError("") }} className={selCls}>
                  <option value="">{"Выберите вид работ..."}</option>
                  {workTypes.map(workType => (
                    <option key={workType.id} value={workType.id}>{workType.code} — {workType.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                  {"Исполнитель"} <span className="text-red-500">*</span>
                </label>
                <select value={executorId} onChange={e => { setExecutorId(e.target.value); setError("") }} className={selCls}>
                  <option value="">{"Выберите сотрудника..."}</option>
                  {employees.filter(employee => employee.is_active && (!section || employee.section_id === section)).map(employee => (
                    <option key={employee.id} value={employee.id}>{employee.full_name}</option>
                  ))}
                </select>
              </div>

              {/* Приоритет */}
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">{"Приоритет"}</label>
                <div className="grid grid-cols-4 gap-2">
                  {([
                    ["low",      "Низкий",     "text-gray-600 bg-gray-100 dark:bg-gray-800"],
                      ["normal",   "Обычный",    "text-blue-700 bg-blue-100 dark:bg-blue-950"],
                      ["high",     "Высокий",    "text-amber-700 bg-amber-100 dark:bg-amber-950"],
                      ["critical", "Критич.",    "text-red-700 bg-red-100 dark:bg-red-950"],
                  ] as [typeof priority,string,string][]).map(([v,l,cls]) => (
                    <button key={v} onClick={() => setPriority(v)}
                      className={`py-1.5 rounded-lg text-xs font-semibold transition-all border-2 ${
                        priority === v
                          ? cls + " border-current"
                          : "border-gray-200 dark:border-gray-700 text-gray-400 hover:border-gray-300"
                      }`}>{l}</button>
                  ))}
                </div>
              </div>

              {/* Примечание */}
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                  {"Примечание"} <span className="text-gray-400 font-normal">({"необязательно"})</span>
                </label>
                <textarea value={note} onChange={e => setNote(e.target.value)} rows={2}
                  placeholder={"Особые указания для участка..."}
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </div>
            </div>

            {/* Подвал */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-400">
                {"Статус"}: <span className="font-semibold text-gray-600 dark:text-gray-300">{"Запланировано"}</span>
              </p>
              <div className="flex gap-3">
                <button onClick={onClose}
                  className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                  {"Отмена"}
                </button>
                <button onClick={() => void handleSend()} disabled={saving}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors shadow-sm disabled:opacity-50">
                  <Plus className="w-4 h-4"/> {saving ? "Создание..." : "Открыть на участок"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════
   СТРАНИЦА
═══════════════════════════════════════ */
const dateToDdMmYyyy = formatDate

/* ═══════════════════════════════════════
   КАРТОЧКА ТО (боковая панель)
═══════════════════════════════════════ */
function DetailDrawer({ entry, siblings, onSelect, plan, canUpdate, updating, error, onClose, onCreateOrder, onChangeStatus, canReschedule, suspended, onRequestMove, onResetDate, isAdmin, todayIso: todayIsoProp, decisions, decisionsError, onBlock, onUnblock, onWaive, onBaseline }: {
  entry: Enriched
  siblings: Enriched[]
  onSelect: (id: string) => void
  plan: MaintenancePlan | undefined
  canUpdate: boolean
  updating: boolean
  error: string | null
  onClose: () => void
  onCreateOrder: (item: ScheduleItem) => void
  onChangeStatus: (item: ScheduleItem, status: MaintenancePlan["status"], completedDate?: string) => Promise<void>
  canReschedule: boolean
  suspended: boolean // a confirmation dialog is open on top: Escape must close only that dialog
  onRequestMove: (item: ScheduleItem, toIso: string) => void
  onResetDate: (item: ScheduleItem) => void
  isAdmin: boolean
  todayIso: string
  decisions: MaintenanceDecision[] | null
  decisionsError: boolean
  onBlock: (item: ScheduleItem) => void
  onUnblock: (item: ScheduleItem) => void
  onWaive: (item: ScheduleItem) => void
  onBaseline: (item: ScheduleItem) => void
}) {
  const item = entry.item
  const st = statusConfig[item.status]
  const cfg = typeCfg(item.type)
  const urgency = item.urgency ? URGENCY_LABEL[item.urgency] : null
  const planStatus = plan?.status ?? item.planStatus ?? (item.status === "upcoming" || item.status === "overdue" ? "scheduled" : item.status)
  const transitions = item.entity_type === "maintenance_plan" && item.plan_id ? PLAN_TRANSITIONS[planStatus] ?? [] : []
  const todayIso = todayIsoProp
  const [completedDate, setCompletedDate] = useState(todayIso)
  const [moveDate, setMoveDate] = useState(item.startDate.slice(0, 10))
  useEffect(() => { setMoveDate(item.startDate.slice(0, 10)) }, [item.id, item.startDate])
  const [history, setHistory] = useState<MileageHistory[] | null>(null)
  const [historyError, setHistoryError] = useState(false)

  const asideRef = useRef<HTMLElement>(null)

  // Give focus back to whatever opened the card when it closes.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    return () => opener?.focus?.()
  }, [])

  // Escape closes; Tab stays inside the card (it is a modal dialog).
  useEffect(() => {
    if (suspended) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { onClose(); return }
      if (event.key !== "Tab" || !asideRef.current) return
      const focusable = asideRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose, suspended])

  useEffect(() => {
    let active = true
    setHistory(null)
    setHistoryError(false)
    api.fixedAssets.mileageHistory(item.asset_id, { days: 30, limit: 10 })
      .then((response) => { if (active) setHistory(response.items) })
      .catch(() => { if (active) setHistoryError(true) })
    return () => { active = false }
  }, [item.asset_id])

  const progress = entry.progress
  const barCls = progress === null ? "bg-gray-300" : progress >= 100 ? "bg-red-500" : progress >= NEAR_THRESHOLD_PCT ? "bg-amber-500" : progress >= 70 ? "bg-blue-500" : "bg-emerald-500"
  const metric = (label: string, value: React.ReactNode) => (
    <div className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2.5 dark:border-gray-800 dark:bg-gray-800/40">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{label}</p>
      <div className="mt-0.5 text-sm font-semibold text-gray-900 dark:text-white">{value}</div>
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="maintenance-drawer-title">
      <button type="button" aria-label={"Закрыть"} onClick={onClose} className="absolute inset-0 cursor-default bg-black/40" />
      <aside ref={asideRef} className="relative flex h-full w-full max-w-lg flex-col overflow-y-auto bg-white shadow-2xl dark:bg-gray-900">
        <div className="flex items-start justify-between gap-3 border-b border-gray-200 px-6 py-5 dark:border-gray-800">
          <div className="flex min-w-0 items-start gap-3">
           <EquipmentAvatar item={item} size="lg" />
           <div className="min-w-0">
            <h2 id="maintenance-drawer-title" className="text-lg font-bold text-gray-900 dark:text-white">{equipmentTitle(item)}</h2>
            <p className="text-xs text-gray-500">{equipmentSubtitle(item)}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <IntervalChip type={item.type} color={cfg.color} large />
              <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${st.cls}`}>
                <st.icon className="h-3 w-3" />{st.label}
              </span>
              {urgency && <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${urgency.cls}`}>{`Срочность: ${urgency.label}`}</span>}
            </div>
           </div>
          </div>
          <button type="button" autoFocus onClick={onClose} aria-label={"Закрыть"}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className={`rounded-xl border px-4 py-3 text-sm leading-snug ${REC_CLS[entry.rec.level]}`}>
            <p className="mb-1 text-[10px] font-bold uppercase tracking-wider opacity-70">{"Рекомендация"}</p>
            {entry.rec.text}
          </div>

          <LivePlanCard item={item} todayIso={todayIso} canUpdate={canUpdate} isAdmin={isAdmin} busy={updating}
            decisions={decisions} decisionsError={decisionsError}
            onBlock={() => onBlock(item)} onUnblock={() => onUnblock(item)} onWaive={() => onWaive(item)} onBaseline={() => onBaseline(item)} />

          <div className="grid grid-cols-2 gap-3">
            {metric("Пробег", entry.mileage !== null ? `${fmtNum(entry.mileage)} км` : "—")}
            {metric("Порог ТО", entry.threshold !== null ? `${fmtNum(entry.threshold)} км` : "—")}
            {metric("Осталось до ТО", entry.remaining !== null
              ? `${entry.remaining <= 0 ? "−" : ""}${fmtNum(Math.abs(entry.remaining))} км${entry.daysLeft !== null ? ` (≈ ${entry.daysLeft} дн.)` : ""}`
              : "—")}
            {metric("Плановая дата", dateToDdMmYyyy(item.startDate))}
            {metric("Участок", item.depot || "—")}
            {metric("Исполнитель", item.tech || "—")}
            {metric("Модель", item.asset_model || "—")}
            {metric("Состояние техники", <AssetStatusChip item={item} />)}
            {metric("Вид ТО", intervalTitle(item.type))}
          </div>

          {progress !== null && (
            <div>
              <div className="mb-1 flex justify-between text-xs text-gray-500">
                <span>{"Выработка порога"}</span><span className="font-semibold">{Math.round(progress)}%</span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                <div className={`h-full rounded-full ${barCls}`} style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
              </div>
            </div>
          )}

          {item.note && (
            <div className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2.5 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-800/40 dark:text-gray-300">
              <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">{"Примечание"}</p>
              {item.note}
            </div>
          )}

          {siblings.length > 1 && (
            <div>
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-500">{`Все интервалы агрегата (${siblings.length})`}</h3>
              <ul className="space-y-1.5">
                {siblings.map((sibling) => {
                  const siblingCfg = typeCfg(sibling.item.type)
                  const current = sibling.item.id === item.id
                  return (
                    <li key={sibling.item.id}>
                      <button type="button" onClick={() => onSelect(sibling.item.id)} aria-current={current ? "true" : undefined}
                        className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left text-xs ${
                          current
                            ? "border-blue-400 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/30"
                            : "border-gray-200 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50"
                        }`}>
                        <span aria-hidden="true" className={`h-2 w-2 flex-shrink-0 rounded-full ${LEVEL_DOT[sibling.rec.level]}`} />
                        <span title={intervalTitle(sibling.item.type)} className={`font-bold ${siblingCfg.text}`}>{intervalCode(sibling.item.type)}</span>
                        <span className="ml-auto text-gray-500">
                          {sibling.remaining !== null ? `${sibling.remaining <= 0 ? "−" : ""}${fmtNum(Math.abs(sibling.remaining))} км` : "—"}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          <div>
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-500">{"История пробега (30 дней)"}</h3>
            {history === null && !historyError && <p className="text-xs text-gray-400">{"Загрузка…"}</p>}
            {historyError && <p className="text-xs text-amber-600 dark:text-amber-400">{"История пробега недоступна"}</p>}
            {history !== null && history.length === 0 && <p className="text-xs text-gray-400">{"Записей за 30 дней нет"}</p>}
            {history !== null && history.length > 0 && (
              <table className="w-full text-xs">
                <thead><tr className="text-left text-gray-400"><th className="py-1 font-medium">{"Дата"}</th><th className="py-1 font-medium">{"Пробег, км"}</th><th className="py-1 font-medium">{"Источник"}</th></tr></thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {history.map((row) => (
                    <tr key={row.id} className="text-gray-700 dark:text-gray-300">
                      <td className="py-1.5">{new Date(row.recorded_at).toLocaleString("ru-RU")}</td>
                      <td className="py-1.5 font-semibold">{fmtNum(Number(row.mileage))}</td>
                      <td className="py-1.5">{MILEAGE_SOURCE_LABEL[row.source] ?? row.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {item.entity_type === "forecast" && (
            <p className="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2.5 text-xs text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300">
              {"Это прогноз по пробегу. План ТО создаётся системой автоматически; чтобы закрепить работу, создайте наряд."}
            </p>
          )}

          {canReschedule && isReschedulable(item, canUpdate) && (
            <div className="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-800">
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">{"Перенос срока"}</h3>
              {item.dateManual && (
                <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                  {`✋ Дата перенесена вручную. Рекомендация системы: ${item.recommendedDate ? dateToDdMmYyyy(item.recommendedDate) : "—"}.${item.rescheduleReason ? ` Причина: ${item.rescheduleReason}` : ""}`}
                </p>
              )}
              <div className="flex items-end gap-2">
                <label className="flex-1 text-xs text-gray-500">
                  {"Новая дата"}
                  <input type="date" min={todayIso} max={shiftDate(todayIso, MAX_RESCHEDULE_DAYS)} value={moveDate}
                    onChange={(event) => setMoveDate(event.target.value)}
                    className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white" />
                </label>
                <button type="button"
                  disabled={!moveDate || moveDate === item.startDate.slice(0, 10) || validateRescheduleDate(moveDate, todayIso) !== null}
                  onClick={() => onRequestMove(item, moveDate)}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50">
                  {"Перенести…"}
                </button>
              </div>
              {item.dateManual && item.entity_type === "maintenance_plan" && (
                <button type="button" onClick={() => onResetDate(item)}
                  className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400">{"Вернуть рекомендованную дату"}</button>
              )}
              <p className="text-[11px] text-gray-400">{"Перед изменением будет показано подтверждение. Срок можно сдвинуть и на полосе в диаграмме Ганта."}</p>
            </div>
          )}

          {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}

          {canUpdate && transitions.length > 0 && (
            <div className="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-800">
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">{`Статус плана: ${PLAN_STATUS_LABEL[planStatus] ?? planStatus}`}</h3>
              {transitions.some((transition) => transition.to === "completed") && (
                <label className="block text-xs text-gray-500">
                  {"Дата завершения"}
                  <input type="date" max={todayIso} value={completedDate} onChange={(event) => setCompletedDate(event.target.value || todayIso)}
                    className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white" />
                </label>
              )}
              <div className="flex flex-wrap gap-2">
                {transitions.map((transition) => (
                  <button key={transition.to} type="button" disabled={updating}
                    onClick={() => {
                      if (transition.to === "cancelled" && !window.confirm("Отменить план ТО? Это действие нельзя отменить.")) return
                      void onChangeStatus(item, transition.to, transition.to === "completed" ? completedDate : undefined)
                    }}
                    className={`rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50 ${
                      transition.danger
                        ? "border border-red-200 text-red-600 hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40"
                        : "bg-blue-600 text-white hover:bg-blue-700"
                    }`}>
                    {updating ? "Сохранение…" : transition.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {item.entity_type === "maintenance_plan" && transitions.length === 0 && planStatus !== "blocked" && (
            <p className="text-xs text-gray-400">{`Статус «${PLAN_STATUS_LABEL[planStatus] ?? planStatus}» изменить нельзя.`}</p>
          )}

          <div className="flex flex-wrap gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
            {item.entity_type !== "work_order" && (
              <button type="button" onClick={() => onCreateOrder(item)}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700">
                <Plus className="h-4 w-4" />{"Создать наряд"}
              </button>
            )}
            <a href={assetHref(item)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
              {"Открыть в основных средствах"}
            </a>
            <a href="/dashboard/directories/maintenance-intervals" className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
              {"Интервалы ТО"}
            </a>
            {item.work_order_id && (
              <a href="/dashboard/work-orders" className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
                {"Наряды"}
              </a>
            )}
          </div>
        </div>
      </aside>
    </div>
  )
}

export default function MaintenancePage() {
  const { hasPermission, user } = useAuth()
  const locale = "ru-RU"
  const [schedule,  setSchedule]  = useState<ScheduleItem[]>([])
  const [plans, setPlans] = useState<MaintenancePlan[]>([])
  const [loading,   setLoading]   = useState(true)
  const [view, setView]           = useState<"gantt"|"table">("table")
  const [filter, setFilter]       = useState<Status|"all">("all")
  const [monthOffset, setMonthOffset] = useState(0)
  const [quickItem, setQuickItem] = useState<ScheduleItem|null>(null)
  const [notifications, setNotifications] = useState<ToastNotification[]>([])
  const [allNotifications, setAllNotifications] = useState<ToastNotification[]>([])
  const [sections, setSections] = useState<Section[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [workTypes, setWorkTypes] = useState<WorkType[]>([])
  const [dailyAverageKm, setDailyAverageKm] = useState("")
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [scheduleError, setScheduleError] = useState<string | null>(null)
  const [plansError, setPlansError] = useState<string | null>(null)
  const [planUpdateError, setPlanUpdateError] = useState<string | null>(null)
  const [updatingPlanId, setUpdatingPlanId] = useState<string | null>(null)
  const shownNotificationsRef = useRef<Set<string>>(new Set())
  const scheduleRequestIdRef = useRef(0)
  const plansRequestIdRef = useRef(0)
  
  // Дополнительные фильтры
  const [filterType, setFilterType] = useState<string>("all") // Тип ТО
  const [filterUnit, setFilterUnit] = useState<string>("") // Поиск по названию
  const [filterUrgency, setFilterUrgency] = useState<"all" | "high" | "medium" | "low">("all")
  const [filterAssetId, setFilterAssetId] = useState("")
  const [showFilters, setShowFilters] = useState(false)
  // Сортировка: крупные пробеги сверху по умолчанию
  const [sortKey, setSortKey] = useState<SortKey>("mileage")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [filterDepot, setFilterDepot] = useState("")
  const [filterMinMileage, setFilterMinMileage] = useState("")
  const [filterMaxMileage, setFilterMaxMileage] = useState("")
  const [onlyNear, setOnlyNear] = useState(false)
  const [onlyWithMileage, setOnlyWithMileage] = useState(false)
  const [tablePage, setTablePage] = useState(0)
  const [tablePageSize, setTablePageSize] = useState(50)
  const [onlyCritical, setOnlyCritical] = useState(false)
  const [filterAssetType, setFilterAssetType] = useState("")
  const [pendingMove, setPendingMove] = useState<{ item: ScheduleItem; toIso: string } | null>(null)
  const [moveBusy, setMoveBusy] = useState(false)
  const [moveError, setMoveError] = useState<string | null>(null)
  const [drawerId, setDrawerId] = useState<string | null>(null)
  // Living plan: KPIs, disruptions, the decision log of the open card and the dialogs on top of it.
  const [kpis, setKpis] = useState<MaintenanceKpis | null>(null)
  const [disruptions, setDisruptions] = useState<MaintenanceDisruption[]>([])
  const [serverPace, setServerPace] = useState<number | null>(null)
  const [decisions, setDecisions] = useState<MaintenanceDecision[] | null>(null)
  const [decisionsError, setDecisionsError] = useState(false)
  type LiveDialog =
    | { kind: "block" | "waive" | "baseline"; item: ScheduleItem }
    | { kind: "disruption" }
  const [liveDialog, setLiveDialog] = useState<LiveDialog | null>(null)
  const [liveBusy, setLiveBusy] = useState(false)
  const [liveError, setLiveError] = useState<string | null>(null)
  const [closingDisruptionId, setClosingDisruptionId] = useState<string | null>(null)
  // The full-page spinner is only for the very first load; later refreshes keep the page (and an open card) in place.
  const hasLoadedRef = useRef(false)
  const [grouped, setGrouped] = useState(true) // one row per unit; the rest of its intervals expand below it
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [hideTest, setHideTest] = useState(false)
  const [ganttPage, setGanttPage] = useState(0)
  const [prefsLoaded, setPrefsLoaded] = useState(false)

  // View preferences survive reloads (storage may be blocked: then defaults are simply used).
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(PREFS_KEY)
      if (raw) {
        const prefs = JSON.parse(raw) as Record<string, unknown>
        if (prefs.view === "gantt" || prefs.view === "table") setView(prefs.view)
        if (typeof prefs.sortKey === "string" && prefs.sortKey in SORT_LABELS) setSortKey(prefs.sortKey as SortKey)
        if (prefs.sortDir === "asc" || prefs.sortDir === "desc") setSortDir(prefs.sortDir)
        if (typeof prefs.grouped === "boolean") setGrouped(prefs.grouped)
        if (typeof prefs.hideTest === "boolean") setHideTest(prefs.hideTest)
        if (typeof prefs.tablePageSize === "number" && TABLE_PAGE_SIZES.includes(prefs.tablePageSize)) {
          setTablePageSize(prefs.tablePageSize)
        }
      }
    } catch { /* corrupt or unavailable storage: keep defaults */ }
    setPrefsLoaded(true)
  }, [])
  useEffect(() => {
    if (!prefsLoaded) return
    try {
      window.localStorage.setItem(PREFS_KEY, JSON.stringify({ view, sortKey, sortDir, grouped, hideTest, tablePageSize }))
    } catch { /* ignore */ }
  }, [prefsLoaded, view, sortKey, sortDir, grouped, hideTest, tablePageSize])
  const canUpdatePlans = user?.role === "admin" || user?.role === "operator"

  // showToast = true — показать всплывающее уведомление, false — только в колокольчик
  const addNotification = useCallback((n: Omit<ToastNotification, "id" | "timestamp" | "read">, uniqueKey?: string, showToast: boolean = false) => {
    // Предотвращаем дублирование уведомлений (используем ref чтобы не вызывать перерендер)
    if (uniqueKey && shownNotificationsRef.current.has(uniqueKey)) return
    
    const id = `${Date.now()}-${Math.random()}`
    const newNotif: ToastNotification = { 
      ...n, 
      id, 
      timestamp: new Date(),
      read: false 
    }
    
    // Добавляем в список всех уведомлений (для колокольчика)
    setAllNotifications(prev => [newNotif, ...prev].slice(0, 100)) // Храним максимум 100
    
    // Добавляем во всплывающие уведомления ТОЛЬКО если showToast = true
    if (showToast) {
      setNotifications(prev => [...prev, newNotif])
      
      // Убираем всплывающее уведомление через 8 секунд
      setTimeout(() => {
        setNotifications(prev => prev.filter(t => t.id !== id))
      }, 8000)
    }
    
    if (uniqueKey) {
      shownNotificationsRef.current.add(uniqueKey)
    }
  }, [])

  const dismissNotification = useCallback((id: string) => {
    setNotifications(prev => prev.filter(t => t.id !== id))
  }, [])

  const markNotificationAsRead = useCallback((id: string) => {
    setAllNotifications(prev => 
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    )
  }, [])

  const markAllNotificationsAsRead = useCallback(() => {
    setAllNotifications(prev => prev.map(n => ({ ...n, read: true })))
  }, [])

  const clearAllNotifications = useCallback(() => {
    setAllNotifications([])
  }, [])


  // Загрузка графика с сервера (даты считаются на сервере)
  const fetchSchedule = useCallback(async (monthOffsetParam?: number) => {
    const requestId = ++scheduleRequestIdRef.current
    setLoading(true)
    try {
      const offset = monthOffsetParam ?? monthOffset
      const now = new Date()
      const totalMonth = now.getMonth() + offset
      const y = now.getFullYear() + Math.floor(totalMonth / 12)
      const m = ((totalMonth % 12) + 12) % 12 + 1
      const queryMonth = `${y}-${String(m).padStart(2, "0")}`

      const response = await api.maintenanceSchedule.get({ month: queryMonth })
      if (requestId !== scheduleRequestIdRef.current) return
      setSchedule(response.schedule)
      setServerPace(toNum(response.daily_average_km))
      setScheduleError(null)
    } catch (e) {
      if (requestId !== scheduleRequestIdRef.current) return
      setSchedule([])
      setScheduleError(e instanceof Error ? e.message : "Не удалось загрузить график ТО")
    } finally {
      if (requestId === scheduleRequestIdRef.current) {
        hasLoadedRef.current = true
        setLoading(false)
      }
    }
  }, [monthOffset])

  useEffect(() => { fetchSchedule(monthOffset) }, [fetchSchedule, monthOffset])

  const fetchPlans = useCallback(async () => {
    const requestId = ++plansRequestIdRef.current
    const now = new Date()
    const totalMonth = now.getMonth() + monthOffset
    const year = now.getFullYear() + Math.floor(totalMonth / 12)
    const month = `${year}-${String(((totalMonth % 12) + 12) % 12 + 1).padStart(2, "0")}`
    const params: Parameters<typeof api.maintenancePlans.list>[0] = {
      limit: 1000,
      offset: 0,
    }
    if (filterAssetId) params.asset_id = filterAssetId
    if (filter !== "overdue") params.month = month
    if (filter === "in_progress" || filter === "completed" || filter === "blocked") {
      params.status = filter
    } else if (filter === "upcoming" || filter === "overdue") {
      params.status = "scheduled"
    }
    if (filterUrgency !== "all") params.urgency = filterUrgency

    setPlansError(null)
    try {
      const response = await api.maintenancePlans.list(params)
      if (requestId === plansRequestIdRef.current) setPlans(response.items)
    } catch (cause) {
      if (requestId !== plansRequestIdRef.current) return
      setPlans([])
      setPlansError(
        cause instanceof Error ? cause.message : "Не удалось загрузить планы ТО"
      )
    }
  }, [filter, filterAssetId, filterUrgency, monthOffset])

  useEffect(() => { void fetchPlans() }, [fetchPlans])

  // KPIs and open disruptions: a failure here must never break the page (they are an overview, not the data).
  const fetchLive = useCallback(async () => {
    try {
      const [kpiResponse, disruptionResponse] = await Promise.all([
        api.maintenanceLive.kpis(),
        api.maintenanceLive.disruptions({ only_open: true }),
      ])
      setKpis(kpiResponse)
      setDisruptions(disruptionResponse)
    } catch {
      setKpis(null)
      setDisruptions([])
    }
  }, [])
  useEffect(() => { void fetchLive() }, [fetchLive])

  useEffect(() => {
    let active = true
    async function loadReferencesAndSettings() {
      setSettingsLoading(true)
      try {
        const [sectionsResponse, employeesResponse, workTypesResponse, settingsResponse] =
          await Promise.all([
            api.sections.list({ limit: 1000, offset: 0 }),
            api.employees.list({ limit: 1000, offset: 0 }),
            api.workTypes.list({ limit: 1000, offset: 0 }),
            api.maintenanceSettings.get(),
          ])
        if (!active) return
        setSections(sectionsResponse.items)
        setEmployees(employeesResponse.items)
        setWorkTypes(workTypesResponse.items)
        setDailyAverageKm(
          settingsResponse.daily_average_km === null
            ? ""
            : String(settingsResponse.daily_average_km)
        )
        setSettingsError(null)
      } catch (cause) {
        if (active) {
          setSettingsError(
            cause instanceof Error
              ? cause.message
              : "Не удалось загрузить настройки ТО"
          )
        }
      } finally {
        if (active) setSettingsLoading(false)
      }
    }
    void loadReferencesAndSettings()
    return () => {
      active = false
    }
  }, [])

  const canConfigureMaintenance =
    hasPermission("maintenance_settings.update") || hasPermission("maintenance.update")

  const updatePlanStatus = async (
    item: ScheduleItem,
    status: MaintenancePlan["status"],
    completedDate?: string
  ) => {
    if (!canUpdatePlans || !item.plan_id) return
    setUpdatingPlanId(item.plan_id)
    setPlanUpdateError(null)
    try {
      await api.maintenancePlans.update(
        item.plan_id,
        completedDate ? { status, completed_date: completedDate } : { status },
      )
      await Promise.all([fetchSchedule(monthOffset), fetchPlans()])
    } catch (cause) {
      setPlanUpdateError(
        cause instanceof Error ? cause.message : "Не удалось обновить статус плана ТО"
      )
    } finally {
      setUpdatingPlanId(null)
    }
  }

  const saveDailyAverageKm = async () => {
    const value = Number(dailyAverageKm)
    if (!Number.isFinite(value) || value <= 0) {
      setSettingsError("Введите положительный средний пробег в км за день")
      return
    }
    setSettingsSaving(true)
    setSettingsError(null)
    try {
      const result = await api.maintenanceSettings.update({ daily_average_km: value })
      setDailyAverageKm(String(result.daily_average_km))
      await fetchSchedule(monthOffset)
    } catch (cause) {
      setSettingsError(
        cause instanceof Error ? cause.message : "Не удалось сохранить настройку"
      )
    } finally {
      setSettingsSaving(false)
    }
  }

  // Диапазон: текущий месяц
  const now         = new Date()
  const rangeStart  = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1)
  const rangeEnd    = new Date(now.getFullYear(), now.getMonth() + monthOffset + 1, 0)
  const rangeDays   = diffDays(rangeStart, rangeEnd) + 1

  const monthLabel  = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(rangeStart)

  // График приходит с сервера с уже рассчитанными датами
  const allSchedule = schedule

  const handleCreateOrder = (item: ScheduleItem) => setQuickItem(item)

  // Уникальные типы ТО для фильтра
  const uniqueTypes = [...new Set(allSchedule.map(s => intervalCode(s.type)))].sort()
  const assetOptions = [
    ...new Map(allSchedule.map((item) => [item.asset_id, item.unit] as const)).entries(),
  ]
  
  // The configured figure wins; otherwise the server's default. Each row also carries its own pace (paceKmPerDay).
  const dailyKm = toNum(dailyAverageKm) !== null && Number(dailyAverageKm) > 0
    ? Number(dailyAverageKm)
    : serverPace !== null && serverPace > 0 ? serverPace : null
  const depotOptions = [...new Set(allSchedule.map((item) => item.depot).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "ru"),
  )
  const minMileage = toNum(filterMinMileage)
  const maxMileage = toNum(filterMaxMileage)

  // Фильтрация — показываем элементы, пересекающиеся с диапазоном
  const allEnriched = allSchedule.map((item) => enrich(item, dailyKm))
  const filteredEnriched = allEnriched.filter((entry) => {
    const item = entry.item
    if (!isInRange(item, rangeStart, rangeEnd, durationDays(item.durationH))) return false
    if (filter !== "all" && item.status !== filter) return false
    if (filterUrgency !== "all" && item.urgency !== filterUrgency) return false
    if (filterAssetId && item.asset_id !== filterAssetId) return false
    if (filterType !== "all" && intervalCode(item.type) !== filterType) return false
    if (filterAssetType && item.asset_type !== filterAssetType) return false
    if (filterUnit) {
      const haystack = [item.unit, item.asset_model, item.asset_serial, item.depot].filter(Boolean).join(" ").toLowerCase()
      if (!haystack.includes(filterUnit.toLowerCase())) return false
    }
    if (filterDepot === NO_DEPOT) { if (item.depot) return false }
    else if (filterDepot && item.depot !== filterDepot) return false
    if (minMileage !== null && (entry.mileage === null || entry.mileage < minMileage)) return false
    if (maxMileage !== null && (entry.mileage === null || entry.mileage > maxMileage)) return false
    if (onlyWithMileage && entry.mileage === null) return false
    if (onlyNear && !((entry.progress ?? 0) >= NEAR_THRESHOLD_PCT || entry.rec.level === "critical")) return false
    if (onlyCritical && entry.rec.level !== "critical") return false
    if (hideTest && isTestInterval(item)) return false
    return true
  })
  const sortedEnriched = [...filteredEnriched].sort((a, b) => compareEnriched(a, b, sortKey, sortDir))
  // One group per unit, in the same order as the flat list (largest mileage first by default).
  const groups = groupByUnit(filteredEnriched, sortKey, sortDir)
  // Counts, empty states and CSV use the flat list of intervals.
  const visible = sortedEnriched.map((entry) => entry.item)

  const hasActiveFilters =
    filterType !== "all" || !!filterUnit || filter !== "all" || filterUrgency !== "all" || !!filterAssetId ||
    !!filterDepot || filterMinMileage !== "" || filterMaxMileage !== "" || onlyNear || onlyWithMileage ||
    onlyCritical || hideTest || !!filterAssetType

  // Summary cards count units, not intervals (a unit has up to nine intervals).
  const unitsWithMileage = groups.filter((group) => group.lead.mileage !== null)
  const topMileage = unitsWithMileage.reduce<UnitGroup | null>(
    (best, group) => (best === null || (group.lead.mileage ?? 0) > (best.lead.mileage ?? 0) ? group : best),
    null,
  )
  const averageMileage = unitsWithMileage.length
    ? unitsWithMileage.reduce((sum, group) => sum + (group.lead.mileage ?? 0), 0) / unitsWithMileage.length
    : null
  const criticalCount = groups.filter((group) => group.level === "critical").length
  const nearCount = groups.filter((group) => group.level === "warning").length

  // Data quality, computed on everything the server returned (not only what passes the filters).
  const unitsTotal = new Set(allEnriched.map((entry) => entry.item.asset_id)).size
  const unitsWithoutDepot = new Set(allEnriched.filter((entry) => !entry.item.depot).map((entry) => entry.item.asset_id)).size
  const testEntries = allEnriched.filter((entry) => isTestInterval(entry.item))
  const testUnits = new Set(testEntries.map((entry) => entry.item.asset_id)).size

  // How many units of each kind of equipment the server returned (drives the colourful type chips).
  const assetTypeList = [
    ...allEnriched
      .reduce((acc, entry) => {
        const type = entry.item.asset_type
        if (!type) return acc
        const found = acc.get(type)
        if (found) found.units.add(entry.item.asset_id)
        else acc.set(type, { type, item: entry.item, units: new Set([entry.item.asset_id]) })
        return acc
      }, new Map<string, { type: string; item: ScheduleItem; units: Set<string> }>())
      .values(),
  ].sort((a, b) => b.units.size - a.units.size)

  // "Виды работ" come from the work-types directory (plus any code the data has that the directory lacks).
  const itemCountByCode = new Map<string, number>()
  for (const entry of allEnriched) {
    const code = intervalCode(entry.item.type)
    itemCountByCode.set(code, (itemCountByCode.get(code) ?? 0) + 1)
  }
  const directoryCodes = new Set(workTypes.map((workType) => workType.code))
  const workTypeLegend = [
    ...[...workTypes]
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((workType) => ({
        code: workType.code,
        cfg: typeCfg(workType.code),
        count: itemCountByCode.get(workType.code) ?? 0,
        title: `${intervalTitle(workType.code)}${workType.description ? ` — ${workType.description}` : ""} · ${workType.unit_type === "wagon" ? "для вагонов" : "для локомотивов"}`,
      })),
    ...[...itemCountByCode]
      .filter(([code]) => !directoryCodes.has(code))
      .map(([code, count]) => ({ code, cfg: typeCfg(code), count, title: `${intervalTitle(code)} · нет в справочнике видов работ` })),
  ]

  // Table paging counts units when grouped, intervals otherwise.
  const tableTotal = grouped ? groups.length : sortedEnriched.length
  const totalTablePages = Math.max(1, Math.ceil(tableTotal / tablePageSize))
  const safeTablePage = Math.min(tablePage, totalTablePages - 1)
  const pageFrom = safeTablePage * tablePageSize
  type DisplayRow = { entry: Enriched; group: UnitGroup | null; child: boolean; rank: number | null }
  const displayRows: DisplayRow[] = grouped
    ? groups.slice(pageFrom, pageFrom + tablePageSize).flatMap((group, index): DisplayRow[] => [
        { entry: group.lead, group, child: false, rank: pageFrom + index + 1 },
        ...(expanded.has(group.key)
          ? group.entries.filter((entry) => entry !== group.lead).map((entry): DisplayRow => ({ entry, group, child: true, rank: null }))
          : []),
      ])
    : sortedEnriched.slice(pageFrom, pageFrom + tablePageSize).map((entry, index): DisplayRow => ({ entry, group: null, child: false, rank: pageFrom + index + 1 }))

  const totalGanttPages = Math.max(1, Math.ceil(groups.length / GANTT_UNITS_PER_PAGE))
  const safeGanttPage = Math.min(ganttPage, totalGanttPages - 1)
  const ganttItems = groups
    .slice(safeGanttPage * GANTT_UNITS_PER_PAGE, (safeGanttPage + 1) * GANTT_UNITS_PER_PAGE)
    .flatMap((group) => group.entries.map((entry) => entry.item))

  const toggleExpanded = (key: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const toggleSort = (key: SortKey) => {
    setTablePage(0)
    if (sortKey === key) setSortDir((current) => (current === "asc" ? "desc" : "asc"))
    else {
      setSortKey(key)
      setSortDir(defaultSortDir(key))
    }
  }

  const resetAllFilters = () => {
    setFilterType("all")
    setFilterUnit("")
    setFilter("all")
    setFilterUrgency("all")
    setFilterAssetId("")
    setFilterDepot("")
    setFilterMinMileage("")
    setFilterMaxMileage("")
    setOnlyNear(false)
    setOnlyWithMileage(false)
    setOnlyCritical(false)
    setHideTest(false)
    setFilterAssetType("")
    setTablePage(0)
  }

  // Click a value in the table to filter by it; click again to clear.
  const toggleTypeFilter = (type: string) => { setFilterType((current) => (current === type ? "all" : type)); setTablePage(0) }
  const toggleDepotFilter = (depot: string) => { setFilterDepot((current) => (current === depot ? "" : depot)); setTablePage(0) }
  const toggleStatusFilter = (status: Status) => { setFilter((current) => (current === status ? "all" : status)); setTablePage(0) }
  const toggleUrgencyFilter = (urgency: "high" | "medium" | "low") => { setFilterUrgency((current) => (current === urgency ? "all" : urgency)); setTablePage(0) }

  const activePills: { key: string; label: string; clear: () => void }[] = []
  if (filterType !== "all") activePills.push({ key: "type", label: `Вид ТО: ${filterType}`, clear: () => setFilterType("all") })
  if (filterDepot) activePills.push({ key: "depot", label: `Участок: ${filterDepot === NO_DEPOT ? "не указан" : filterDepot}`, clear: () => setFilterDepot("") })
  if (filter !== "all") activePills.push({ key: "status", label: `Статус: ${statusConfig[filter].label}`, clear: () => setFilter("all") })
  if (filterUrgency !== "all") activePills.push({ key: "urgency", label: `Срочность: ${URGENCY_LABEL[filterUrgency].label}`, clear: () => setFilterUrgency("all") })
  if (filterUnit) activePills.push({ key: "unit", label: `Поиск: ${filterUnit}`, clear: () => setFilterUnit("") })
  if (filterAssetId) activePills.push({ key: "asset", label: "Одна единица", clear: () => setFilterAssetId("") })
  if (onlyCritical) activePills.push({ key: "critical", label: "Только срочные", clear: () => setOnlyCritical(false) })
  if (onlyNear) activePills.push({ key: "near", label: `Близко к порогу (≥${NEAR_THRESHOLD_PCT}%)`, clear: () => setOnlyNear(false) })
  if (onlyWithMileage) activePills.push({ key: "withMileage", label: "Только с пробегом", clear: () => setOnlyWithMileage(false) })
  if (filterAssetType) activePills.push({ key: "assetType", label: `Техника: ${assetStyle(filterAssetType).label}`, clear: () => setFilterAssetType("") })
  if (hideTest) activePills.push({ key: "hideTest", label: "Тестовые интервалы скрыты", clear: () => setHideTest(false) })
  if (filterMinMileage !== "" || filterMaxMileage !== "") {
    activePills.push({
      key: "mileage",
      label: `Пробег: ${filterMinMileage || "0"} — ${filterMaxMileage || "∞"} км`,
      clear: () => { setFilterMinMileage(""); setFilterMaxMileage("") },
    })
  }

  const todayIso = toIsoDate(new Date())
  // Dragging needs the backend that stores manual dates; an older backend never sends `dateManual`.
  const canReschedule = canUpdatePlans && allSchedule.every((item) => item.dateManual !== undefined)

  const requestMove = (item: ScheduleItem, toIso: string) => {
    const problem = validateRescheduleDate(toIso, todayIso)
    if (problem) {
      addNotification({ type: "warning", title: "Перенос невозможен", message: problem }, undefined, true)
      return
    }
    if (toIso === item.startDate.slice(0, 10)) return
    setMoveError(null)
    setPendingMove({ item, toIso })
  }

  const confirmMove = async (reason: string) => {
    if (!pendingMove) return
    const { item, toIso } = pendingMove
    setMoveBusy(true)
    setMoveError(null)
    try {
      if (item.entity_type === "maintenance_plan" && item.plan_id) {
        await api.maintenancePlans.update(item.plan_id, {
          scheduled_date: toIso,
          ...(reason ? { reschedule_reason: reason } : {}),
        })
      } else if (item.entity_type === "forecast" && item.interval_id) {
        await api.maintenancePlans.createFromForecast({
          asset_id: item.asset_id,
          interval_id: item.interval_id,
          scheduled_date: toIso,
          ...(reason ? { reschedule_reason: reason } : {}),
        })
      } else {
        throw new Error("Эту запись перенести нельзя")
      }
      setPendingMove(null)
      addNotification({
        type: "success",
        title: "Срок ТО перенесён",
        message: `${equipmentTitle(item)} · ${intervalCode(item.type)}: ${formatDate(item.startDate)} → ${formatDate(toIso)}`,
      }, undefined, true)
      await Promise.all([fetchSchedule(monthOffset), fetchPlans()])
    } catch (cause) {
      setMoveError(cause instanceof Error ? cause.message : "Не удалось перенести срок ТО")
    } finally {
      setMoveBusy(false)
    }
  }

  const resetManualDate = async (item: ScheduleItem) => {
    if (!item.plan_id) return
    const recommended = item.recommendedDate ? formatDate(item.recommendedDate) : "рекомендованную системой"
    if (!window.confirm(`Вернуть ${recommended}? Ваша ручная дата ${formatDate(item.startDate)} будет снята.`)) return
    setMoveBusy(true)
    try {
      await api.maintenancePlans.update(item.plan_id, { reset_schedule: true })
      addNotification({ type: "info", title: "Возвращена рекомендованная дата", message: `${equipmentTitle(item)} · ${intervalCode(item.type)}` }, undefined, true)
      await Promise.all([fetchSchedule(monthOffset), fetchPlans()])
    } catch (cause) {
      setPlanUpdateError(cause instanceof Error ? cause.message : "Не удалось вернуть рекомендованную дату")
    } finally {
      setMoveBusy(false)
    }
  }

  const refreshAll = () => Promise.all([fetchSchedule(monthOffset), fetchPlans(), fetchLive()])

  const runLive = async (action: () => Promise<unknown>, done: { title: string; message: string }, failure: string) => {
    setLiveBusy(true)
    setLiveError(null)
    try {
      await action()
      setLiveDialog(null)
      addNotification({ type: "success", ...done }, undefined, true)
      await refreshAll()
      return true
    } catch (cause) {
      setLiveError(cause instanceof Error ? cause.message : failure)
      return false
    } finally {
      setLiveBusy(false)
    }
  }

  const confirmBlock = (item: ScheduleItem, data: { reason_code: MaintenanceBlockReason; until: string | null; note: string | null }) =>
    runLive(() => api.maintenancePlans.block(item.plan_id as string, data),
      { title: "План заблокирован", message: `${equipmentTitle(item)} · ${intervalCode(item.type)}: обязательство сохранено` },
      "Не удалось заблокировать план")

  const unblockItem = async (item: ScheduleItem) => {
    if (!item.plan_id) return
    await runLive(() => api.maintenancePlans.unblock(item.plan_id as string),
      { title: "Блокировка снята", message: `${equipmentTitle(item)} · ${intervalCode(item.type)} вернулся в план` },
      "Не удалось снять блокировку")
  }

  const confirmWaive = (item: ScheduleItem, reason: string) =>
    runLive(() => api.maintenancePlans.waive(item.plan_id as string, { reason }),
      { title: "Цикл пропущен", message: `${equipmentTitle(item)} · ${intervalCode(item.type)}: следующий отсчёт от порога этого цикла` },
      "Не удалось пропустить цикл")

  const confirmBaseline = (item: ScheduleItem, payload: { done_at: string; km?: number | null; odometer_km?: number | null; hours?: number | null; note?: string | null }) =>
    runLive(() => api.maintenanceLive.saveBaseline({ asset_id: item.asset_id, interval_id: item.interval_id as string, ...payload }),
      { title: "Последнее ТО сохранено", message: `${equipmentTitle(item)} · ${intervalCode(item.type)}: прогноз пересчитан от новой точки отсчёта` },
      "Не удалось сохранить последнее ТО")

  const confirmDisruption = (data: MaintenanceDisruptionCreate) =>
    runLive(() => api.maintenanceLive.createDisruption(data),
      { title: "Сбой зафиксирован", message: "Запланированные работы в этот период заблокированы, но не потеряны" },
      "Не удалось зафиксировать сбой")

  const closeDisruption = async (id: string) => {
    setClosingDisruptionId(id)
    try {
      await api.maintenanceLive.closeDisruption(id)
      addNotification({ type: "success", title: "Сбой закрыт", message: "Заблокированные работы вернулись в план" }, undefined, true)
      await refreshAll()
    } catch (cause) {
      addNotification({ type: "error", title: "Не удалось закрыть сбой", message: cause instanceof Error ? cause.message : "Ошибка запроса" }, undefined, true)
    } finally {
      setClosingDisruptionId(null)
    }
  }

  const drawerEntry = drawerId ? allEnriched.find((entry) => entry.item.id === drawerId) ?? null : null
  const drawerPlanId = drawerEntry?.item.plan_id ?? null
  useEffect(() => {
    setDecisions(null)
    setDecisionsError(false)
    if (!drawerPlanId) return
    let active = true
    api.maintenancePlans.decisions(drawerPlanId)
      .then((rows) => { if (active) setDecisions(rows) })
      .catch(() => { if (active) setDecisionsError(true) })
    return () => { active = false }
  }, [drawerPlanId, schedule])
  const drawerSiblings = drawerEntry
    ? allEnriched
        .filter((entry) => entry.item.asset_id === drawerEntry.item.asset_id)
        .sort((a, b) => compareEnriched(a, b, "remaining", "asc"))
    : []

  const exportCsv = () => {
    const header = ["№", "Ед.ТПС", "Тип техники", "Модель", "Участок", "Исполнитель", "Пробег, км", "Вид ТО", "Порог ТО, км", "Осталось, км", "Осталось, дн.", "Выработка, %", "Срочность", "Дата", "Статус", "Рекомендация"]
    const rows = sortedEnriched.map((entry, index) => [
      index + 1,
      entry.item.unit,
      entry.item.asset_type_name ?? entry.item.asset_type ?? "",
      entry.item.asset_model ?? "",
      entry.item.depot || "",
      entry.item.tech || "",
      entry.mileage,
      entry.item.type,
      entry.threshold,
      entry.remaining,
      entry.daysLeft,
      entry.progress === null ? null : Math.round(entry.progress),
      entry.item.urgency ? URGENCY_LABEL[entry.item.urgency].label : "",
      dateToDdMmYyyy(entry.item.startDate),
      statusConfig[entry.item.status].label,
      entry.rec.text,
    ])
    const blob = new Blob([buildCsv(header, rows)], { type: "text/csv;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `maintenance-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const counts = {
    all:         allSchedule.length,
    upcoming:    allSchedule.filter(s => s.status === "upcoming").length,
    in_progress: allSchedule.filter(s => s.status === "in_progress").length,
    completed:   allSchedule.filter(s => s.status === "completed").length,
    overdue:     allSchedule.filter(s => s.status === "overdue").length,
    blocked:     allSchedule.filter(s => s.status === "blocked").length,
  }

  if (loading && !hasLoadedRef.current) return (
    <div className="flex items-center justify-center h-96 text-gray-400 text-sm gap-3">
      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
      {"Загрузка графика..."}
    </div>
  )

  return (
    <div className="p-8 space-y-6">
      <ToastContainer notifications={notifications} onDismiss={dismissNotification} />
      
      {quickItem && (
        <QuickOrderModal 
          item={quickItem} 
          onClose={() => setQuickItem(null)} 
          sections={sections}
          employees={employees}
          workTypes={workTypes}
          onOrderCreated={fetchSchedule}
          onNotify={addNotification}
        />
      )}

      {drawerEntry && (
        <DetailDrawer
          entry={drawerEntry}
          siblings={drawerSiblings}
          onSelect={setDrawerId}
          plan={plans.find((plan) => plan.id === drawerEntry.item.plan_id)}
          canUpdate={canUpdatePlans}
          updating={updatingPlanId !== null && updatingPlanId === drawerEntry.item.plan_id}
          error={planUpdateError}
          onClose={() => setDrawerId(null)}
          onCreateOrder={(item) => { setDrawerId(null); handleCreateOrder(item) }}
          onChangeStatus={updatePlanStatus}
          canReschedule={canReschedule}
          suspended={pendingMove !== null}
          onRequestMove={requestMove}
          onResetDate={resetManualDate}
          isAdmin={user?.role === "admin"}
          todayIso={todayIso}
          decisions={decisions}
          decisionsError={decisionsError}
          onBlock={(item) => { setLiveError(null); setLiveDialog({ kind: "block", item }) }}
          onUnblock={(item) => void unblockItem(item)}
          onWaive={(item) => { setLiveError(null); setLiveDialog({ kind: "waive", item }) }}
          onBaseline={(item) => { setLiveError(null); setLiveDialog({ kind: "baseline", item }) }}
        />
      )}
      {liveDialog?.kind === "block" && (
        <BlockDialog item={liveDialog.item} todayIso={todayIso} busy={liveBusy} error={liveError}
          onConfirm={(data) => void confirmBlock(liveDialog.item, data)} onCancel={() => { if (!liveBusy) setLiveDialog(null) }} />
      )}
      {liveDialog?.kind === "waive" && (
        <WaiveDialog item={liveDialog.item} busy={liveBusy} error={liveError}
          onConfirm={(reason) => void confirmWaive(liveDialog.item, reason)} onCancel={() => { if (!liveBusy) setLiveDialog(null) }} />
      )}
      {liveDialog?.kind === "baseline" && (
        <BaselineDialog item={liveDialog.item} todayIso={todayIso} busy={liveBusy} error={liveError}
          onConfirm={(payload) => void confirmBaseline(liveDialog.item, payload)} onCancel={() => { if (!liveBusy) setLiveDialog(null) }} />
      )}
      {liveDialog?.kind === "disruption" && (
        <DisruptionDialog todayIso={todayIso} sections={sections} busy={liveBusy} error={liveError}
          assets={assetOptions.map(([id, label]) => ({ id, label }))}
          onConfirm={(data) => void confirmDisruption(data)} onCancel={() => { if (!liveBusy) setLiveDialog(null) }} />
      )}
      {pendingMove && (
        <RescheduleDialog
          item={pendingMove.item}
          toIso={pendingMove.toIso}
          todayIso={todayIso}
          dailyKm={dailyKm}
          color={typeCfg(pendingMove.item.type).color}
          busy={moveBusy}
          error={moveError}
          onConfirm={(reason) => void confirmMove(reason)}
          onCancel={() => { if (!moveBusy) { setPendingMove(null); setMoveError(null) } }}
        />
      )}

      {/* Заголовок */}
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{"ТО и ремонты"}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {"График ТО и ремонтов"}
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center justify-between gap-3 sm:w-auto sm:justify-end">
          {loading && hasLoadedRef.current && <span className="text-xs text-gray-400">{"Обновление…"}</span>}
          {/* Колокольчик уведомлений */}
          <NotificationBell
            notifications={allNotifications}
            onMarkAsRead={markNotificationAsRead}
            onMarkAllAsRead={markAllNotificationsAsRead}
            onClear={clearAllNotifications}
          />

          {/* Переключение вида */}
          <div className="flex p-1 bg-gray-100 dark:bg-gray-800 rounded-xl gap-1">
            <button onClick={() => setView("gantt")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                view==="gantt" ? "bg-white dark:bg-gray-900 text-blue-600 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}>
              <BarChart3 className="w-4 h-4"/> {"Диаграмма Ганта"}
            </button>
            <button onClick={() => setView("table")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                view==="table" ? "bg-white dark:bg-gray-900 text-blue-600 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}>
              <List className="w-4 h-4"/> {"Список"}
            </button>
          </div>
        </div>
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{"Расчётная средняя суточная наработка"}</h2>
            <p className="mt-1 text-xs text-gray-500">
              {"Значение используется для прогноза дат ТО по пробегу. Настраивают администратор, оператор или инженер."}
            </p>
          </div>
          {canConfigureMaintenance ? (
            <div className="flex w-full gap-2 md:max-w-sm">
              <label className="flex-1 text-xs text-gray-500">
                {"км в день"}
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={dailyAverageKm}
                  onChange={(event) => setDailyAverageKm(event.target.value)}
                  disabled={settingsLoading || settingsSaving}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                />
              </label>
              <button
                type="button"
                onClick={() => void saveDailyAverageKm()}
                disabled={settingsLoading || settingsSaving}
                className="self-end rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {settingsSaving ? "Сохранение..." : "Сохранить"}
              </button>
            </div>
          ) : (
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {dailyAverageKm ? `${dailyAverageKm} ${"км в день"}` : "Значение ещё не настроено"}
            </p>
          )}
        </div>
        {settingsError && <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{settingsError}</p>}
        {!settingsLoading && !dailyAverageKm && (
          <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
            {"Суточный пробег не настроен: календарные прогнозы по километровым интервалам не рассчитываются."}
          </p>
        )}
      </section>

      {scheduleError && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {"Не удалось загрузить график:"} {scheduleError}
        </p>
      )}
      {plansError && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {"Не удалось загрузить планы ТО"}: {plansError}
        </p>
      )}
      {planUpdateError && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {"Не удалось обновить статус плана ТО"}: {planUpdateError}
        </p>
      )}

      {unitsTotal > 0 && unitsWithoutDepot / unitsTotal >= 0.3 && (
        <div role="note" className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <span>{`У ${unitsWithoutDepot} из ${unitsTotal} агрегатов не указан участок, поэтому фильтр по участкам неполный.`}</span>
          <button type="button" onClick={() => { setFilterDepot(NO_DEPOT); setShowFilters(true); setTablePage(0) }}
            className="rounded-lg border border-amber-300 px-3 py-1 text-xs font-medium hover:bg-amber-100 dark:border-amber-800 dark:hover:bg-amber-900/40">
            {"Показать без участка"}
          </button>
          <a href="/dashboard/directories/assets" className="text-xs font-medium underline">{"Назначить участки →"}</a>
        </div>
      )}
      {testEntries.length > 0 && (
        <div role="note" className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <span>{`Найден тестовый интервал «test»: ${testEntries.length} ${plural(testEntries.length, ["запись", "записи", "записей"])} у ${testUnits} ${plural(testUnits, ["агрегата", "агрегатов", "агрегатов"])}. Он засоряет список: отключите его в справочнике интервалов или скройте здесь.`}</span>
          <button type="button" onClick={() => { setHideTest((current) => !current); setTablePage(0) }}
            className="rounded-lg border border-amber-300 px-3 py-1 text-xs font-medium hover:bg-amber-100 dark:border-amber-800 dark:hover:bg-amber-900/40">
            {hideTest ? "Показать тестовые" : "Скрыть тестовые"}
          </button>
          <a href="/dashboard/directories/maintenance-intervals" className="text-xs font-medium underline">{"Справочник интервалов →"}</a>
        </div>
      )}

      {/* ═══ ПАНЕЛЬ ФИЛЬТРОВ ═══ */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {/* Кнопка раскрытия фильтров */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              hasActiveFilters
                ? "bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400"
                : "bg-gray-100 dark:bg-gray-800 text-gray-500"
            }`}>
              <Filter className="w-4 h-4" />
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-white">{"Фильтры"}</span>
            {hasActiveFilters && (
              <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                {"Активны"}
              </span>
            )}
          </div>
          <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${showFilters ? "rotate-180" : ""}`} />
        </button>

        {/* Раскрывающаяся панель фильтров */}
        {showFilters && (
          <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800">
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 pt-4">
              
              {/* Поиск по названию */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  {"Поиск оборудования"}
                </label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={filterUnit}
                    onChange={(e) => setFilterUnit(e.target.value)}
                    placeholder={"Введите номер..."}
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Фильтр по типу ТО */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  {"Тип ТО"}
                </label>
                <select
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent appearance-none cursor-pointer"
                >
                  <option value="all">{"Все типы"}</option>
                  {uniqueTypes.map(type => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>

              {/* Фильтр по статусу */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  {"Статус"}
                </label>
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value as Status | "all")}
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent appearance-none cursor-pointer"
                >
                  <option value="all">{"Все статусы"}</option>
                  <option value="overdue">🔴 {"Просрочено"} ({counts.overdue})</option>
                  <option value="in_progress">🟡 {"Выполняется"} ({counts.in_progress})</option>
                  <option value="upcoming">⚪ {"Запланировано"} ({counts.upcoming})</option>
                  <option value="completed">🟢 {"Выполнено"} ({counts.completed})</option>
                  <option value="blocked">🟠 {"Заблокировано"} ({counts.blocked})</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  {"Уровень срочности"}
                </label>
                <select
                  value={filterUrgency}
                  onChange={(event) => setFilterUrgency(event.target.value as typeof filterUrgency)}
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
                >
                  <option value="all">{"Все уровни срочности"}</option>
                  <option value="high">{"Высокая"}</option>
                  <option value="medium">{"Средняя"}</option>
                  <option value="low">{"Низкая"}</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  {"Оборудование"}
                </label>
                <select
                  value={filterAssetId}
                  onChange={(event) => setFilterAssetId(event.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
                >
                  <option value="">{"Все единицы"}</option>
                  {assetOptions.map(([assetId, unit]) => (
                    <option key={assetId} value={assetId}>{unit}</option>
                  ))}
                </select>
              </div>

              {/* Кнопка сброса */}
              <div className="flex items-end">
                <button
                  onClick={resetAllFilters}
                  disabled={!hasActiveFilters}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <RotateCcw className="w-4 h-4" />
                  {"Сбросить"}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 pt-4">
              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  {"Участок"}
                </label>
                <select
                  value={filterDepot}
                  onChange={(event) => { setFilterDepot(event.target.value); setTablePage(0) }}
                  className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
                >
                  <option value="">{"Все участки"}</option>
                  <option value={NO_DEPOT}>{"— без участка —"}</option>
                  {depotOptions.map((depot) => <option key={depot} value={depot}>{depot}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  {"Пробег, км (от — до)"}
                </label>
                <div className="flex items-center gap-2">
                  <input type="number" min="0" inputMode="decimal" placeholder={"от"} aria-label={"Пробег от"} value={filterMinMileage}
                    onChange={(event) => { setFilterMinMileage(event.target.value); setTablePage(0) }}
                    className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white" />
                  <span className="text-gray-400">—</span>
                  <input type="number" min="0" inputMode="decimal" placeholder={"до"} aria-label={"Пробег до"} value={filterMaxMileage}
                    onChange={(event) => { setFilterMaxMileage(event.target.value); setTablePage(0) }}
                    className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white" />
                </div>
              </div>
              <label className="flex items-end gap-2 pb-2.5 text-sm text-gray-700 dark:text-gray-300 md:col-span-1 lg:col-span-1">
                <input type="checkbox" checked={onlyNear} onChange={(event) => { setOnlyNear(event.target.checked); setTablePage(0) }} />
                {`Близко к порогу (≥${NEAR_THRESHOLD_PCT}%)`}
              </label>
              <label className="flex items-end gap-2 pb-2.5 text-sm text-gray-700 dark:text-gray-300">
                <input type="checkbox" checked={onlyWithMileage} onChange={(event) => { setOnlyWithMileage(event.target.checked); setTablePage(0) }} />
                {"Только с данными о пробеге"}
              </label>
            </div>

            {/* Быстрые фильтры по типу ТО */}
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-gray-400 mr-2">{"Быстрый выбор:"}</span>
                <button
                  onClick={() => setFilterType("all")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    filterType === "all"
                      ? "bg-blue-500 text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  {"Все"}
                </button>
                {uniqueTypes.map(type => {
                  const cfg = typeCfg(type)
                  const count = allSchedule.filter(s => intervalCode(s.type) === type).length
                  return (
                    <button
                      key={type}
                      onClick={() => setFilterType(type)}
                      style={{ 
                        backgroundColor: filterType === type ? cfg.color : undefined,
                        borderColor: cfg.color
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border-2 transition-all ${
                        filterType === type
                          ? "text-white"
                          : "bg-white dark:bg-gray-900 hover:opacity-80"
                      }`}
                    >
                      {intervalCode(type)} ({count})
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Результаты фильтрации */}
            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-gray-500 dark:text-gray-400">
                {"Найдено:"} <span className="font-bold text-gray-900 dark:text-white">{visible.length}</span> {"из"} {allSchedule.length}
              </span>
              {visible.length === 0 && hasActiveFilters && (
                <span className="text-amber-600 dark:text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" />
                  {"Нет результатов по заданным фильтрам"}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Сортировка и сводка по пробегу */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-900">
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{"Сортировка:"}</span>
        <select
          aria-label={"Сортировать по"}
          value={sortKey}
          onChange={(event) => { const key = event.target.value as SortKey; setSortKey(key); setSortDir(defaultSortDir(key)); setTablePage(0) }}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
        >
          {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => <option key={key} value={key}>{SORT_LABELS[key]}</option>)}
        </select>
        <button type="button" onClick={() => setSortDir((current) => (current === "asc" ? "desc" : "asc"))}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
          {sortDir === "desc" ? "▼ по убыванию" : "▲ по возрастанию"}
        </button>
        <span className="ml-auto text-xs text-gray-400">{"Записи без данных о пробеге всегда внизу списка"}</span>
      </div>

      {assetTypeList.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-gray-400">{"Техника:"}</span>
          {assetTypeList.map(({ type, item, units }) => {
            const style = assetStyle(type)
            const active = filterAssetType === type
            return (
              <button key={type} type="button" aria-pressed={active}
                onClick={() => { setFilterAssetType(active ? "" : type); setTablePage(0) }}
                className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all ${
                  active
                    ? `border-transparent bg-gradient-to-br text-white shadow-md ${style.gradient}`
                    : `${style.soft} ${style.text} ${style.ring} hover:shadow-sm`
                }`}>
                <AssetTypeIcon type={type} className="h-4 w-4" />
                {item.asset_type_name ?? style.label}
                <span className={`rounded-full px-1.5 text-[10px] ${active ? "bg-white/25" : "bg-white/70 dark:bg-black/20"}`}>{units.size}</span>
              </button>
            )
          })}
        </div>
      )}

      {activePills.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-gray-400">{"Применено:"}</span>
          {activePills.map((pill) => (
            <button key={pill.key} type="button" onClick={() => { pill.clear(); setTablePage(0) }} title={"Нажмите, чтобы убрать"}
              className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-300">
              {pill.label} <span aria-hidden="true">✕</span>
            </button>
          ))}
          <button type="button" onClick={resetAllFilters} className="text-xs font-medium text-gray-500 underline hover:text-gray-800 dark:hover:text-gray-200">{"Сбросить всё"}</button>
        </div>
      )}

      <LiveOverview kpis={kpis} disruptions={disruptions} sections={sections} canUpdate={canUpdatePlans}
        assetLabel={(id) => assetOptions.find(([assetId]) => assetId === id)?.[1] ?? "техника"}
        busyId={closingDisruptionId} onClose={(id) => void closeDisruption(id)}
        onCreate={() => { setLiveError(null); setLiveDialog({ kind: "disruption" }) }} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <button type="button" onClick={() => { if (topMileage) setDrawerId(topMileage.lead.item.id) }} disabled={!topMileage}
          className="rounded-2xl border border-gray-200 bg-white p-4 text-left transition-colors hover:border-blue-300 disabled:cursor-default dark:border-gray-800 dark:bg-gray-900">
          <p className="text-xs font-semibold text-gray-500">{"Максимальный пробег"}</p>
          <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{topMileage?.lead.mileage != null ? `${fmtNum(topMileage.lead.mileage)} км` : "—"}</p>
          <p className="mt-1 truncate text-xs text-gray-400" title={topMileage ? equipmentSubtitle(topMileage.lead.item) : undefined}>{topMileage ? equipmentTitle(topMileage.lead.item) : "Нет данных"}</p>
        </button>
        <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
          <p className="text-xs font-semibold text-gray-500">{"Средний пробег"}</p>
          <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{averageMileage !== null ? `${fmtNum(averageMileage)} км` : "—"}</p>
          <p className="mt-1 text-xs text-gray-400">{`по ${unitsWithMileage.length} ${plural(unitsWithMileage.length, ["агрегату", "агрегатам", "агрегатам"])} с пробегом`}</p>
        </div>
        <button type="button" onClick={() => { setOnlyCritical((current) => !current); setTablePage(0) }}
          className={`rounded-2xl border p-4 text-left transition-colors ${onlyCritical ? "border-red-400 bg-red-100 dark:border-red-700 dark:bg-red-950/40" : "border-red-200 bg-red-50/60 hover:bg-red-50 dark:border-red-900 dark:bg-red-950/20"}`}>
          <p className="text-xs font-semibold text-red-700 dark:text-red-300">{"Нужны срочные действия"}</p>
          <p className="mt-1 text-2xl font-bold text-red-700 dark:text-red-300">{criticalCount}</p>
          <p className="mt-1 text-xs text-red-600/70 dark:text-red-300/70">{onlyCritical ? "нажмите, чтобы снять фильтр" : "порог превышен или наряд просрочен — нажмите, чтобы показать"}</p>
        </button>
        <button type="button" onClick={() => { setOnlyNear((current) => !current); setTablePage(0) }}
          className={`rounded-2xl border p-4 text-left transition-colors ${onlyNear ? "border-amber-400 bg-amber-100 dark:border-amber-700 dark:bg-amber-950/40" : "border-amber-200 bg-amber-50/60 hover:bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20"}`}>
          <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">{`Близко к порогу (≥${NEAR_THRESHOLD_PCT}%)`}</p>
          <p className="mt-1 text-2xl font-bold text-amber-800 dark:text-amber-300">{nearCount}</p>
          <p className="mt-1 text-xs text-amber-700/70 dark:text-amber-300/70">{onlyNear ? "нажмите, чтобы снять фильтр" : "нажмите, чтобы показать только их"}</p>
        </button>
      </div>

      {/* KPI карточки */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5 sm:gap-4">
        {(["upcoming","in_progress","completed","overdue","blocked"] as Status[]).map(s => {
          const cfg = statusConfig[s]
          const count = counts[s]
          const pct = counts.all > 0 ? Math.round((count / counts.all) * 100) : 0
          return (
            <button key={s} onClick={() => setFilter(filter===s ? "all" : s)}
              className={`text-left p-5 rounded-2xl border-2 transition-all ${
                filter===s
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-950/40 shadow-md"
                  : "border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 hover:border-blue-300"
              }`}>
              <div className="flex items-center justify-between mb-3">
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${cfg.cls}`}>
                  <cfg.icon className="w-4 h-4"/>
                </div>
                <span className="text-2xl font-bold text-gray-900 dark:text-white">{count}</span>
              </div>
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">              {cfg.label}</p>
              <div className="mt-2 h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                <div className={`h-full rounded-full transition-all ${cfg.cls.split(" ")[0].replace("bg-","bg-").replace("-100","-500").replace("-950","-500")}`}
                  style={{ width: `${pct}%` }}/>
              </div>
              <p className="text-[10px] text-gray-400 mt-1">{pct}% {"от всех"}</p>
            </button>
          )
        })}
      </div>

      {/* Виды работ: из справочника; нажмите, чтобы отфильтровать */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs text-gray-400">{"Виды работ:"}</span>
        {workTypeLegend.map((entry) => {
          const active = filterType === entry.code
          return (
            <button key={entry.code} type="button" aria-pressed={active} title={entry.title}
              onClick={() => toggleTypeFilter(entry.code)}
              style={active ? { backgroundColor: entry.cfg.color, borderColor: entry.cfg.color } : undefined}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition-all ${
                active ? "text-white shadow-md" : `${entry.cfg.text} ${entry.cfg.border} bg-white hover:shadow-sm dark:bg-gray-900`
              } ${entry.count === 0 && !active ? "opacity-60" : ""}`}>
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: active ? "#fff" : entry.cfg.color }} />
              {entry.code}
              <span className={`rounded-full px-1.5 text-[10px] ${active ? "bg-white/25" : "bg-gray-100 dark:bg-gray-800"}`}>{entry.count}</span>
            </button>
          )
        })}
        <a href="/dashboard/directories/work-types" className="ml-1 text-xs text-blue-600 hover:underline">{"Справочник →"}</a>
      </div>

      {/* ДИАГРАММА ГАНТА */}
      {view === "gantt" && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
          {/* Шапка с навигацией по месяцам */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
            <div className="flex items-center gap-3">
              <Calendar className="w-4 h-4 text-blue-500"/>
              <h2 className="text-sm font-bold text-gray-900 dark:text-white">{monthLabel}</h2>
              <span className="text-xs text-gray-400">{`· ${groups.length} ${plural(groups.length, ["агрегат", "агрегата", "агрегатов"])}, ${visible.length} ${plural(visible.length, ["интервал", "интервала", "интервалов"])}`}</span>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => setMonthOffset(o => o-1)}
                className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                <ChevronLeft className="w-4 h-4 text-gray-500"/>
              </button>
              <button onClick={() => setMonthOffset(0)}
                className="px-3 py-1 text-xs font-medium rounded-lg bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 hover:bg-blue-200 transition-colors">
                {"Сегодня"}
              </button>
              <button onClick={() => setMonthOffset(o => o+1)}
                className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                <ChevronRight className="w-4 h-4 text-gray-500"/>
              </button>
            </div>
          </div>

          <div className="px-6 py-4">
            {visible.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Calendar className="w-12 h-12 opacity-20 mb-3"/>
                {scheduleError ? (
                  <button type="button" onClick={() => void fetchSchedule(monthOffset)} className="text-sm text-blue-600 underline">
                    {"Повторить"}
                  </button>
                ) : (
                  <>
                    <p className="text-sm font-medium">{"Нет работ в этом периоде"}</p>
                    <p className="text-xs mt-1">{"Измените фильтр или перейдите к другому месяцу"}</p>
                  </>
                )}
              </div>
            ) : (
              <>
                <GanttChart items={ganttItems} rangeStart={rangeStart} rangeDays={rangeDays} onCreateOrder={handleCreateOrder} onOpen={(item) => setDrawerId(item.id)} canReschedule={canReschedule} onReschedule={requestMove}/>
                {totalGanttPages > 1 && (
                  <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-gray-800">
                    <span>{`Агрегаты ${safeGanttPage * GANTT_UNITS_PER_PAGE + 1}–${Math.min(groups.length, (safeGanttPage + 1) * GANTT_UNITS_PER_PAGE)} из ${groups.length}`}</span>
                    <div className="flex items-center gap-1">
                      <button type="button" onClick={() => setGanttPage(0)} disabled={safeGanttPage === 0} className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"«"}</button>
                      <button type="button" onClick={() => setGanttPage(Math.max(0, safeGanttPage - 1))} disabled={safeGanttPage === 0} className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"‹"}</button>
                      <span className="px-2">{`${safeGanttPage + 1} / ${totalGanttPages}`}</span>
                      <button type="button" onClick={() => setGanttPage(Math.min(totalGanttPages - 1, safeGanttPage + 1))} disabled={safeGanttPage >= totalGanttPages - 1} className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"›"}</button>
                      <button type="button" onClick={() => setGanttPage(totalGanttPages - 1)} disabled={safeGanttPage >= totalGanttPages - 1} className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"»"}</button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ТАБЛИЧНЫЙ ВИД */}
      {view === "table" && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex flex-wrap items-center gap-3">
            <List className="w-4 h-4 text-blue-500"/>
            <h2 className="text-sm font-bold text-gray-900 dark:text-white">{grouped ? "Агрегаты" : "Список работ"}</h2>
            <span className="text-xs text-gray-400">
              {grouped ? `· ${groups.length} ${plural(groups.length, ["агрегат", "агрегата", "агрегатов"])}, ${visible.length} ${plural(visible.length, ["интервал", "интервала", "интервалов"])}` : `· ${visible.length} позиций`}
            </span>
            <div className="ml-auto flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300">
                <input type="checkbox" checked={grouped} onChange={(event) => { setGrouped(event.target.checked); setTablePage(0) }} />
                {"Группировать по агрегату"}
              </label>
              {grouped && (
                <>
                  <button type="button" onClick={() => setExpanded(new Set(groups.filter((group) => group.entries.length > 1).map((group) => group.key)))}
                    className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400">{"Развернуть все"}</button>
                  <button type="button" onClick={() => setExpanded(new Set())}
                    className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400">{"Свернуть все"}</button>
                </>
              )}
              <label className="flex items-center gap-1.5 text-xs text-gray-500">
                {grouped ? "Агрегатов на странице" : "На странице"}
                <select value={tablePageSize} onChange={(event) => { setTablePageSize(Number(event.target.value)); setTablePage(0) }}
                  className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-700 dark:bg-gray-800">
                  {TABLE_PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
                </select>
              </label>
              <button type="button" onClick={exportCsv} disabled={sortedEnriched.length === 0}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
                {"Экспорт CSV"}
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
          <table className="w-full min-w-[1250px]">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-800">
                {TABLE_COLUMNS.map((column) => {
                  const active = column.sort !== undefined && sortKey === column.sort
                  const label = grouped && column.label === "Вид ТО" ? "Ближайшее ТО" : column.label
                  return (
                    <th key={column.label} aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
                      className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">
                      {column.sort ? (
                        <button type="button" onClick={() => toggleSort(column.sort as SortKey)} title={"Нажмите для сортировки"}
                          className={`inline-flex items-center gap-1 uppercase tracking-wider hover:text-gray-900 dark:hover:text-white ${active ? "text-blue-600 dark:text-blue-400" : ""}`}>
                          {label}
                          <span aria-hidden="true" className={active ? "" : "opacity-30"}>{active ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
                        </button>
                      ) : label}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {visible.length === 0 && !scheduleError && (
                <tr>
                  <td colSpan={TABLE_COLUMNS.length} className="px-5 py-10 text-center text-sm text-gray-400">
                    {hasActiveFilters ? (
                      <>
                        {"Ничего не найдено по заданным фильтрам. "}
                        <button type="button" onClick={resetAllFilters} className="text-blue-600 underline">{"Сбросить фильтры"}</button>
                      </>
                    ) : "Нет данных"}
                  </td>
                </tr>
              )}
              {visible.length === 0 && scheduleError && (
                <tr>
                  <td colSpan={TABLE_COLUMNS.length} className="px-5 py-10 text-center text-sm text-gray-400">
                    <button type="button" onClick={() => void fetchSchedule(monthOffset)} className="text-blue-600 underline">
                      {"Повторить"}
                    </button>
                  </td>
                </tr>
              )}
              {displayRows.map(({ entry, group, child, rank }) => {
                const item = entry.item
                const st = statusConfig[item.status]
                const cfg = typeCfg(item.type)
                const urgency = item.urgency ? URGENCY_LABEL[item.urgency] : null
                const progress = entry.progress
                const barCls = progress === null ? "bg-gray-300" : progress >= 100 ? "bg-red-500" : progress >= NEAR_THRESHOLD_PCT ? "bg-amber-500" : progress >= 70 ? "bg-blue-500" : "bg-emerald-500"
                const planStatus = plans.find((plan) => plan.id === item.plan_id)?.status ??
                  (item.status === "upcoming" || item.status === "overdue" ? "scheduled" : item.status)
                const rowTransitions = PLAN_TRANSITIONS[planStatus] ?? []
                const isExpanded = group !== null && expanded.has(group.key)
                return (
                  <tr key={item.id}
                    tabIndex={0}
                    onClick={() => setDrawerId(item.id)}
                    onKeyDown={(event) => { if (event.key === "Enter" && event.target === event.currentTarget) setDrawerId(item.id) }}
                    title={"Нажмите, чтобы открыть карточку"}
                    className={`cursor-pointer hover:bg-blue-50/50 focus:bg-blue-50/50 focus:outline-none dark:hover:bg-gray-800/50 transition-colors group ${
                    child ? "bg-gray-50/70 dark:bg-gray-800/30" : item.status === "overdue" || entry.rec.level === "critical" ? "bg-red-50/50 dark:bg-red-950/20" : ""
                  }`}>
                    <td className="px-4 py-3 text-xs text-gray-400">{rank ?? ""}</td>
                    <td className="px-4 py-3 min-w-[300px]">
                      {child ? (
                        <span className="pl-5 text-xs text-gray-400">{`↳ ${inventoryNumberOf(item)}`}</span>
                      ) : (
                        <div className="flex items-start gap-3">
                          <EquipmentAvatar item={item} size="md" />
                          <div className="min-w-0">
                            <a href={assetHref(item)} onClick={(event) => event.stopPropagation()} title={"Открыть в основных средствах"}
                              className="text-sm font-semibold text-gray-900 hover:text-blue-600 hover:underline dark:text-white">{equipmentTitle(item)}</a>
                            <p className="text-xs text-gray-500">{equipmentSubtitle(item)}</p>
                            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                              {item.depot ? <SectionChip name={item.depot} onClick={() => toggleDepotFilter(item.depot)} /> : null}
                              <AssetStatusChip item={item} />
                              <OnlineChip item={item} />
                              {item.tech ? <span className="text-[11px] text-gray-400">{`· ${item.tech}`}</span> : null}
                            </div>
                            {group && group.entries.length > 1 && (
                              <button type="button" aria-expanded={isExpanded}
                                onClick={(event) => { event.stopPropagation(); toggleExpanded(group.key) }}
                                className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300">
                                <span aria-hidden="true">{isExpanded ? "▾" : "▸"}</span>
                                {`${group.entries.length} ${plural(group.entries.length, ["интервал", "интервала", "интервалов"])}`}
                                {group.level === "critical" && <span className="text-red-600 dark:text-red-400">{"· срочно"}</span>}
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {child ? null : entry.mileage !== null ? (
                        <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                          {fmtNum(entry.mileage)} км
                        </span>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <button type="button" title={"Фильтр по виду ТО"}
                        onClick={(event) => { event.stopPropagation(); toggleTypeFilter(intervalCode(item.type)) }}
                        className="rounded-lg hover:opacity-80">
                        <IntervalChip type={item.type} color={cfg.color} />
                      </button>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300 whitespace-nowrap">
                      {entry.threshold !== null ? fmtNum(entry.threshold) : "—"}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {entry.remaining !== null ? (
                        <>
                          <span className={`text-sm font-semibold ${
                            entry.remaining <= 0
                              ? "text-red-600 dark:text-red-400"
                              : entry.remaining < 10
                                ? "text-amber-600 dark:text-amber-400"
                                : "text-gray-600 dark:text-gray-300"
                          }`}>
                            {entry.remaining <= 0 ? `−${fmtNum(Math.abs(entry.remaining))}` : fmtNum(entry.remaining)} км
                          </span>
                          {entry.daysLeft !== null && <p className="text-xs text-gray-400">{`≈ ${entry.daysLeft} дн.`}</p>}
                        </>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 min-w-[110px]">
                      {progress !== null ? (
                        <div title={`${Math.round(progress)}% текущего интервала`}>
                          <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                            <div className={`h-full rounded-full ${barCls}`} style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
                          </div>
                          <p className="mt-1 text-[10px] text-gray-400">{Math.round(progress)}%</p>
                        </div>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {urgency && item.urgency ? (
                        <button type="button" title={"Фильтр по срочности"}
                          onClick={(event) => { event.stopPropagation(); toggleUrgencyFilter(item.urgency as "high" | "medium" | "low") }}
                          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold hover:opacity-80 ${urgency.cls}`}>{urgency.label}</button>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {item.priority !== null && item.priority !== undefined ? (
                        <span title={(item.priorityWhy ?? []).join("; ") || "Приоритет"}
                          className={`inline-flex min-w-[2.25rem] justify-center rounded-full px-2 py-0.5 text-xs font-bold ${PRIORITY_CLS[priorityTone(item.priority)]}`}>
                          {item.priority}
                        </span>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                      {item.confidence && item.confidence !== "high" && (
                        <span title={CONFIDENCE_LABEL[item.confidence].hint} className="ml-1 text-xs text-amber-600 dark:text-amber-400">
                          {item.confidence === "stale" ? "⚠" : "≈"}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300 whitespace-nowrap">
                      {dateToDdMmYyyy(item.startDate)}
                      {item.dateManual && (
                        <span title={`Перенесено вручную. Рекомендовано: ${item.recommendedDate ? formatDate(item.recommendedDate) : "—"}${item.rescheduleReason ? `. Причина: ${item.rescheduleReason}` : ""}`}
                          className="ml-1.5 inline-flex rounded bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
                          {"✋ вручную"}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <button type="button" title={"Фильтр по статусу"}
                        onClick={(event) => { event.stopPropagation(); toggleStatusFilter(item.status) }}
                        className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full hover:opacity-80 ${st.cls}`}>
                        <st.icon className="w-3 h-3"/>
                        {st.label}
                      </button>
                    </td>
                    <td className="px-4 py-3 min-w-[240px]">
                      <span className={`inline-block rounded-lg border px-2.5 py-1.5 text-xs leading-snug ${REC_CLS[entry.rec.level]}`}>
                        {entry.rec.text}
                      </span>
                    </td>
                    <td className="px-4 py-3" onClick={(event) => event.stopPropagation()}>
                      {canUpdatePlans && item.entity_type === "maintenance_plan" && item.plan_id && (
                        <label className="sr-only" htmlFor={`plan-status-${item.plan_id}`}>{"Статус плана"}</label>
                      )}
                      {canUpdatePlans && item.entity_type === "maintenance_plan" && item.plan_id && (
                        <select
                          id={`plan-status-${item.plan_id}`}
                          aria-label={"Статус плана"}
                          value={planStatus}
                          disabled={updatingPlanId === item.plan_id || rowTransitions.length === 0}
                          onChange={(event) => {
                            const next = event.target.value as MaintenancePlan["status"]
                            if (next === "cancelled" && !window.confirm("Отменить план ТО? Это действие нельзя отменить.")) return
                            void updatePlanStatus(item, next)
                          }}
                          className="mb-2 w-full rounded-md border border-gray-200 bg-white px-2 py-1 text-xs disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800"
                        >
                          <option value={planStatus}>{PLAN_STATUS_LABEL[planStatus] ?? planStatus}</option>
                          {rowTransitions.map((transition) => (
                            <option key={transition.to} value={transition.to}>{`→ ${PLAN_STATUS_LABEL[transition.to]}`}</option>
                          ))}
                        </select>
                      )}
                      {item.entity_type !== "work_order" && <button
                        onClick={() => handleCreateOrder(item)}
                        className={`flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition-colors whitespace-nowrap border ${
                          item.status === "overdue" || entry.rec.level === "critical"
                            ? "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-950 border-red-200 dark:border-red-800"
                            : "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 hover:bg-blue-100 dark:hover:bg-blue-950 border-blue-200 dark:border-blue-800"
                        }`}>
                        <Plus className="w-3 h-3"/>
                        {"Наряд"}
                      </button>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          </div>

          {totalTablePages > 1 && (
            <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-5 py-3 text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-800/30">
              <span>{`Страница ${safeTablePage + 1} из ${totalTablePages} · ${grouped ? "Агрегатов" : "Записей"}: ${tableTotal}`}</span>
              <div className="flex items-center gap-1">
                <button type="button" onClick={() => setTablePage(0)} disabled={safeTablePage === 0}
                  className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"«"}</button>
                <button type="button" onClick={() => setTablePage(Math.max(0, safeTablePage - 1))} disabled={safeTablePage === 0}
                  className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"‹"}</button>
                <button type="button" onClick={() => setTablePage(Math.min(totalTablePages - 1, safeTablePage + 1))} disabled={safeTablePage >= totalTablePages - 1}
                  className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"›"}</button>
                <button type="button" onClick={() => setTablePage(totalTablePages - 1)} disabled={safeTablePage >= totalTablePages - 1}
                  className="rounded-lg border border-gray-300 px-2.5 py-1 disabled:opacity-40 dark:border-gray-700">{"»"}</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Подсказка */}
      <div className="flex items-start gap-2 text-xs text-gray-400 bg-emerald-50 dark:bg-emerald-950/30 rounded-xl px-4 py-3 border border-emerald-200 dark:border-emerald-700">
        <Gauge className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-emerald-500"/>
        <span>
          <strong className="text-emerald-700 dark:text-emerald-400">{"График ТО:"}</strong>{" "}
          {"Данные о пробеге поступают в реальном времени. При приближении к порогу ТО система автоматически показывает уведомление."}
          {"Нажмите «Открыть наряд» чтобы создать наряд-задание на основе пробега."}{" "}
          <a href="/dashboard/directories/maintenance-intervals" className="ml-1 text-emerald-600 hover:underline">
            {"Настроить интервалы ТО →"}
          </a>
        </span>
      </div>

    </div>
  )
}
