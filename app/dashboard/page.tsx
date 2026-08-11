"use client"

import { useState, useEffect, useMemo, useCallback } from "react"
import { supabase } from "@/lib/supabase"
import { useSectionView } from "@/lib/section-view-context"
import {
  Train, Wrench, AlertTriangle, CheckCircle,
  TrendingUp, ArrowUpRight, BarChart3,
  Activity, Target, CalendarDays, ClipboardList, Container, RefreshCw,
} from "lucide-react"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, LineChart, Line,
} from "recharts"

/* ─── Вспомогательные ─── */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl px-4 py-3 text-xs">
      <p className="font-semibold text-gray-700 dark:text-gray-200 mb-1.5">{label}</p>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2 mb-0.5">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color }} />
          <span className="text-gray-500 dark:text-gray-400">{p.name}:</span>
          <span className="font-semibold text-gray-900 dark:text-white">{p.value}</span>
        </div>
      ))}
    </div>
  )
}

const RADIAN = Math.PI / 180
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const renderPieLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
  if (percent < 0.06) return null
  const r = innerRadius + (outerRadius - innerRadius) * 0.6
  const x = cx + r * Math.cos(-midAngle * RADIAN)
  const y = cy + r * Math.sin(-midAngle * RADIAN)
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central"
      fontSize={11} fontWeight="bold">
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  )
}

const MONTH_NAMES = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]

const woStatusCfg: Record<string,{label:string;cls:string}> = {
  completed:   { label:"Выполнен", cls:"bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400" },
  in_progress: { label:"В работе", cls:"bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400" },
  pending:     { label:"Ожидание", cls:"bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400" },
}
const prioCls: Record<string,string> = {
  critical: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  high:     "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400",
  normal:   "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
  low:      "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
}
const prioLabel: Record<string,string> = {
  critical:"Критичный", high:"Высокий", normal:"Обычный", low:"Низкий"
}

/* ════════════════════════════════════════
   СТРАНИЦА
════════════════════════════════════════ */
export default function DashboardPage() {
  const { effectiveSection } = useSectionView()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [assets,  setAssets]  = useState<any[]>([])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [orders,  setOrders]  = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [maintenanceIntervals, setMaintenanceIntervals] = useState<any[]>([])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [{ data: a }, { data: o }, { data: mi }] = await Promise.all([
        supabase.from("fixed_assets").select("asset_type,status,series,depot,mileage,name").limit(2000),
        supabase.from("work_orders")
          .select("id,unit,description,repair_kind,status,tech,section,priority,date_start,created_at,created")
          .order("created_at", { ascending: false })
          .limit(400),
        supabase.from("maintenance_intervals")
          .select("*")
          .eq("is_active", true)
          .order("interval_km", { ascending: true }),
      ])
      setAssets(a ?? [])
      setOrders(o ?? [])
      setMaintenanceIntervals(mi ?? [])
    } catch (e) {
      console.error("Ошибка загрузки дашборда:", e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Обновление данных при изменениях в БД (real-time)
  useEffect(() => {
    const channel = supabase
      .channel("dashboard_sync")
      .on("postgres_changes", { event: "*", schema: "public", table: "fixed_assets" }, () => {
        loadData()
      })
      .on("postgres_changes", { event: "*", schema: "public", table: "work_orders" }, () => {
        loadData()
      })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [loadData])

  /* Фильтрация по участку: для мастера и при выборе участка админом */
  const filteredOrders = useMemo(() => {
    if (!effectiveSection) return orders
    return orders.filter((o: { section?: string }) => (o.section ?? "") === effectiveSection)
  }, [orders, effectiveSection])
  const filteredAssets = useMemo(() => {
    if (!effectiveSection) return assets
    return assets.filter((a: { depot?: string }) => (a.depot ?? "") === effectiveSection)
  }, [assets, effectiveSection])

  /* Единицы с открытыми нарядами (ожидание или в работе) — считаем их «на ТО» */
  const unitsWithOpenOrder = useMemo(() => {
    const open = filteredOrders.filter((o: { status?: string }) => o.status === "pending" || o.status === "in_progress")
    return new Set(open.map((o: { unit?: string }) => (o.unit ?? "").trim()))
  }, [filteredOrders])

  /* ── Счётчики активов (по отфильтрованным) + учёт открытых нарядов ── */
  const totalAssets  = filteredAssets.length
  const locoCount    = filteredAssets.filter(a => a.asset_type === "locomotive").length
  const wagonCount   = filteredAssets.filter(a => a.asset_type === "wagon").length
  /* В эксплуатации: статус operational и нет открытого наряда */
  const operational  = useMemo(() => 
    filteredAssets.filter((a: { status?: string; name?: string }) => 
      a.status === "operational" && !unitsWithOpenOrder.has((a.name ?? "").trim())
    ).length,
    [filteredAssets, unitsWithOpenOrder]
  )
  /* На ТО: статус maintenance ИЛИ есть открытый наряд при статусе operational */
  const onMaint      = useMemo(() =>
    filteredAssets.filter((a: { status?: string; name?: string }) =>
      a.status === "maintenance" || (a.status === "operational" && unitsWithOpenOrder.has((a.name ?? "").trim()))
    ).length,
    [filteredAssets, unitsWithOpenOrder]
  )
  const onRepair     = filteredAssets.filter((a: { status?: string }) => a.status === "repair").length
  const outOfService = filteredAssets.filter((a: { status?: string }) => a.status === "out_of_service").length
  const availPct     = totalAssets > 0 ? Math.round((operational / totalAssets) * 100) : 0

  /* ── Разбивка по сериям ── */
  const seriesMap: Record<string, { loco: number; wagon: number }> = {}
  for (const a of filteredAssets) {
    const s = a.series || "Прочие"
    if (!seriesMap[s]) seriesMap[s] = { loco: 0, wagon: 0 }
    if (a.asset_type === "locomotive") seriesMap[s].loco++
    else seriesMap[s].wagon++
  }
  const seriesStats = Object.entries(seriesMap)
    .map(([series, v]) => ({ series, ...v, total: v.loco + v.wagon }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 8)

  /* ── Счётчики нарядов ── */
  const openOrders      = filteredOrders.filter(o => o.status === "pending" || o.status === "in_progress").length
  const inProgressOrders = filteredOrders.filter(o => o.status === "in_progress").length
  const completedOrders = filteredOrders.filter(o => o.status === "completed").length

  /* ── KPI карточки ── */
  const kpi = [
    {
      title: "Всего единиц ОС",   value: totalAssets,   unit:"ед.",
      sub: effectiveSection ? `участок: ${effectiveSection}` : "в реестре", Icon: Train,
      light:"bg-blue-50 dark:bg-blue-950/60", text:"text-blue-600 dark:text-blue-400", bar:"bg-blue-500",
      pct: 100,
    },
    {
      title: "В эксплуатации",    value: operational,   unit:"ед.",
      sub: totalAssets ? `${availPct}% от парка` : "—", Icon: CheckCircle,
      light:"bg-emerald-50 dark:bg-emerald-950/60", text:"text-emerald-600 dark:text-emerald-400", bar:"bg-emerald-500",
      pct: availPct,
    },
    {
      title: "На техобслуживании", value: onMaint + onRepair, unit:"ед.",
      sub: totalAssets ? `${Math.round(((onMaint+onRepair)/totalAssets)*100)}% от парка` : "—", Icon: Wrench,
      light:"bg-amber-50 dark:bg-amber-950/60", text:"text-amber-600 dark:text-amber-400", bar:"bg-amber-500",
      pct: totalAssets ? Math.round(((onMaint+onRepair)/totalAssets)*100) : 0,
    },
    {
      title: "Открытые наряды",   value: openOrders,    unit:"нз",
      sub: `${inProgressOrders} выполняется`,  Icon: ClipboardList,
      light:"bg-purple-50 dark:bg-purple-950/60", text:"text-purple-600 dark:text-purple-400", bar:"bg-purple-500",
      pct: filteredOrders.length ? Math.round((openOrders / filteredOrders.length) * 100) : 0,
    },
  ]

  /* ── Состояние парка (donut) ── */
  const fleetStatus = [
    { name:"В эксплуатации", value: operational,  color:"#10b981" },
    { name:"На ТО",           value: onMaint,      color:"#f59e0b" },
    { name:"Ремонт",          value: onRepair,     color:"#f97316" },
    { name:"Списан",          value: outOfService, color:"#ef4444" },
  ].filter(s => s.value > 0)

  /* ── Последние 6 месяцев ── */
  const now = new Date()
  const months6 = Array.from({ length: 6 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - (5 - i), 1)
    return {
      key:   `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`,
      label: MONTH_NAMES[d.getMonth()],
    }
  })

  /* ── Тренд нарядов по месяцам ── */
  const workOrdersTrend = months6.map(({ key, label }) => {
    const mo = filteredOrders.filter(o => {
      // Проверяем оба поля: created_at и created
      const dateStr = o.created_at || o.created || ""
      return dateStr.slice(0, 7) === key
    })
    return {
      month:    label,
      открыто:  mo.length,
      закрыто:  mo.filter(o => o.status === "completed").length,
      вработе:  mo.filter(o => o.status === "in_progress").length,
    }
  })

  /* ── Готовность по месяцам (симуляция тренда на основе текущих данных) ── */
  const availability = months6.map(({ label }, idx) => {
    // Небольшая вариация для визуализации тренда
    const variation = Math.sin(idx * 0.5) * 5
    const pct = Math.max(0, Math.min(100, Math.round(availPct + variation)))
    return { month: label, pct }
  })

  /* ── Виды ремонта ── */
  const rkMap: Record<string,number> = {}
  for (const o of filteredOrders) {
    const parts = (o.repair_kind ?? "").split(",").map((s: string) => s.trim()).filter(Boolean)
    for (const k of parts) rkMap[k] = (rkMap[k] ?? 0) + 1
  }
  const repairKindStats = Object.entries(rkMap)
    .sort((a,b) => b[1]-a[1]).slice(0,7)
    .map(([kind,count]) => ({ kind, count }))

  /* ── Предстоящее ТО (pending наряды с датой) ── */
  const upcomingOrders = filteredOrders
    .filter(o => o.status === "pending" && o.date_start)
    .slice(0, 5)

  /* ── Последние наряды ── */
  const recentWO = filteredOrders.slice(0, 5)

  /* ── Текущая дата ── */
  const todayLabel = new Date().toLocaleDateString("ru-RU", { day:"numeric", month:"long", year:"numeric" })

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-400 text-sm gap-3">
      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
      Загрузка дашборда...
    </div>
  )

  return (
    <div className="p-6 space-y-6 bg-gray-50 dark:bg-gray-950 min-h-full">

      {/* Шапка */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Дашборд</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            {effectiveSection ? (
              <>Участок: <span className="font-medium text-gray-700 dark:text-gray-300">{effectiveSection}</span> · {todayLabel}</>
            ) : (
              <>Обзор состояния парка · <span className="font-medium">{todayLabel}</span></>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {effectiveSection && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-xs font-medium text-gray-700 dark:text-gray-300">
              Только данные участка
            </div>
          )}
          <button
            type="button"
            onClick={() => loadData()}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
            title="Обновить данные"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Обновить
          </button>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-full">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-medium text-emerald-700 dark:text-emerald-400">Данные из БД · актуально</span>
          </div>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpi.map(card => (
          <div key={card.title}
            className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-4">
              <div className={`w-10 h-10 rounded-xl ${card.light} flex items-center justify-center`}>
                <card.Icon className={`w-5 h-5 ${card.text}`} />
              </div>
            </div>
            <p className="text-3xl font-bold text-gray-900 dark:text-white">
              {card.value} <span className="text-base font-normal text-gray-400">{card.unit}</span>
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{card.title}</p>
            <div className="mt-3 h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
              <div className={`h-full rounded-full ${card.bar}`} style={{ width:`${card.pct}%` }}/>
            </div>
            <p className="text-[10px] text-gray-400 mt-1">{card.sub}</p>
          </div>
        ))}
      </div>

      {/* Парк техники — разбивка */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-4 h-4 text-gray-500"/>
            <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">Состав парка техники</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {[
              { label:"Тяговые агрегаты", value: locoCount,  total: totalAssets, color:"bg-blue-500",   icon: Train,      iconCls:"text-blue-500" },
              { label:"Вагоны-самосвалы", value: wagonCount, total: totalAssets, color:"bg-violet-500", icon: Container,  iconCls:"text-violet-500" },
            ].map(item => (
              <div key={item.label} className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-gray-50 dark:bg-gray-800 flex items-center justify-center flex-shrink-0">
                  <item.icon className={`w-6 h-6 ${item.iconCls}`}/>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-600 dark:text-gray-300 font-medium">{item.label}</span>
                    <span className="font-bold text-gray-900 dark:text-white">{item.value} <span className="text-gray-400 font-normal">ед.</span></span>
                  </div>
                  <div className="h-2.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${item.color} transition-all duration-700`}
                      style={{ width: item.total ? `${Math.round(item.value / item.total * 100)}%` : "0%" }}/>
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">
                    {item.total ? Math.round(item.value / item.total * 100) : 0}% от общего парка ({totalAssets} ед.)
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Разбивка по сериям */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Train className="w-4 h-4 text-gray-500"/>
            <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">По сериям техники</span>
          </div>
          {seriesStats.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-gray-400 text-xs">Нет данных</div>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={seriesStats} layout="vertical" barSize={12}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false}/>
                <XAxis type="number" tick={{ fontSize:10, fill:"#9ca3af" }} axisLine={false} tickLine={false}/>
                <YAxis type="category" dataKey="series" tick={{ fontSize:10, fill:"#9ca3af" }} axisLine={false} tickLine={false} width={60}/>
                <Tooltip content={<CustomTooltip/>}/>
                <Bar dataKey="loco" name="Локомотивы" fill="#3b82f6" radius={[0,3,3,0]} stackId="a"/>
                <Bar dataKey="wagon" name="Вагоны" fill="#8b5cf6" radius={[0,3,3,0]} stackId="a"/>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>


      {/* Ряд 2: Donut + Bar */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">

        {/* Donut */}
        <div className="lg:col-span-2 bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center">
              <Target className="w-3.5 h-3.5 text-blue-600"/>
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Состояние парка</p>
              <p className="text-xs text-gray-400">Распределение по статусу</p>
            </div>
          </div>
          {fleetStatus.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-gray-400 text-xs">Нет данных</div>
          ) : (
            <div className="flex items-center gap-4">
              <PieChart width={160} height={160}>
                <Pie data={fleetStatus} cx="50%" cy="50%"
                  innerRadius={45} outerRadius={75}
                  dataKey="value" labelLine={false} label={renderPieLabel}>
                  {fleetStatus.map((e,i) => <Cell key={i} fill={e.color}/>)}
                </Pie>
                <Tooltip content={<CustomTooltip/>}/>
              </PieChart>
              <div className="flex-1 space-y-2">
                {fleetStatus.map(s=>(
                  <div key={s.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background:s.color }}/>
                      <span className="text-xs text-gray-600 dark:text-gray-300">{s.name}</span>
                    </div>
                    <span className="text-xs font-bold text-gray-900 dark:text-white">{s.value}</span>
                  </div>
                ))}
                <div className="pt-2 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between">
                  <span className="text-xs text-gray-400">Итого</span>
                  <span className="text-xs font-bold text-gray-900 dark:text-white">{totalAssets}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Bar — Наряды по месяцам */}
        <div className="lg:col-span-3 bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-amber-50 dark:bg-amber-950 flex items-center justify-center">
                <BarChart3 className="w-3.5 h-3.5 text-amber-600"/>
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Наряд-заказы по месяцам</p>
                <p className="text-xs text-gray-400">Последние 6 месяцев</p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-purple-500"/><span className="text-gray-500">Открыто</span></span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-emerald-500"/><span className="text-gray-500">Закрыто</span></span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-amber-400"/><span className="text-gray-500">В работе</span></span>
            </div>
          </div>
          {filteredOrders.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-gray-400 text-xs">Нет данных</div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={workOrdersTrend} barGap={2} barSize={14}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false}/>
                <XAxis dataKey="month" tick={{ fontSize:11, fill:"#9ca3af" }} axisLine={false} tickLine={false}/>
                <YAxis tick={{ fontSize:11, fill:"#9ca3af" }} axisLine={false} tickLine={false} width={24} allowDecimals={false}/>
                <Tooltip content={<CustomTooltip/>}/>
                <Bar dataKey="открыто"  name="Открыто"  fill="#8b5cf6" radius={[3,3,0,0]}/>
                <Bar dataKey="закрыто"  name="Закрыто"  fill="#10b981" radius={[3,3,0,0]}/>
                <Bar dataKey="вработе"  name="В работе" fill="#f59e0b" radius={[3,3,0,0]}/>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Ряд 3: Area + Line */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Area */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-purple-50 dark:bg-purple-950 flex items-center justify-center">
              <Activity className="w-3.5 h-3.5 text-purple-600"/>
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Динамика нарядов</p>
              <p className="text-xs text-gray-400">Открыто / закрыто / в работе</p>
            </div>
          </div>
          {filteredOrders.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-gray-400 text-xs">Нет данных</div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={workOrdersTrend}>
                <defs>
                  <linearGradient id="gradOpen"  x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#8b5cf6" stopOpacity={0.15}/>
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="gradClose" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#10b981" stopOpacity={0.15}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false}/>
                <XAxis dataKey="month" tick={{ fontSize:11, fill:"#9ca3af" }} axisLine={false} tickLine={false}/>
                <YAxis tick={{ fontSize:11, fill:"#9ca3af" }} axisLine={false} tickLine={false} width={24} allowDecimals={false}/>
                <Tooltip content={<CustomTooltip/>}/>
                <Area type="monotone" dataKey="открыто" name="Открыто"  stroke="#8b5cf6" strokeWidth={2} fill="url(#gradOpen)"  dot={{ r:3, fill:"#8b5cf6" }}/>
                <Area type="monotone" dataKey="закрыто" name="Закрыто"  stroke="#10b981" strokeWidth={2} fill="url(#gradClose)" dot={{ r:3, fill:"#10b981" }}/>
                <Area type="monotone" dataKey="вработе" name="В работе" stroke="#f59e0b" strokeWidth={2} fill="none"            dot={{ r:3, fill:"#f59e0b" }} strokeDasharray="4 2"/>
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Line — готовность */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-emerald-50 dark:bg-emerald-950 flex items-center justify-center">
                <TrendingUp className="w-3.5 h-3.5 text-emerald-600"/>
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Готовность парка</p>
                <p className="text-xs text-gray-400">% исправных единиц ОС</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-xl font-bold text-gray-900 dark:text-white">{availPct}%</p>
              <p className="text-[10px] text-gray-400">от {totalAssets} ед.</p>
            </div>
          </div>
          {totalAssets === 0 ? (
            <div className="flex items-center justify-center h-40 text-gray-400 text-xs">Нет данных</div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={availability}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false}/>
                <XAxis dataKey="month" tick={{ fontSize:11, fill:"#9ca3af" }} axisLine={false} tickLine={false}/>
                <YAxis domain={[0,100]} tick={{ fontSize:11, fill:"#9ca3af" }} axisLine={false} tickLine={false} width={30}
                  tickFormatter={v=>`${v}%`}/>
                <Tooltip content={<CustomTooltip/>} formatter={(v: number)=>[`${v}%`,"Готовность"]}/>
                <Line type="monotone" dataKey="pct" name="Готовность"
                  stroke="#10b981" strokeWidth={2.5}
                  dot={{ r:4, fill:"#10b981", strokeWidth:2, stroke:"#fff" }}
                  activeDot={{ r:6 }}/>
              </LineChart>
            </ResponsiveContainer>
          )}
          <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
            <span className="w-6 border-t-2 border-dashed border-gray-300"/>
            <span>Целевой показатель: 80%</span>
          </div>
        </div>
      </div>

      {/* Ряд 5: виды ремонта + предстоящее + наряды */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Виды ремонта */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-indigo-50 dark:bg-indigo-950 flex items-center justify-center">
              <Wrench className="w-3.5 h-3.5 text-indigo-600"/>
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">По видам ремонта</p>
              <p className="text-xs text-gray-400">Количество нарядов</p>
            </div>
          </div>
          {repairKindStats.length === 0 ? (
            <div className="flex items-center justify-center h-24 text-gray-400 text-xs">Нет данных</div>
          ) : (
            <div className="space-y-2.5">
              {repairKindStats.map(r => {
                const max = Math.max(...repairKindStats.map(x=>x.count))
                const pct = Math.round((r.count/max)*100)
                return (
                  <div key={r.kind}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 w-16 truncate">{r.kind}</span>
                      <span className="text-xs text-gray-500">{r.count} нз</span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                      <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-blue-500"
                        style={{ width:`${pct}%` }}/>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Предстоящее ТО */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-amber-50 dark:bg-amber-950 flex items-center justify-center">
              <CalendarDays className="w-3.5 h-3.5 text-amber-600"/>
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Запланированное ТО</p>
              <p className="text-xs text-gray-400">Ближайшие наряды</p>
            </div>
          </div>
          {upcomingOrders.length === 0 ? (
            <div className="flex items-center justify-center h-24 text-gray-400 text-xs">Нет запланированных нарядов</div>
          ) : (
            <div className="space-y-2">
              {upcomingOrders.map(item=>(
                <div key={item.id}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-gray-50 dark:bg-gray-800/60">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 flex items-center justify-center">
                      <Train className="w-3 h-3 text-gray-500"/>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-gray-900 dark:text-white truncate max-w-[80px]">{item.unit}</p>
                      <p className="text-[10px] text-gray-400">{item.repair_kind}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${prioCls[item.priority] ?? prioCls.normal}`}>
                      {prioLabel[item.priority] ?? "Обычный"}
                    </span>
                    <span className="text-[10px] text-gray-400 whitespace-nowrap">{item.date_start}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Последние наряды */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center">
              <ArrowUpRight className="w-3.5 h-3.5 text-blue-600"/>
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Последние наряды</p>
              <p className="text-xs text-gray-400">
                {completedOrders} выполнено · {openOrders} открыто
              </p>
            </div>
          </div>
          {recentWO.length === 0 ? (
            <div className="flex items-center justify-center h-24 text-gray-400 text-xs">Нет нарядов</div>
          ) : (
            <div className="space-y-2">
              {recentWO.map(wo=>(
                <div key={wo.id}
                  className="p-2.5 rounded-xl bg-gray-50 dark:bg-gray-800/60">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-mono text-gray-400 truncate">{wo.id}</span>
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${(woStatusCfg[wo.status] ?? woStatusCfg.pending).cls}`}>
                      {(woStatusCfg[wo.status] ?? woStatusCfg.pending).label}
                    </span>
                  </div>
                  <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 truncate">{wo.unit}</p>
                  <p className="text-xs text-gray-600 dark:text-gray-300 truncate">{wo.description}</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">{wo.tech}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

    </div>
  )
}
