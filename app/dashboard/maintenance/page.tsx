"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { supabase } from "@/lib/supabase"
import { useSections } from "@/lib/use-sections"
import {
  Calendar, Wrench, CheckCircle, Clock, AlertTriangle,
  BarChart3, List, ChevronLeft, ChevronRight, Info, Plus, X, ChevronDown,
  Gauge, Wifi, WifiOff, Bell, Filter, Search, RotateCcw
} from "lucide-react"

/* ═══════════════════════════════════════
   ДАННЫЕ
═══════════════════════════════════════ */
type Status = "upcoming" | "in_progress" | "completed" | "overdue"
type ScheduleItem = {
  id: string
  unit: string
  type: string
  startDate: string
  durationH: number
  depot: string
  tech: string
  status: Status
  note?: string
  mileage?: number
  remainingKm?: number
  nextThreshold?: number
}

type MaintenanceInterval = {
  id: string
  code: string
  name: string
  interval_km: number
  is_active: boolean
}

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
    if (minutes < 60) return `${minutes} мин. назад`
    if (hours < 24) return `${hours} ч. назад`
    return date.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })
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
                <span className="text-sm font-bold text-gray-900 dark:text-white">Уведомления</span>
                {unreadCount > 0 && (
                  <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400">
                    {unreadCount} новых
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {unreadCount > 0 && (
                  <button
                    onClick={onMarkAllAsRead}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline px-2 py-1"
                  >
                    Прочитать все
                  </button>
                )}
                {notifications.length > 0 && (
                  <button
                    onClick={onClear}
                    className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 px-2 py-1"
                  >
                    Очистить
                  </button>
                )}
              </div>
            </div>

            {/* Notifications list */}
            <div className="max-h-[400px] overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                  <Bell className="w-10 h-10 opacity-20 mb-2" />
                  <p className="text-sm">Нет уведомлений</p>
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
                  {notifications.filter(n => n.type === "error").length} критических уведомлений требуют внимания
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

const statusConfig: Record<Status, { label: string; icon: React.ElementType; cls: string; dot: string }> = {
  upcoming:    { label:"Запланировано", icon:Clock,         cls:"bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",        dot:"bg-gray-400" },
  in_progress: { label:"Выполняется",  icon:Wrench,        cls:"bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",     dot:"bg-amber-500" },
  completed:   { label:"Выполнено",    icon:CheckCircle,   cls:"bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",     dot:"bg-green-500" },
  overdue:     { label:"Просрочено",   icon:AlertTriangle, cls:"bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",             dot:"bg-red-500" },
}

/* ═══════════════════════════════════════
   ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
═══════════════════════════════════════ */
function parseDate(d: string): Date {
  const [day, month, year] = d.split(".").map(Number)
  return new Date(year, month - 1, day)
}
function formatDateShort(d: Date): string {
  return d.getDate().toString().padStart(2,"0") + "." + (d.getMonth()+1).toString().padStart(2,"0")
}
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
   КОМПОНЕНТ ДИАГРАММЫ ГАНТА
═══════════════════════════════════════ */
function GanttChart({ items, rangeStart, rangeDays, onCreateOrder }: {
  items: ScheduleItem[]
  rangeStart: Date
  rangeDays: number
  onCreateOrder?: (unit: string, section: string) => void
}) {
  const today = new Date()
  const todayOffset = diffDays(rangeStart, today)
  const todayPct = (todayOffset / rangeDays) * 100

  // Заголовок с днями
  const headerDates: Date[] = []
  for (let i = 0; i <= rangeDays; i += 2) {
    headerDates.push(addDays(rangeStart, i))
  }

  // Группировка по оборудованию
  const groupedItems = items.reduce((acc, item) => {
    if (!acc[item.unit]) acc[item.unit] = []
    acc[item.unit].push(item)
    return acc
  }, {} as Record<string, ScheduleItem[]>)

  return (
    <div className="overflow-x-auto">
      <div style={{ minWidth: "1100px" }}>
        
        {/* ═══ ШАПКА ТАБЛИЦЫ ═══ */}
        <div className="flex items-end border-b-2 border-gray-300 dark:border-gray-600 pb-3 mb-4">
          {/* Колонка оборудования */}
          <div className="w-[380px] flex-shrink-0">
            <div className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-1">
              Оборудование
            </div>
            <div className="text-[10px] text-gray-400">
              Название · Тип ТО · Пробег
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
                  {['Вс','Пн','Вт','Ср','Чт','Пт','Сб'][d.getDay()]}
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
                  СЕГОДНЯ
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ═══ СТРОКИ ГРАФИКА ═══ */}
        <div className="space-y-3">
          {Object.entries(groupedItems).map(([unitName, unitItems]) => {
            const firstItem = unitItems[0]
            const isWialon = false
            const isOnline = false
            
            return (
              <div key={unitName} className="group">
                {/* Карточка оборудования */}
                <div className="flex items-stretch rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden hover:shadow-lg transition-shadow">
                  
                  {/* ═══ ЛЕВАЯ ПАНЕЛЬ: Информация об оборудовании ═══ */}
                  <div className="w-[380px] flex-shrink-0 p-4 border-r border-gray-100 dark:border-gray-800 bg-gradient-to-r from-gray-50 to-white dark:from-gray-800/50 dark:to-gray-900">
                    <div className="flex items-start gap-4">
                      
                      {/* Большая иконка статуса */}
                      <div className={`w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 ${
                        isWialon 
                          ? isOnline 
                            ? 'bg-gradient-to-br from-green-400 to-emerald-500 text-white shadow-lg shadow-green-500/30'
                            : 'bg-gray-200 dark:bg-gray-700 text-gray-400'
                          : firstItem.status === 'overdue'
                            ? 'bg-gradient-to-br from-red-400 to-red-600 text-white shadow-lg shadow-red-500/30 animate-pulse'
                            : firstItem.status === 'in_progress'
                              ? 'bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-lg shadow-amber-500/30'
                              : 'bg-gradient-to-br from-blue-400 to-blue-600 text-white shadow-lg shadow-blue-500/30'
                      }`}>
                        {isWialon ? (
                          <Gauge className="w-7 h-7" />
                        ) : firstItem.status === 'overdue' ? (
                          <AlertTriangle className="w-7 h-7" />
                        ) : firstItem.status === 'in_progress' ? (
                          <Wrench className="w-7 h-7" />
                        ) : (
                          <Clock className="w-7 h-7" />
                        )}
                      </div>
                      
                      {/* Текстовая информация */}
                      <div className="flex-1 min-w-0">
                        {/* Номер тягового агрегата - КРУПНО */}
                        <div className="flex items-center gap-2">
                          <h3 className="text-xl font-black text-gray-900 dark:text-white tracking-tight">
                            {unitName}
                          </h3>
                        </div>
                        
                        {/* Типы ТО */}
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {unitItems.map((item, idx) => {
                            const cfg = typeConfig[item.type] ?? typeConfig["ВНП"]
                            return (
                              <span 
                                key={idx}
                                style={{ backgroundColor: cfg.color }}
                                className="text-xs font-bold text-white px-2.5 py-1 rounded-lg shadow-sm"
                              >
                                {item.type}
                              </span>
                            )
                          })}
                        </div>
                        
                        {firstItem.mileage !== undefined && (
                          <div className="mt-2.5 flex items-center gap-2">
                            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-900/50">
                              <Gauge className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                              <span className="text-base font-bold text-emerald-700 dark:text-emerald-300">
                                {firstItem.mileage.toLocaleString()} км
                              </span>
                            </div>
                            {firstItem.remainingKm !== undefined && (
                              <span className={`text-sm font-bold px-2.5 py-1.5 rounded-lg ${
                                firstItem.remainingKm <= 0 
                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300'
                                  : firstItem.remainingKm < 10
                                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300'
                                    : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                              }`}>
                                {firstItem.remainingKm <= 0 
                                  ? `⚠️ −${Math.abs(firstItem.remainingKm)} км`
                                  : `↓ ${firstItem.remainingKm} км`
                                }
                              </span>
                            )}
                          </div>
                        )}
                        
                        {/* Дата для обычных нарядов */}
                        {!isWialon && (
                          <div className="mt-2 text-xs text-gray-500">
                            📅 {firstItem.startDate} · ⏱ {firstItem.durationH}ч
                          </div>
                        )}
                      </div>
                      
                      {/* Кнопка создания наряда */}
                      {onCreateOrder && (
                        <button
                          title="Открыть наряд-задание"
                          onClick={() => onCreateOrder(unitName, firstItem.depot)}
                          className="opacity-0 group-hover:opacity-100 transition-all flex-shrink-0 p-2 rounded-xl bg-blue-500 hover:bg-blue-600 text-white shadow-lg hover:shadow-xl hover:scale-105"
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
                    <div className="relative h-full flex flex-col justify-center gap-1.5 py-1">
                      {unitItems.map((item, idx) => {
                        const start = parseDate(item.startDate)
                        const days = durationDays(item.durationH)
                        const left = (diffDays(rangeStart, start) / rangeDays) * 100
                        const width = (days / rangeDays) * 100
                        const cfg = typeConfig[item.type] ?? typeConfig["ВНП"]
                        const isOver = item.status === "overdue"
                        const isIP = item.status === "in_progress"
                        const isDone = item.status === "completed"
                        
                        return (
                          <div 
                            key={idx}
                            style={{
                              left: `${Math.max(0, left)}%`,
                              width: `${Math.max(Math.min(width, 100 - Math.max(0, left)), 8)}%`,
                            }}
                            className="absolute"
                          >
                            <div
                              style={{ backgroundColor: cfg.color }}
                              className={`
                                h-10 rounded-xl flex items-center px-3 gap-2
                                shadow-lg hover:shadow-xl transition-all cursor-pointer
                                hover:scale-105 hover:z-20
                                ${isDone ? 'opacity-50' : ''}
                                ${isOver ? 'ring-2 ring-red-400 ring-offset-2 animate-pulse' : ''}
                                ${isIP ? 'ring-2 ring-white/50 ring-inset' : ''}
                              `}
                              title={`${item.unit}\n${item.type}\nДата: ${item.startDate}\n${item.mileage ? `Пробег: ${item.mileage} км` : ''}`}
                            >
                              {/* Иконка типа */}
                              {isOver && <AlertTriangle className="w-5 h-5 text-white flex-shrink-0" />}
                              {isIP && <Wrench className="w-5 h-5 text-white flex-shrink-0 animate-spin" style={{ animationDuration: '3s' }} />}
                              
                              {/* Название ТО + Номер агрегата */}
                              <div className="flex flex-col min-w-0">
                                <span className="text-sm font-black text-white drop-shadow truncate">
                                  {item.type}
                                </span>
                                <span className="text-[10px] font-semibold text-white/80 truncate">
                                  {item.unit}
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
            {/* Типы ТО */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-xs font-semibold text-gray-500 uppercase">Виды работ:</span>
              {Object.entries(typeConfig).slice(0, 6).map(([type, cfg]) => (
                <div key={type} className="flex items-center gap-1.5">
                  <div 
                    className="w-4 h-4 rounded"
                    style={{ backgroundColor: cfg.color }}
                  />
                  <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{type}</span>
                </div>
              ))}
            </div>
            
            {/* Статусы */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <div className="w-4 h-4 rounded bg-red-500 animate-pulse"/>
                <span className="text-xs text-gray-600 dark:text-gray-400">Просрочено</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-1 h-4 bg-red-500 rounded"/>
                <span className="text-xs text-gray-600 dark:text-gray-400">Сегодня</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Gauge className="w-4 h-4 text-emerald-500"/>
                <span className="text-xs text-gray-600 dark:text-gray-400">Данные графика</span>
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

function genOrderId(): string {
  const now = new Date()
  const y  = now.getFullYear()
  const mo = String(now.getMonth() + 1).padStart(2, "0")
  const d  = String(now.getDate()).padStart(2, "0")
  const h  = String(now.getHours()).padStart(2, "0")
  const mi = String(now.getMinutes()).padStart(2, "0")
  const s  = String(now.getSeconds()).padStart(2, "0")
  return `НЗ-${y}${mo}${d}-${h}${mi}${s}`
}

function QuickOrderModal({ item, onClose, sections, onOrderCreated, onNotify }: {
  item: ScheduleItem
  onClose: () => void
  sections: string[]
  onOrderCreated?: () => void
  onNotify?: (n: { type: "warning" | "error" | "success" | "info"; title: string; message: string }, uniqueKey?: string, showToast?: boolean) => void
}) {
  const [section,   setSection]   = useState(item.depot || "")
  const [priority,  setPriority]  = useState("normal")
  const [note,      setNote]      = useState("")
  const [saved,     setSaved]     = useState(false)
  const [orderId,   setOrderId]   = useState("")
  const [error,     setError]     = useState("")

  const handleSend = async () => {
    if (!section) { setError("Выберите участок для отправки наряда"); return }
    setError("")
    const id = genOrderId()
    
    const mileageInfo = item.mileage !== undefined 
      ? ` (пробег: ${item.mileage.toLocaleString()} км, до ТО: ${item.remainingKm} км)`
      : ""
    
    const row = {
      id,
      unit_type:    "locomotive",
      unit:          item.unit,
      depot:         section,
      section:       section,
      equipment:     item.unit.split(/[-\s]/)[0] ?? item.unit,
      work_type:     "Плановое",
      repair_kind:   item.type,
      status:        "pending",
      priority:      item.status === "overdue" ? "critical" : priority,
      tech:          "",
      chief:         "",
      description:   `${item.type} — плановое техническое обслуживание${mileageInfo}`,
      note:          note || "",
      created:       new Date().toLocaleDateString("ru-RU"),
      closed:        "—",
      repair_items:  [],
      date_start:    item.startDate,
      date_end:      "",
      // Сохраняем данные пробега для отслеживания цикла ТО
      mileage_at_creation: item.mileage || null,
      mileage_threshold: item.nextThreshold || null,
    }
    
    const { error: insertError } = await supabase.from("work_orders").insert(row)
    
    if (insertError) {
      console.error("Ошибка создания наряда:", insertError)
      setError("Ошибка при создании наряда")
      return
    }
    
    setOrderId(id)
    setSaved(true)
    
    // Уведомление об успешном создании — показываем toast
    if (onNotify) {
      onNotify({
        type: "success",
        title: `Наряд ${id} создан`,
        message: `${item.type} для ${item.unit} отправлен на участок ${section}`
      }, undefined, true) // showToast = true
    }
    
    // Обновляем данные чтобы ТО исчезло из графика
    if (onOrderCreated) {
      onOrderCreated()
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
              <p className="text-xs text-blue-200 font-medium">Открыть наряд-задание по графику</p>
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
              <p className="text-lg font-bold text-gray-900 dark:text-white">Наряд открыт!</p>
              <p className="text-sm text-gray-500 mt-1">
                Номер: <span className="font-mono font-bold text-blue-600">{orderId}</span>
              </p>
              <p className="text-sm text-gray-500 mt-1">
                Участок: <span className="font-semibold text-gray-700 dark:text-gray-300">{section}</span>
              </p>
              {false && (
                <div className="mt-3 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800">
                  <p className="text-xs text-emerald-700 dark:text-emerald-300">
                    <Gauge className="w-3 h-3 inline mr-1" />
                    Это ТО теперь не будет показываться в графике до завершения наряда.
                  </p>
                  {item.nextThreshold && (
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                      Следующее {item.type} запланируется при пробеге {item.nextThreshold.toLocaleString()} км
                    </p>
                  )}
                </div>
              )}
              <p className="text-xs text-gray-400 mt-2">
                Наряд появится в разделе «Запланировано» для выбранного участка.
              </p>
            </div>
            <button onClick={onClose}
              className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors">
              Готово
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
                    Данные из графика ТО
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
                    <span className="text-gray-400 text-xs block">Единица ТПС</span>
                    <p className="font-semibold text-gray-900 dark:text-white">{item.unit}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-xs block">Вид ремонта</span>
                    <p className="font-bold text-blue-600 dark:text-blue-400">{item.type}</p>
                  </div>
                  {item.mileage !== undefined && (
                    <>
                      <div>
                        <span className="text-gray-400 text-xs block">Текущий пробег</span>
                        <p className="font-bold text-emerald-600 dark:text-emerald-400">{item.mileage.toLocaleString()} км</p>
                      </div>
                      <div>
                        <span className="text-gray-400 text-xs block">До ТО осталось</span>
                        <p className={`font-bold ${
                          (item.remainingKm || 0) <= 0 
                            ? "text-red-600 dark:text-red-400" 
                            : "text-amber-600 dark:text-amber-400"
                        }`}>
                          {(item.remainingKm || 0) <= 0 
                            ? `Просрочено на ${Math.abs(item.remainingKm || 0)} км` 
                            : `${item.remainingKm} км`
                          }
                        </p>
                      </div>
                    </>
                  )}
                  <div>
                    <span className="text-gray-400 text-xs block">Дата начала</span>
                    <p className="font-medium text-gray-700 dark:text-gray-300">{item.startDate}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-xs block">Длительность</span>
                    <p className="font-medium text-gray-700 dark:text-gray-300">{item.durationH} ч</p>
                  </div>
                </div>
                {item.status === "overdue" && (
                  <div className="mt-3 flex items-center gap-2 p-2 rounded-lg bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300">
                    <AlertTriangle className="w-4 h-4" />
                    <span className="text-xs font-semibold">Требуется срочный ремонт! Пробег превысил норматив.</span>
                  </div>
                )}
              </div>

              {/* Выбор участка — обязательно */}
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                  Участок <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <select
                    value={section}
                    onChange={e => { setSection(e.target.value); setError("") }}
                    className={`${selCls} ${error ? "border-red-400 focus:ring-red-400" : ""}`}>
                    <option value="">Выберите участок...</option>
                    {sections.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
                </div>
                {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
              </div>

              {/* Приоритет */}
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">Приоритет</label>
                <div className="grid grid-cols-4 gap-2">
                  {([
                    ["low",      "Низкий",     "text-gray-600 bg-gray-100 dark:bg-gray-800"],
                    ["normal",   "Обычный",    "text-blue-700 bg-blue-100 dark:bg-blue-950"],
                    ["high",     "Высокий",    "text-amber-700 bg-amber-100 dark:bg-amber-950"],
                    ["critical", "Критич.",    "text-red-700 bg-red-100 dark:bg-red-950"],
                  ] as [string,string,string][]).map(([v,l,cls]) => (
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
                  Примечание <span className="text-gray-400 font-normal">(необязательно)</span>
                </label>
                <textarea value={note} onChange={e => setNote(e.target.value)} rows={2}
                  placeholder="Особые указания для участка..."
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </div>
            </div>

            {/* Подвал */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-400">
                Статус: <span className="font-semibold text-gray-600 dark:text-gray-300">Запланировано</span>
              </p>
              <div className="flex gap-3">
                <button onClick={onClose}
                  className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                  Отмена
                </button>
                <button onClick={handleSend}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors shadow-sm">
                  <Plus className="w-4 h-4"/> Открыть на участок
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
function dateToDdMmYyyy(isoDate: string): string {
  if (!isoDate) return ""
  const [y, m, d] = isoDate.split("T")[0].split("-")
  return [d, m, y].join(".")
}

// Конвертация строки work_orders → ScheduleItem (опционально обогащаем пробегом из ОС)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function woToSchedule(r: any, mileageByUnit?: Record<string, number>): ScheduleItem {
  const woStatus: Record<string, Status> = {
    pending:     "upcoming",
    in_progress: "in_progress",
    completed:   "completed",
  }
  const today = new Date()
  const todayStr = [
    String(today.getDate()).padStart(2,"0"),
    String(today.getMonth()+1).padStart(2,"0"),
    today.getFullYear(),
  ].join(".")
  const unit = r.unit || ""
  const mileage = mileageByUnit?.[unit] ?? mileageByUnit?.[unit.trim()]
  return {
    id:        r.id,
    unit,
    type:      r.repair_kind || r.work_type || "ТО",
    startDate: r.date_start || todayStr,
    durationH: 8,
    depot:     r.section || r.depot || "",
    tech:      r.tech || "",
    status:    woStatus[r.status] ?? "upcoming",
    note:      r.note || undefined,
    mileage:   mileage !== undefined ? mileage : undefined,
  }
}

// Плановое ТО по пробегу (maintenance_plan + актуальный пробег из ОС)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function planToSchedule(mp: any, currentMileage: number): ScheduleItem {
  const startDate = dateToDdMmYyyy(mp.scheduled_date)
  const trigger = Number(mp.trigger_mileage) || 0
  const remainingKm = trigger - currentMileage
  const status: Status = mp.status === "InProgress" ? "in_progress" : "upcoming"
  return {
    id:            `plan-${mp.id}`,
    unit:          mp.asset_name || "",
    type:          mp.maintenance_type || "ТО",
    startDate:     startDate || dateToDdMmYyyy(new Date().toISOString()),
    durationH:     8,
    depot:         "",
    tech:          "",
    status,
    mileage:       currentMileage,
    remainingKm:   remainingKm < 0 ? 0 : remainingKm,
    nextThreshold: trigger,
  }
}

// Следующий порог по интервалу (км): ближайшее следующее кратное interval_km
function nextTriggerKm(currentMileage: number, intervalKm: number): number {
  if (intervalKm <= 0) return currentMileage
  return (Math.floor(currentMileage / intervalKm) + 1) * intervalKm
}

// Плановые ТО по справочнику интервалов (maintenance_intervals) + пробег из ОС
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function intervalsToSchedule(
  assets: { id: string; name: string; mileage: string; depot: string; asset_type: string }[],
  intervals: { code: string; name: string; interval_km: number; asset_types: string[] | null; is_active: boolean }[],
  existingPlanKeys: Set<string>
): ScheduleItem[] {
  const today = new Date()
  const todayStr = [
    String(today.getDate()).padStart(2, "0"),
    String(today.getMonth() + 1).padStart(2, "0"),
    today.getFullYear(),
  ].join(".")
  const items: ScheduleItem[] = []
  for (const a of assets) {
    const mileage = parseInt(String(a.mileage || "0"), 10) || 0
    const assetTypes = (a.asset_type && [a.asset_type]) || ["locomotive", "diesel"]
    for (const iv of intervals) {
      if (!iv.is_active || !iv.interval_km) continue
      const types = iv.asset_types || ["locomotive", "diesel"]
      if (!assetTypes.some((t: string) => types.includes(t))) continue
      const nextTr = nextTriggerKm(mileage, iv.interval_km)
      const key = `${a.id}-${iv.code}-${nextTr}`
      if (existingPlanKeys.has(key)) continue
      const remainingKm = nextTr - mileage
      items.push({
        id:            `interval-${key}`,
        unit:          a.name || "",
        type:          iv.code || iv.name,
        startDate:     todayStr,
        durationH:     8,
        depot:         a.depot || "",
        tech:          "",
        status:        "upcoming",
        mileage,
        remainingKm:   remainingKm < 0 ? 0 : remainingKm,
        nextThreshold: nextTr,
      })
    }
  }
  return items
}

export default function MaintenancePage() {
  const [schedule,  setSchedule]  = useState<ScheduleItem[]>([])
  const [loading,   setLoading]   = useState(true)
  const [view, setView]           = useState<"gantt"|"table">("gantt")
  const [filter, setFilter]       = useState<Status|"all">("all")
  const [monthOffset, setMonthOffset] = useState(0)
  const [quickItem, setQuickItem] = useState<ScheduleItem|null>(null)
  const [notifications, setNotifications] = useState<ToastNotification[]>([])
  const [allNotifications, setAllNotifications] = useState<ToastNotification[]>([])
  const [initialLoadDone, setInitialLoadDone] = useState(false)
  const shownNotificationsRef = useRef<Set<string>>(new Set())
  
  // Дополнительные фильтры
  const [filterType, setFilterType] = useState<string>("all") // Тип ТО
  const [filterUnit, setFilterUnit] = useState<string>("") // Поиск по названию
  const [showFilters, setShowFilters] = useState(false)

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
    setLoading(true)
    try {
      const offset = monthOffsetParam ?? monthOffset
      const now = new Date()
      const totalMonth = now.getMonth() + offset
      const y = now.getFullYear() + Math.floor(totalMonth / 12)
      const m = ((totalMonth % 12) + 12) % 12 + 1
      const queryMonth = `${y}-${String(m).padStart(2, "0")}`

      const res = await fetch(`/api/maintenance-schedule?month=${queryMonth}`)
      if (!res.ok) throw new Error(await res.text())
      const { schedule: data } = await res.json()
      setSchedule(Array.isArray(data) ? data : [])
      setInitialLoadDone(true)
    } catch (e) {
      console.error("Ошибка загрузки ТО и ремонтов:", e)
      setSchedule([])
    } finally {
      setLoading(false)
    }
  }, [monthOffset])

  useEffect(() => { fetchSchedule(monthOffset) }, [fetchSchedule, monthOffset])

  useEffect(() => {
    const channel = supabase
      .channel("maintenance_sync")
      .on("postgres_changes", { event: "*", schema: "public", table: "work_orders" }, () => fetchSchedule())
      .on("postgres_changes", { event: "*", schema: "public", table: "maintenance_plan" }, () => fetchSchedule())
      .on("postgres_changes", { event: "*", schema: "public", table: "fixed_assets" }, () => fetchSchedule())
      .on("postgres_changes", { event: "*", schema: "public", table: "maintenance_intervals" }, () => fetchSchedule())
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [fetchSchedule])

  // Диапазон: текущий месяц
  const now         = new Date()
  const today       = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const rangeStart  = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1)
  const rangeEnd    = new Date(now.getFullYear(), now.getMonth() + monthOffset + 1, 0)
  const rangeDays   = diffDays(rangeStart, rangeEnd) + 1

  const monthNames  = ["Январь","Февраль","Март","Апрель","Май","Июнь",
                       "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
  const monthLabel  = monthNames[rangeStart.getMonth()] + " " + rangeStart.getFullYear()

  // График приходит с сервера с уже рассчитанными датами
  const allSchedule = schedule

  const handleCreateOrder = (unit: string, _section: string) => {
    const found = allSchedule.find((s) => s.unit === unit)
    if (found) setQuickItem(found)
  }

  // Участки из справочника (БД)
  const { sections: sectionsFromDb } = useSections()
  const qSections = sectionsFromDb.length > 0 ? sectionsFromDb : [...new Set(schedule.map(s => s.depot).filter(Boolean))].sort()

  // Уникальные типы ТО для фильтра
  const uniqueTypes = [...new Set(allSchedule.map(s => s.type))].sort()
  
  // Уникальные названия оборудования для фильтра
  const uniqueUnits = [...new Set(allSchedule.map(s => s.unit))].sort()

  // Фильтрация — показываем элементы, пересекающиеся с диапазоном
  const visible = allSchedule.filter(item => {
    if (!item.startDate) return false
    try {
      const s = parseDate(item.startDate)
      const e = addDays(s, durationDays(item.durationH))
      const inRange = s <= rangeEnd && e >= rangeStart
      
      // Фильтр по статусу
      const statusMatch = filter === "all" || item.status === filter
      
      // Фильтр по типу ТО
      const typeMatch = filterType === "all" || item.type === filterType
      
      // Фильтр по названию оборудования (поиск)
      const unitMatch = !filterUnit || item.unit.toLowerCase().includes(filterUnit.toLowerCase())
      
      return inRange && statusMatch && typeMatch && unitMatch
    } catch { return false }
  })

  const counts = {
    all:         allSchedule.length,
    upcoming:    allSchedule.filter(s => s.status === "upcoming").length,
    in_progress: allSchedule.filter(s => s.status === "in_progress").length,
    completed:   allSchedule.filter(s => s.status === "completed").length,
    overdue:     allSchedule.filter(s => s.status === "overdue").length,
  }

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-400 text-sm gap-3">
      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
      Загрузка графика...
    </div>
  )

  return (
    <div className="p-8 space-y-6">
      <ToastContainer notifications={notifications} onDismiss={dismissNotification} />
      
      {quickItem && (
        <QuickOrderModal 
          item={quickItem} 
          onClose={() => setQuickItem(null)} 
          sections={qSections}
          onOrderCreated={fetchSchedule}
          onNotify={addNotification}
        />
      )}

      {/* Заголовок */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">ТО и ремонты</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            График ТО и ремонтов
          </p>
        </div>
        <div className="flex items-center gap-3">
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
              <BarChart3 className="w-4 h-4"/> Диаграмма Ганта
            </button>
            <button onClick={() => setView("table")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                view==="table" ? "bg-white dark:bg-gray-900 text-blue-600 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}>
              <List className="w-4 h-4"/> Список
            </button>
          </div>
        </div>
      </div>

      {/* ═══ ПАНЕЛЬ ФИЛЬТРОВ ═══ */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {/* Кнопка раскрытия фильтров */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              (filterType !== "all" || filterUnit || filter !== "all")
                ? "bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400"
                : "bg-gray-100 dark:bg-gray-800 text-gray-500"
            }`}>
              <Filter className="w-4 h-4" />
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-white">Фильтры</span>
            {(filterType !== "all" || filterUnit || filter !== "all") && (
              <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                Активны
              </span>
            )}
          </div>
          <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${showFilters ? "rotate-180" : ""}`} />
        </button>

        {/* Раскрывающаяся панель фильтров */}
        {showFilters && (
          <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4">
              
              {/* Поиск по названию */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  Поиск оборудования
                </label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={filterUnit}
                    onChange={(e) => setFilterUnit(e.target.value)}
                    placeholder="Введите номер..."
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Фильтр по типу ТО */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  Тип ТО
                </label>
                <select
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent appearance-none cursor-pointer"
                >
                  <option value="all">Все типы</option>
                  {uniqueTypes.map(type => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>

              {/* Фильтр по статусу */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                  Статус
                </label>
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value as Status | "all")}
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent appearance-none cursor-pointer"
                >
                  <option value="all">Все статусы</option>
                  <option value="overdue">🔴 Просрочено ({counts.overdue})</option>
                  <option value="in_progress">🟡 Выполняется ({counts.in_progress})</option>
                  <option value="upcoming">⚪ Запланировано ({counts.upcoming})</option>
                  <option value="completed">🟢 Выполнено ({counts.completed})</option>
                </select>
              </div>

              {/* Кнопка сброса */}
              <div className="flex items-end">
                <button
                  onClick={() => {
                    setFilterType("all")
                    setFilterUnit("")
                    setFilter("all")
                  }}
                  disabled={filterType === "all" && !filterUnit && filter === "all"}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <RotateCcw className="w-4 h-4" />
                  Сбросить
                </button>
              </div>
            </div>

            {/* Быстрые фильтры по типу ТО */}
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-gray-400 mr-2">Быстрый выбор:</span>
                <button
                  onClick={() => setFilterType("all")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    filterType === "all"
                      ? "bg-blue-500 text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  Все
                </button>
                {uniqueTypes.map(type => {
                  const cfg = typeConfig[type] ?? typeConfig["ВНП"]
                  const count = allSchedule.filter(s => s.type === type).length
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
                      {type} ({count})
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Результаты фильтрации */}
            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-gray-500 dark:text-gray-400">
                Найдено: <span className="font-bold text-gray-900 dark:text-white">{visible.length}</span> из {allSchedule.length}
              </span>
              {visible.length === 0 && (filterType !== "all" || filterUnit || filter !== "all") && (
                <span className="text-amber-600 dark:text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" />
                  Нет результатов по заданным фильтрам
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* KPI карточки */}
      <div className="grid grid-cols-4 gap-4">
        {(["upcoming","in_progress","completed","overdue"] as Status[]).map(s => {
          const cfg = statusConfig[s]
          const count = counts[s]
          const pct = Math.round((count / counts.all) * 100)
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
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{cfg.label}</p>
              <div className="mt-2 h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                <div className={`h-full rounded-full transition-all ${cfg.cls.split(" ")[0].replace("bg-","bg-").replace("-100","-500").replace("-950","-500")}`}
                  style={{ width: `${pct}%` }}/>
              </div>
              <p className="text-[10px] text-gray-400 mt-1">{pct}% от всех</p>
            </button>
          )
        })}
      </div>

      {/* Легенда типов ремонта */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs text-gray-400 mr-1">Виды работ:</span>
        {Object.entries(typeConfig).map(([type, cfg]) => (
          <span key={type}
            className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border ${cfg.text} ${cfg.border} bg-white dark:bg-gray-900`}>
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: cfg.color }}/>
            {type}
          </span>
        ))}
      </div>

      {/* ДИАГРАММА ГАНТА */}
      {view === "gantt" && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
          {/* Шапка с навигацией по месяцам */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
            <div className="flex items-center gap-3">
              <Calendar className="w-4 h-4 text-blue-500"/>
              <h2 className="text-sm font-bold text-gray-900 dark:text-white">{monthLabel}</h2>
              <span className="text-xs text-gray-400">· {visible.length} позиций</span>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => setMonthOffset(o => o-1)}
                className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                <ChevronLeft className="w-4 h-4 text-gray-500"/>
              </button>
              <button onClick={() => setMonthOffset(0)}
                className="px-3 py-1 text-xs font-medium rounded-lg bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 hover:bg-blue-200 transition-colors">
                Сегодня
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
                <p className="text-sm font-medium">Нет работ в этом периоде</p>
                <p className="text-xs mt-1">Измените фильтр или перейдите к другому месяцу</p>
              </div>
            ) : (
              <GanttChart items={visible} rangeStart={rangeStart} rangeDays={rangeDays} onCreateOrder={handleCreateOrder}/>
            )}
          </div>
        </div>
      )}

      {/* ТАБЛИЧНЫЙ ВИД */}
      {view === "table" && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex items-center gap-3">
            <List className="w-4 h-4 text-blue-500"/>
            <h2 className="text-sm font-bold text-gray-900 dark:text-white">Список работ</h2>
            <span className="text-xs text-gray-400">· {visible.length} позиций</span>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-800">
                {["Ед.ТПС","Пробег","Вид ТО","До ТО","Дата","Статус","Источник","Действие"].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {visible.length === 0 && (
                <tr><td colSpan={8} className="px-5 py-10 text-center text-sm text-gray-400">Нет данных</td></tr>
              )}
              {visible.map(item => {
                const st  = statusConfig[item.status]
                const cfg = typeConfig[item.type] ?? typeConfig["ВНП"]
                return (
                  <tr key={item.id} className={`hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group ${
                    item.status === "overdue" ? "bg-red-50/50 dark:bg-red-950/20" : ""
                  }`}>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        {false && (
                          false ? (
                            <Wifi className="w-3 h-3 text-green-500" />
                          ) : (
                            <WifiOff className="w-3 h-3 text-gray-400" />
                          )
                        )}
                        <span className="text-sm font-medium text-gray-900 dark:text-white">{item.unit}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      {item.mileage !== undefined ? (
                        <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                          {item.mileage.toLocaleString()} км
                        </span>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded border ${cfg.text} ${cfg.border} bg-white dark:bg-gray-900`}>
                        {item.type}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      {item.remainingKm !== undefined ? (
                        <span className={`text-sm font-semibold ${
                          item.remainingKm <= 0 
                            ? "text-red-600 dark:text-red-400" 
                            : item.remainingKm < 10 
                              ? "text-amber-600 dark:text-amber-400"
                              : "text-gray-600 dark:text-gray-300"
                        }`}>
                          {item.remainingKm <= 0 ? `−${Math.abs(item.remainingKm)}` : item.remainingKm} км
                        </span>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600 dark:text-gray-300">{item.startDate}</td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${st.cls}`}>
                        <st.icon className="w-3 h-3"/>
                        {st.label}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      {false ? (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                          <Gauge className="w-3 h-3" />
                          —
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400">Наряд</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <button
                        onClick={() => handleCreateOrder(item.unit, item.depot)}
                        className={`flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition-colors whitespace-nowrap border ${
                          item.status === "overdue"
                            ? "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-950 border-red-200 dark:border-red-800"
                            : "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 hover:bg-blue-100 dark:hover:bg-blue-950 border-blue-200 dark:border-blue-800"
                        }`}>
                        <Plus className="w-3 h-3"/> 
                        Наряд
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Подсказка */}
      <div className="flex items-start gap-2 text-xs text-gray-400 bg-emerald-50 dark:bg-emerald-950/30 rounded-xl px-4 py-3 border border-emerald-200 dark:border-emerald-700">
        <Gauge className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-emerald-500"/>
        <span>
          <strong className="text-emerald-700 dark:text-emerald-400">График ТО:</strong>{" "}
          Данные о пробеге поступают в реальном времени. При приближении к порогу ТО система автоматически показывает уведомление.
          Нажмите «Открыть наряд» чтобы создать наряд-задание на основе пробега.
          <a href="/dashboard/directories/maintenance-intervals" className="ml-1 text-emerald-600 hover:underline">
            Настроить интервалы ТО →
          </a>
        </span>
      </div>

    </div>
  )
}
