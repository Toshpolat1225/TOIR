"use client"

import { useState, useEffect, useCallback, Suspense } from "react"
import { supabase } from "@/lib/supabase"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell, AreaChart, Area,
  ComposedChart, Scatter
} from "recharts"
import {
  TrendingUp, TrendingDown, DollarSign, AlertTriangle,
  Activity, Gauge, Package, Wrench, Calendar, RefreshCw,
  ChevronDown, BarChart3, PieChartIcon, LineChartIcon,
  Brain, Shield, Bell, Cpu, Zap, HeartPulse, CheckCircle, XCircle,
  Loader2
} from "lucide-react"
import { Button } from "@/components/ui/button"

// Скелетон для карточек
function KpiSkeleton() {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 shadow-sm animate-pulse">
      <div className="flex items-start justify-between">
        <div className="flex-1 space-y-3">
          <div className="h-3 w-20 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="h-7 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="h-2 w-16 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
        <div className="w-11 h-11 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
    </div>
  )
}

// Скелетон для графиков
function ChartSkeleton({ height = 300 }: { height?: number }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
      <div className="animate-pulse">
        <div className="flex items-center justify-between mb-6">
          <div className="space-y-2">
            <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
            <div className="h-3 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
          </div>
          <div className="w-5 h-5 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
        <div className="flex items-end gap-2" style={{ height }}>
          {[40, 65, 45, 80, 55, 70, 50].map((h, i) => (
            <div key={i} className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-t" style={{ height: `${h}%` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

// Скелетон для AI секции
function AiSectionSkeleton() {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm animate-pulse">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        <div className="space-y-1">
          <div className="h-4 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="h-2 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-16 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        ))}
      </div>
    </div>
  )
}

// Цвета для графиков
const COLORS = {
  primary: "#3b82f6",
  success: "#22c55e", 
  warning: "#f59e0b",
  danger: "#ef4444",
  purple: "#8b5cf6",
  cyan: "#06b6d4",
  pink: "#ec4899",
  sections: ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
}

// Типы данных
type SectionEfficiency = {
  section: string
  section_id: string
  total_orders: number
  completed_orders: number
  total_tmc_items: number
  total_actual_cost: number
  total_norm_cost: number
  total_savings: number
  avg_savings_percent: number
  avg_deviation_percent: number
  total_overruns: number
  avg_mileage_between: number
  avg_days_between: number
}

type WorkTypeEfficiency = {
  repair_kind: string
  total_orders: number
  total_actual_cost: number
  total_norm_cost: number
  total_savings: number
  avg_savings_percent: number
  avg_deviation_percent: number
  avg_mileage_between: number
}

type MonthlyEfficiency = {
  month: string
  section: string
  orders_count: number
  actual_cost: number
  norm_cost: number
  savings: number
  avg_savings_percent: number
}

type ExecutiveSummary = {
  work_order_id: string
  unit: string
  section: string
  repair_kind: string
  status: string
  total_cost: number
  total_norm_cost: number
  cost_savings: number
  savings_percent: number
  avg_deviation_percent: number
  mileage_between_orders: number
  created_at: string
}

// AI Insights типы
type AiInsight = {
  id: string
  equipment_id: string
  work_order_id: string
  insight_type: "anomaly" | "prediction" | "efficiency"
  probability: number
  severity: "low" | "medium" | "high" | "critical"
  message: string
  suggested_action: string
  details: Record<string, unknown>
  is_resolved: boolean
  created_at: string
  equipment_name?: string
}

type FleetHealth = {
  total_assets: number
  healthy_count: number
  warning_count: number
  risk_count: number
  critical_count: number
  avg_health_score: number
  reliability_percent: number
}

type EquipmentWithRisk = {
  id: string
  name: string
  failure_probability: number
  health_score: number
  predicted_failure_km: number
  last_ml_update: string
}

// Форматирование чисел
const formatCurrency = (value: number | null | undefined) => {
  if (value == null) return "0"
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(0)}K`
  return value.toFixed(0)
}

const formatPercent = (value: number | null | undefined) => {
  if (value == null) return "0%"
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`
}

// KPI Card компонент
function KpiCard({ title, value, subtitle, icon: Icon, trend, trendValue, color = "blue" }: {
  title: string
  value: string | number
  subtitle?: string
  icon: React.ElementType
  trend?: "up" | "down" | "neutral"
  trendValue?: string
  color?: "blue" | "green" | "red" | "amber" | "purple"
}) {
  const colorClasses = {
    blue: "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400",
    green: "bg-green-50 dark:bg-green-950 text-green-600 dark:text-green-400",
    red: "bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400",
    amber: "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400",
    purple: "bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400",
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{title}</p>
          <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
          {subtitle && <p className="mt-1 text-xs text-gray-500">{subtitle}</p>}
          {trend && trendValue && (
            <div className={`mt-2 flex items-center gap-1 text-xs font-medium ${
              trend === "up" ? "text-green-600" : trend === "down" ? "text-red-600" : "text-gray-500"
            }`}>
              {trend === "up" ? <TrendingUp className="w-3 h-3" /> : 
               trend === "down" ? <TrendingDown className="w-3 h-3" /> : null}
              {trendValue}
            </div>
          )}
        </div>
        <div className={`p-3 rounded-xl ${colorClasses[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  )
}

// Кастомный Tooltip для графиков
const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
      <p className="text-xs font-semibold text-gray-900 dark:text-white mb-2">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? formatCurrency(entry.value) : entry.value}
        </p>
      ))}
    </div>
  )
}

export default function AnalyticsDashboard() {
  const [loading, setLoading] = useState(true)
  const [sectionData, setSectionData] = useState<SectionEfficiency[]>([])
  const [workTypeData, setWorkTypeData] = useState<WorkTypeEfficiency[]>([])
  const [monthlyData, setMonthlyData] = useState<MonthlyEfficiency[]>([])
  const [summaryData, setSummaryData] = useState<ExecutiveSummary[]>([])
  const [selectedPeriod, setSelectedPeriod] = useState<"month" | "quarter" | "year">("month")
  
  // AI Insights состояния
  const [aiInsights, setAiInsights] = useState<AiInsight[]>([])
  const [fleetHealth, setFleetHealth] = useState<FleetHealth | null>(null)
  const [riskEquipment, setRiskEquipment] = useState<EquipmentWithRisk[]>([])

  // Состояния загрузки для разных секций (для Suspense-like поведения)
  const [loadingMain, setLoadingMain] = useState(true)
  const [loadingAi, setLoadingAi] = useState(true)

  // Загрузка AI данных - ОПТИМИЗИРОВАНО: все запросы параллельно
  const fetchAiData = useCallback(async () => {
    setLoadingAi(true)
    try {
      // Все AI запросы параллельно
      const [insightsRes, healthRes, equipmentRes] = await Promise.all([
        supabase.from("ai_insights")
          .select("*")
          .order("created_at", { ascending: false })
          .limit(10)
          .then(r => r)
          .catch(() => ({ data: null, error: true })),
        supabase.from("fleet_health")
          .select("*")
          .limit(1)
          .maybeSingle()
          .then(r => r)
          .catch(() => ({ data: null, error: true })),
        supabase.from("fixed_assets")
          .select("id, name, failure_probability, health_score, predicted_failure_km, last_ml_update")
          .in("asset_type", ["locomotive", "wagon", "diesel"])
          .gt("failure_probability", 0.3)
          .order("failure_probability", { ascending: false })
          .limit(5)
          .then(r => r)
          .catch(() => ({ data: null, error: true }))
      ])

      // Загружаем названия оборудования параллельно с основными данными
      if (insightsRes.data && insightsRes.data.length > 0) {
        const equipmentIds = [...new Set(insightsRes.data.map((i: { equipment_id?: string }) => i.equipment_id).filter(Boolean))]
        if (equipmentIds.length > 0) {
          // Этот запрос выполняется только если есть equipment_ids
          const { data: equipmentNames } = await supabase
            .from("fixed_assets")
            .select("id, name")
            .in("id", equipmentIds)
          
          const nameMap = new Map(equipmentNames?.map((e: { id: string; name: string }) => [e.id, e.name]) || [])
          const insightsWithNames = insightsRes.data.map((insight: AiInsight) => ({
            ...insight,
            equipment_name: nameMap.get(insight.equipment_id) || undefined
          }))
          setAiInsights(insightsWithNames)
        } else {
          setAiInsights(insightsRes.data as AiInsight[])
        }
      }
      
      if (healthRes.data) setFleetHealth(healthRes.data as FleetHealth)
      if (equipmentRes.data) setRiskEquipment(equipmentRes.data as EquipmentWithRisk[])
      
    } catch (error) {
      console.error("Error fetching AI data:", error)
    }
    setLoadingAi(false)
  }, [])

  // Загрузка основных данных - ОПТИМИЗИРОВАНО
  const fetchMainData = useCallback(async () => {
    setLoadingMain(true)
    
    try {
      // ВСЕ запросы параллельно через Promise.all
      const [sectionRes, workTypeRes, monthlyRes, summaryRes] = await Promise.all([
        supabase.from("section_efficiency")
          .select("*")
          .limit(20)
          .then(r => r)
          .catch(() => ({ data: null, error: true })),
        supabase.from("work_type_efficiency")
          .select("*")
          .limit(20)
          .then(r => r)
          .catch(() => ({ data: null, error: true })),
        supabase.from("monthly_efficiency")
          .select("*")
          .order("month", { ascending: false })
          .limit(12) // Только последние 12 месяцев
          .then(r => r)
          .catch(() => ({ data: null, error: true })),
        supabase.from("executive_summary")
          .select("*")
          .order("created_at", { ascending: false })
          .limit(50) // Уменьшено с 100 до 50
          .then(r => r)
          .catch(() => ({ data: null, error: true }))
      ])

      // Устанавливаем данные если они есть
      if (sectionRes.data) setSectionData(sectionRes.data)
      if (workTypeRes.data) setWorkTypeData(workTypeRes.data)
      if (monthlyRes.data) setMonthlyData(monthlyRes.data)
      if (summaryRes.data) setSummaryData(summaryRes.data)
      
    } catch (error) {
      console.error("Error fetching analytics:", error)
    }
    
    setLoadingMain(false)
  }, [])

  // Загрузка всех данных ПАРАЛЛЕЛЬНО
  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      await Promise.all([
        fetchMainData(),
        fetchAiData()
      ])
    } catch (e) {
      console.error("Ошибка загрузки аналитики:", e)
    } finally {
      setLoading(false)
    }
  }, [fetchMainData, fetchAiData])

  useEffect(() => { fetchData() }, [fetchData])

  // Расчёт KPI
  const totalOrders = sectionData.reduce((sum, s) => sum + s.total_orders, 0)
  const totalCost = sectionData.reduce((sum, s) => sum + s.total_actual_cost, 0)
  const totalNormCost = sectionData.reduce((sum, s) => sum + s.total_norm_cost, 0)
  const totalSavings = sectionData.reduce((sum, s) => sum + s.total_savings, 0)
  const avgDeviation = sectionData.length > 0 
    ? sectionData.reduce((sum, s) => sum + s.avg_deviation_percent, 0) / sectionData.length 
    : 0
  const totalOverruns = sectionData.reduce((sum, s) => sum + s.total_overruns, 0)

  // Данные для графика сравнения затрат
  const costComparisonData = sectionData.map(s => ({
    name: s.section,
    actual: s.total_actual_cost,
    norm: s.total_norm_cost,
    savings: s.total_savings
  }))

  // Данные для pie chart эффективности
  const efficiencyPieData = sectionData.map((s, i) => ({
    name: s.section,
    value: Math.abs(s.total_savings),
    color: COLORS.sections[i % COLORS.sections.length],
    isPositive: s.total_savings >= 0
  }))

  // Данные для графика отклонений
  const deviationData = sectionData.map(s => ({
    name: s.section,
    deviation: s.avg_deviation_percent,
    overruns: s.total_overruns
  }))

  // Агрегированные месячные данные для линейного графика
  const monthlyTrendData = monthlyData.reduce((acc, item) => {
    const existing = acc.find(a => a.month === item.month)
    if (existing) {
      existing.actual += item.actual_cost
      existing.norm += item.norm_cost
      existing.orders += item.orders_count
    } else {
      acc.push({
        month: item.month,
        actual: item.actual_cost,
        norm: item.norm_cost,
        orders: item.orders_count
      })
    }
    return acc
  }, [] as { month: string; actual: number; norm: number; orders: number }[]).reverse()

  // Данные по видам работ для bar chart
  const workTypeChartData = workTypeData.map(wt => ({
    name: wt.repair_kind,
    cost: wt.total_actual_cost,
    orders: wt.total_orders,
    mileage: wt.avg_mileage_between
  }))

  // Показываем layout сразу, данные загружаются прогрессивно
  return (
    <div className="p-8 space-y-6 bg-gray-50 dark:bg-gray-950 min-h-screen">
      {/* Заголовок - показывается СРАЗУ */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Экономическая эффективность
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Аналитика расхода ТМЦ и эффективности участков
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select 
            value={selectedPeriod}
            onChange={e => setSelectedPeriod(e.target.value as "month" | "quarter" | "year")}
            className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
          >
            <option value="month">За месяц</option>
            <option value="quarter">За квартал</option>
            <option value="year">За год</option>
          </select>
          <Button onClick={fetchData} variant="outline" className="gap-2" disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Обновить
          </Button>
        </div>
      </div>

      {/* KPI Cards - скелетоны при загрузке */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-4">
        {loadingMain ? (
          <>
            {[1, 2, 3, 4, 5, 6].map(i => <KpiSkeleton key={i} />)}
          </>
        ) : (
          <>
        <KpiCard
          title="Всего нарядов"
          value={totalOrders}
          subtitle="за выбранный период"
          icon={Wrench}
          color="blue"
        />
        <KpiCard
          title="Фактические затраты"
          value={`${formatCurrency(totalCost)} сум`}
          subtitle="общая сумма"
          icon={DollarSign}
          color="amber"
        />
        <KpiCard
          title="Нормативные затраты"
          value={`${formatCurrency(totalNormCost)} сум`}
          subtitle="по нормативам"
          icon={Activity}
          color="purple"
        />
        <KpiCard
          title={totalSavings >= 0 ? "Экономия" : "Перерасход"}
          value={`${formatCurrency(Math.abs(totalSavings))} сум`}
          icon={totalSavings >= 0 ? TrendingUp : TrendingDown}
          trend={totalSavings >= 0 ? "up" : "down"}
          trendValue={formatPercent(totalNormCost > 0 ? (totalSavings / totalNormCost) * 100 : 0)}
          color={totalSavings >= 0 ? "green" : "red"}
        />
        <KpiCard
          title="Ср. отклонение"
          value={formatPercent(avgDeviation)}
          subtitle="от норматива"
          icon={Gauge}
          color={Math.abs(avgDeviation) <= 10 ? "green" : "amber"}
        />
        <KpiCard
          title="Превышения"
          value={totalOverruns}
          subtitle="случаев >20%"
          icon={AlertTriangle}
          color={totalOverruns > 10 ? "red" : "amber"}
        />
        </>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          AI INSIGHTS SECTION - с прогрессивной загрузкой
      ═══════════════════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Здоровье парка - Progress Bar */}
        {loadingAi ? (
          <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl p-6 shadow-lg text-white animate-pulse">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 bg-white/20 rounded-lg" />
              <div className="space-y-1">
                <div className="h-4 w-24 bg-white/30 rounded" />
                <div className="h-3 w-32 bg-white/20 rounded" />
              </div>
            </div>
            <div className="h-12 bg-white/20 rounded mb-4" />
            <div className="h-3 bg-white/20 rounded-full mb-4" />
            <div className="grid grid-cols-4 gap-2">
              {[1,2,3,4].map(i => <div key={i} className="h-14 bg-white/10 rounded-lg" />)}
            </div>
          </div>
        ) : (
        <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl p-6 shadow-lg text-white">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-white/20 rounded-lg">
              <HeartPulse className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold">Здоровье парка</h3>
              <p className="text-xs text-blue-100">Надёжность оборудования</p>
            </div>
          </div>
          
          {fleetHealth && (
            <>
              {/* Главный индикатор */}
              <div className="mb-4">
                <div className="flex items-end justify-between mb-2">
                  <span className="text-4xl font-bold">{fleetHealth.reliability_percent}%</span>
                  <span className="text-sm text-blue-100">надёжность</span>
                </div>
                <div className="h-3 bg-white/20 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-white rounded-full transition-all duration-500"
                    style={{ width: `${fleetHealth.reliability_percent}%` }}
                  />
                </div>
              </div>
              
              {/* Статистика */}
              <div className="grid grid-cols-4 gap-2 text-center">
                <div className="bg-white/10 rounded-lg p-2">
                  <p className="text-lg font-bold text-green-300">{fleetHealth.healthy_count}</p>
                  <p className="text-[10px] text-blue-100">Норма</p>
                </div>
                <div className="bg-white/10 rounded-lg p-2">
                  <p className="text-lg font-bold text-yellow-300">{fleetHealth.warning_count}</p>
                  <p className="text-[10px] text-blue-100">Внимание</p>
                </div>
                <div className="bg-white/10 rounded-lg p-2">
                  <p className="text-lg font-bold text-orange-300">{fleetHealth.risk_count}</p>
                  <p className="text-[10px] text-blue-100">Риск</p>
                </div>
                <div className="bg-white/10 rounded-lg p-2">
                  <p className="text-lg font-bold text-red-300">{fleetHealth.critical_count}</p>
                  <p className="text-[10px] text-blue-100">Критич.</p>
                </div>
              </div>
            </>
          )}
        </div>
        )}

        {/* AI Прогнозы - карточки с рисками */}
        {loadingAi ? (
          <AiSectionSkeleton />
        ) : (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="p-2 bg-purple-100 dark:bg-purple-900/50 rounded-lg">
                <Brain className="w-4 h-4 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">AI-Прогнозы</h3>
                <p className="text-[10px] text-gray-500">Оборудование в зоне риска</p>
              </div>
            </div>
            <Cpu className="w-4 h-4 text-gray-400" />
          </div>
          
          <div className="space-y-3">
            {riskEquipment.length === 0 ? (
              <div className="text-center py-6 text-gray-400">
                <Shield className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-xs">Нет оборудования в зоне риска</p>
              </div>
            ) : (
              riskEquipment.map(eq => (
                <div 
                  key={eq.id}
                  className={`p-3 rounded-lg border-l-4 ${
                    eq.failure_probability >= 0.7 
                      ? "bg-red-50 dark:bg-red-950/30 border-red-500" 
                      : eq.failure_probability >= 0.5
                      ? "bg-amber-50 dark:bg-amber-950/30 border-amber-500"
                      : "bg-yellow-50 dark:bg-yellow-950/30 border-yellow-500"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">{eq.name}</p>
                      <p className="text-[10px] text-gray-500 mt-0.5">
                        {eq.predicted_failure_km 
                          ? `~${eq.predicted_failure_km.toLocaleString()} км до отказа`
                          : "Требуется диагностика"
                        }
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={`text-lg font-bold ${
                        eq.failure_probability >= 0.7 ? "text-red-600" :
                        eq.failure_probability >= 0.5 ? "text-amber-600" : "text-yellow-600"
                      }`}>
                        {(eq.failure_probability * 100).toFixed(0)}%
                      </p>
                      <p className="text-[9px] text-gray-400">риск</p>
                    </div>
                  </div>
                  <div className="mt-2 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full ${
                        eq.failure_probability >= 0.7 ? "bg-red-500" :
                        eq.failure_probability >= 0.5 ? "bg-amber-500" : "bg-yellow-500"
                      }`}
                      style={{ width: `${eq.failure_probability * 100}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
        )}

        {/* Лента уведомлений AI */}
        {loadingAi ? (
          <AiSectionSkeleton />
        ) : (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="p-2 bg-amber-100 dark:bg-amber-900/50 rounded-lg">
                <Bell className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">AI-Уведомления</h3>
                <p className="text-[10px] text-gray-500">Последние инсайты</p>
              </div>
            </div>
            {aiInsights.filter(i => !i.is_resolved).length > 0 && (
              <span className="px-2 py-0.5 text-[10px] font-bold bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 rounded-full">
                {aiInsights.filter(i => !i.is_resolved).length} новых
              </span>
            )}
          </div>
          
          <div className="space-y-2 max-h-[280px] overflow-y-auto">
            {aiInsights.length === 0 ? (
              <div className="text-center py-6 text-gray-400">
                <Zap className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-xs">Нет уведомлений</p>
              </div>
            ) : (
              aiInsights.slice(0, 5).map(insight => (
                <div 
                  key={insight.id}
                  className={`p-3 rounded-lg border ${
                    insight.is_resolved 
                      ? "bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 opacity-60"
                      : insight.insight_type === "anomaly"
                      ? "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800"
                      : insight.insight_type === "prediction"
                      ? "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800"
                      : "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <div className={`p-1 rounded ${
                      insight.insight_type === "anomaly" 
                        ? "bg-red-100 dark:bg-red-900" 
                        : insight.insight_type === "prediction"
                        ? "bg-amber-100 dark:bg-amber-900"
                        : "bg-green-100 dark:bg-green-900"
                    }`}>
                      {insight.insight_type === "anomaly" ? (
                        <XCircle className="w-3 h-3 text-red-600 dark:text-red-400" />
                      ) : insight.insight_type === "prediction" ? (
                        <AlertTriangle className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                      ) : (
                        <CheckCircle className="w-3 h-3 text-green-600 dark:text-green-400" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      {insight.equipment_name && (
                        <div className="flex items-center gap-1 mb-1">
                          <span className="text-[10px] font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-1.5 py-0.5 rounded">
                            {insight.equipment_name}
                          </span>
                          {insight.probability > 0 && (
                            <span className={`text-[9px] font-bold px-1 py-0.5 rounded ${
                              insight.probability >= 0.8 ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300" :
                              insight.probability >= 0.5 ? "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300" :
                              "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300"
                            }`}>
                              {Math.round(insight.probability * 100)}%
                            </span>
                          )}
                        </div>
                      )}
                      <p className="text-xs text-gray-900 dark:text-white leading-snug line-clamp-2">
                        {insight.message}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                          insight.severity === "critical" ? "bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200" :
                          insight.severity === "high" ? "bg-orange-200 text-orange-800 dark:bg-orange-900 dark:text-orange-200" :
                          insight.severity === "medium" ? "bg-yellow-200 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200" :
                          "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                        }`}>
                          {insight.severity === "critical" ? "Критично" :
                           insight.severity === "high" ? "Высокий" :
                           insight.severity === "medium" ? "Средний" : "Низкий"}
                        </span>
                        <span className="text-[9px] text-gray-400">
                          {new Date(insight.created_at).toLocaleString("ru-RU", { 
                            day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" 
                          })}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
        )}
      </div>

      {/* Графики - первый ряд */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Сравнение затрат по участкам */}
        {loadingMain ? (
          <ChartSkeleton />
        ) : (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                Затраты по участкам
              </h3>
              <p className="text-xs text-gray-500 mt-1">Факт vs Норматив</p>
            </div>
            <BarChart3 className="w-5 h-5 text-gray-400" />
          </div>
          <BarChart width={500} height={300} data={costComparisonData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={formatCurrency} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="actual" name="Факт" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
            <Bar dataKey="norm" name="Норматив" fill={COLORS.purple} radius={[4, 4, 0, 0]} />
          </BarChart>
        </div>
        )}

        {/* Экономия/Перерасход по участкам */}
        {loadingMain ? (
          <ChartSkeleton />
        ) : (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                Экономия / Перерасход
              </h3>
              <p className="text-xs text-gray-500 mt-1">По участкам</p>
            </div>
            <PieChartIcon className="w-5 h-5 text-gray-400" />
          </div>
          <div className="flex items-center gap-8">
            <PieChart width={200} height={200}>
              <Pie
                data={efficiencyPieData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                dataKey="value"
                labelLine={false}
              >
                {efficiencyPieData.map((entry, i) => (
                  <Cell 
                    key={i} 
                    fill={entry.isPositive ? COLORS.success : COLORS.danger} 
                    opacity={0.7 + (i * 0.1)}
                  />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
            <div className="flex-1 space-y-2">
              {sectionData.map((s, i) => (
                <div key={s.section} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded-full" 
                      style={{ backgroundColor: s.total_savings >= 0 ? COLORS.success : COLORS.danger }}
                    />
                    <span className="text-gray-700 dark:text-gray-300">{s.section}</span>
                  </div>
                  <span className={`font-semibold ${s.total_savings >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {s.total_savings >= 0 ? "+" : ""}{formatCurrency(s.total_savings)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
        )}
      </div>

      {/* Графики - второй ряд */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Тренд затрат по месяцам */}
        {loadingMain ? (
          <ChartSkeleton />
        ) : (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                Динамика затрат
              </h3>
              <p className="text-xs text-gray-500 mt-1">По месяцам</p>
            </div>
            <LineChartIcon className="w-5 h-5 text-gray-400" />
          </div>
          <AreaChart width={500} height={300} data={monthlyTrendData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={formatCurrency} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area 
              type="monotone" 
              dataKey="actual" 
              name="Факт" 
              stroke={COLORS.primary} 
              fill={COLORS.primary} 
              fillOpacity={0.3} 
            />
            <Area 
              type="monotone" 
              dataKey="norm" 
              name="Норматив" 
              stroke={COLORS.purple} 
              fill={COLORS.purple} 
              fillOpacity={0.3} 
            />
          </AreaChart>
        </div>
        )}

        {/* Отклонения от нормативов */}
        {loadingMain ? (
          <ChartSkeleton />
        ) : (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                Отклонения от нормативов
              </h3>
              <p className="text-xs text-gray-500 mt-1">Среднее отклонение и превышения</p>
            </div>
            <AlertTriangle className="w-5 h-5 text-gray-400" />
          </div>
          <ComposedChart width={500} height={300} data={deviationData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar 
              yAxisId="left" 
              dataKey="deviation" 
              name="Отклонение %" 
              fill={COLORS.warning}
              radius={[4, 4, 0, 0]}
            />
            <Line 
              yAxisId="right" 
              type="monotone" 
              dataKey="overruns" 
              name="Превышения" 
              stroke={COLORS.danger}
              strokeWidth={2}
              dot={{ fill: COLORS.danger }}
            />
          </ComposedChart>
        </div>
        )}
      </div>

      {/* Эффективность по видам работ */}
      {loadingMain ? (
        <ChartSkeleton height={300} />
      ) : (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">
              Эффективность по видам работ
            </h3>
            <p className="text-xs text-gray-500 mt-1">Затраты, количество нарядов и средний пробег</p>
          </div>
          <Wrench className="w-5 h-5 text-gray-400" />
        </div>
        <div className="overflow-x-auto">
          <BarChart width={1000} height={300} data={workTypeChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} tickFormatter={formatCurrency} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar yAxisId="left" dataKey="cost" name="Затраты" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
            <Bar yAxisId="right" dataKey="orders" name="Нарядов" fill={COLORS.success} radius={[4, 4, 0, 0]} />
            <Bar yAxisId="right" dataKey="mileage" name="Ср. пробег" fill={COLORS.cyan} radius={[4, 4, 0, 0]} />
          </BarChart>
        </div>
      </div>
      )}

      {/* Таблица эффективности участков */}
      {loadingMain ? (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden animate-pulse">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
            <div className="h-5 w-48 bg-gray-200 dark:bg-gray-700 rounded" />
          </div>
          <div className="p-4 space-y-3">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="h-10 bg-gray-200 dark:bg-gray-700 rounded" />
            ))}
          </div>
        </div>
      ) : (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">
            Детальная статистика по участкам
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Участок</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Нарядов</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Факт. затраты</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Норматив</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Экономия</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Отклонение</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Превышения</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Ср. пробег</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {sectionData.map(s => (
                <tr key={s.section} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{s.section}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{s.total_orders}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                    {formatCurrency(s.total_actual_cost)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                    {formatCurrency(s.total_norm_cost)}
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold ${
                    s.total_savings >= 0 ? "text-green-600" : "text-red-600"
                  }`}>
                    {s.total_savings >= 0 ? "+" : ""}{formatCurrency(s.total_savings)}
                  </td>
                  <td className={`px-4 py-3 text-right font-medium ${
                    Math.abs(s.avg_deviation_percent) <= 10 ? "text-green-600" : 
                    Math.abs(s.avg_deviation_percent) <= 20 ? "text-amber-600" : "text-red-600"
                  }`}>
                    {formatPercent(s.avg_deviation_percent)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      s.total_overruns === 0 ? "bg-green-100 text-green-700" :
                      s.total_overruns <= 5 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                    }`}>
                      {s.total_overruns}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                    {s.avg_mileage_between?.toLocaleString() || "—"} км
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      )}
    </div>
  )
}
