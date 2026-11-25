"use client"

import { useState, type ReactNode } from "react"
import {
  ChartSkeleton,
  CustomTooltip,
  KpiSkeleton,
  StatCard,
} from "./_components/AnalyticsElements"
import { AiBlock } from "./_components/AiBlock"
import { PartsForecastSection } from "./_components/PartsForecastSection"
import { useAnalyticsData } from "./_components/useAnalyticsData"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  Line, PieChart, Pie, Cell, AreaChart, Area,
  ComposedChart, ResponsiveContainer
} from "recharts"
import {
  TrendingUp, TrendingDown, DollarSign, AlertTriangle,
  Activity, Gauge, Wrench, RefreshCw,
  BarChart3, PieChartIcon, LineChartIcon,
  Loader2
} from "@/components/ui/icons"
import { Button } from "@/components/ui/button"
import { ChartZoomControls, useChartZoom } from "@/components/ui/chart-zoom"
import { fmtInt, fmtMoney, fmtNumber, fmtPercent } from "@/lib/format"

// Цвета для графиков
const COLORS = {
  primary: "#3b82f6",
  success: "#22c55e",
  warning: "#f59e0b",
  danger: "#ef4444",
  purple: "#8b5cf6",
  cyan: "#06b6d4",
}

const GRID = { strokeDasharray: "3 3", stroke: "#9ca3af", strokeOpacity: 0.25 }
const TICK = { fontSize: 11, fill: "#9ca3af" }

const deviationFormat = (value: number, name: string) => (name.startsWith("Отклонение") ? fmtPercent(value) : fmtInt(value))
const workTypeFormat = (value: number, name: string) => (name === "Затраты" ? fmtMoney(value) : name === "Нарядов" ? fmtInt(value) : fmtNumber(value))

function ChartCard({ title, subtitle, icon: Icon, action, children }: {
  title: string
  subtitle: string
  icon: typeof BarChart3
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="min-w-0 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900 sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h3>
          <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          {action}
          <Icon className="h-5 w-5 text-gray-400" />
        </div>
      </div>
      {children}
    </div>
  )
}

export default function AnalyticsDashboard() {
  const {
    sectionData,
    workTypeData,
    monthlyData,
    aiInsights,
    mlInsights,
    fleetHealth,
    riskEquipment,
    loading,
    loadingMain,
    loadingAi,
    error: loadError,
    reload: fetchData,
  } = useAnalyticsData()
  const [selectedPeriod, setSelectedPeriod] = useState<"month" | "quarter" | "year">("month")

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
  const efficiencyPieData = sectionData.map((s) => ({
    name: s.section,
    value: Math.abs(s.total_savings),
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

  const trendZoom = useChartZoom(monthlyTrendData, 4)

  // Данные по видам работ для bar chart
  const workTypeChartData = workTypeData.map(wt => ({
    name: wt.repair_kind,
    cost: wt.total_actual_cost,
    orders: wt.total_orders,
    mileage: wt.avg_mileage_between
  }))

  // Показываем layout сразу, данные загружаются прогрессивно
  return (
    <div className="mx-auto min-h-screen max-w-[1680px] space-y-6 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950">
      {/* Заголовок - показывается СРАЗУ */}
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            ИИ-Аналитика
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Экономическая эффективность: расход ТМЦ и работа участков
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:gap-3">
          <select 
            value={selectedPeriod}
            onChange={e => setSelectedPeriod(e.target.value as "month" | "quarter" | "year")}
            className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
          >
            <option value="month">За месяц</option>
            <option value="quarter">За квартал</option>
            <option value="year">За год</option>
          </select>
          <Button onClick={() => void fetchData()} variant="outline" className="gap-2" disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Обновить
          </Button>
        </div>
      </div>

      {loadError && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {loadError}
        </div>
      )}

      {/* KPI: одна карточка для количества, денег и процентов */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {loadingMain ? (
          <>
            {[1, 2, 3, 4, 5, 6].map(i => <KpiSkeleton key={i} />)}
          </>
        ) : (
          <>
            <StatCard title="Всего нарядов" value={fmtInt(totalOrders)} subtitle="за выбранный период" icon={Wrench} color="blue" />
            <StatCard title="Фактические затраты" value={fmtMoney(totalCost)} unit="сум" subtitle="общая сумма" icon={DollarSign} color="amber" />
            <StatCard title="Нормативные затраты" value={fmtMoney(totalNormCost)} unit="сум" subtitle="по нормативам" icon={Activity} color="purple" />
            <StatCard
              title={totalSavings >= 0 ? "Экономия" : "Перерасход"}
              value={fmtMoney(Math.abs(totalSavings))}
              unit="сум"
              subtitle="факт против норматива"
              icon={totalSavings >= 0 ? TrendingUp : TrendingDown}
              trend={totalSavings >= 0 ? "up" : "down"}
              trendValue={fmtPercent(totalNormCost > 0 ? (totalSavings / totalNormCost) * 100 : 0, true)}
              color={totalSavings >= 0 ? "green" : "red"}
              colorValue
            />
            <StatCard
              title="Ср. отклонение"
              value={fmtPercent(avgDeviation)}
              subtitle="от норматива"
              icon={Gauge}
              color={Math.abs(avgDeviation) <= 10 ? "green" : "amber"}
            />
            <StatCard
              title="Превышения"
              value={fmtInt(totalOverruns)}
              subtitle="случаев >20%"
              icon={AlertTriangle}
              color={totalOverruns > 10 ? "red" : "amber"}
            />
          </>
        )}
      </div>

      <AiBlock
        loading={loadingAi}
        fleetHealth={fleetHealth}
        riskEquipment={riskEquipment}
        mlInsights={mlInsights}
        aiSummary={aiInsights}
        sections={sectionData}
      />

      <PartsForecastSection />

      {/* Графики - первый ряд */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {loadingMain ? <ChartSkeleton /> : (
          <ChartCard title="Затраты по участкам" subtitle="Факт vs Норматив, сум" icon={BarChart3}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={costComparisonData}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="name" tick={TICK} />
                <YAxis tick={TICK} tickFormatter={(v: number) => fmtMoney(v)} width={78} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="actual" name="Факт" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
                <Bar dataKey="norm" name="Норматив" fill={COLORS.purple} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {loadingMain ? <ChartSkeleton /> : (
          <ChartCard title="Экономия / Перерасход" subtitle="По участкам: зелёный - экономия, красный - перерасход" icon={PieChartIcon}>
            <div className="flex flex-col items-center gap-6 sm:flex-row">
              <div className="h-48 w-48 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={efficiencyPieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" labelLine={false}>
                      {efficiencyPieData.map((entry, i) => (
                        <Cell key={i} fill={entry.isPositive ? COLORS.success : COLORS.danger} opacity={Math.min(1, 0.7 + i * 0.1)} />
                      ))}
                    </Pie>
                    <Tooltip content={<CustomTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="w-full flex-1 space-y-2">
                {sectionData.map((s) => (
                  <div key={s.section} className="flex items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 rounded-full" style={{ backgroundColor: s.total_savings >= 0 ? COLORS.success : COLORS.danger }} />
                      <span className="text-gray-700 dark:text-gray-300">{s.section}</span>
                    </div>
                    <span className={`font-semibold tabular-nums ${s.total_savings >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                      {s.total_savings >= 0 ? "+" : ""}{fmtMoney(s.total_savings)} сум
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </ChartCard>
        )}
      </div>

      {/* Графики - второй ряд */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {loadingMain ? <ChartSkeleton /> : (
          <ChartCard title="Динамика затрат" subtitle="По месяцам, сум" icon={LineChartIcon} action={<ChartZoomControls zoom={trendZoom} />}>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={trendZoom.view}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="month" tick={TICK} />
                <YAxis tick={TICK} tickFormatter={(v: number) => fmtMoney(v)} width={78} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Area type="monotone" dataKey="actual" name="Факт" stroke={COLORS.primary} fill={COLORS.primary} fillOpacity={0.3} />
                <Area type="monotone" dataKey="norm" name="Норматив" stroke={COLORS.purple} fill={COLORS.purple} fillOpacity={0.3} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {loadingMain ? <ChartSkeleton /> : (
          <ChartCard title="Отклонения от нормативов" subtitle="Среднее отклонение и превышения" icon={AlertTriangle}>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={deviationData}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="name" tick={TICK} />
                <YAxis yAxisId="left" tick={TICK} tickFormatter={(v: number) => fmtPercent(v)} width={70} />
                <YAxis yAxisId="right" orientation="right" tick={TICK} />
                <Tooltip content={<CustomTooltip format={deviationFormat} />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="left" dataKey="deviation" name="Отклонение %" fill={COLORS.warning} radius={[4, 4, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="overruns" name="Превышения" stroke={COLORS.danger} strokeWidth={2} dot={{ fill: COLORS.danger }} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartCard>
        )}
      </div>

      {/* Эффективность по видам работ */}
      {loadingMain ? <ChartSkeleton height={300} /> : (
        <ChartCard title="Эффективность по видам работ" subtitle="Затраты, количество нарядов и средний пробег" icon={Wrench}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={workTypeChartData}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="name" tick={TICK} />
              <YAxis yAxisId="left" tick={TICK} tickFormatter={(v: number) => fmtMoney(v)} width={78} />
              <YAxis yAxisId="right" orientation="right" tick={TICK} />
              <Tooltip content={<CustomTooltip format={workTypeFormat} />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="left" dataKey="cost" name="Затраты" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
              <Bar yAxisId="right" dataKey="orders" name="Нарядов" fill={COLORS.success} radius={[4, 4, 0, 0]} />
              <Bar yAxisId="right" dataKey="mileage" name="Ср. пробег" fill={COLORS.cyan} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
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
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{fmtInt(s.total_orders)}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                    {fmtMoney(s.total_actual_cost)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                    {fmtMoney(s.total_norm_cost)}
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold ${
                    s.total_savings >= 0 ? "text-green-600" : "text-red-600"
                  }`}>
                    {s.total_savings >= 0 ? "+" : ""}{fmtMoney(s.total_savings)}
                  </td>
                  <td className={`px-4 py-3 text-right font-medium ${
                    Math.abs(s.avg_deviation_percent) <= 10 ? "text-green-600" : 
                    Math.abs(s.avg_deviation_percent) <= 20 ? "text-amber-600" : "text-red-600"
                  }`}>
                    {fmtPercent(s.avg_deviation_percent, true)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      s.total_overruns === 0 ? "bg-green-100 text-green-700" :
                      s.total_overruns <= 5 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                    }`}>
                      {fmtInt(s.total_overruns)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                    {s.avg_mileage_between ? `${fmtNumber(s.avg_mileage_between)} км` : "—"}
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
