import type { ElementType } from "react"
import { TrendingDown, TrendingUp } from "@/components/ui/icons"

export function KpiSkeleton() {
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

export function ChartSkeleton({ height = 300 }: { height?: number }) {
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
          {[40, 65, 45, 80, 55, 70, 50].map((itemHeight, index) => (
            <div key={index} className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-t" style={{ height: `${itemHeight}%` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

export function AiSectionSkeleton() {
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
        {[1, 2, 3].map((item) => <div key={item} className="h-16 bg-gray-200 dark:bg-gray-700 rounded-lg" />)}
      </div>
    </div>
  )
}

export function formatCurrency(value: number | null | undefined) {
  if (value == null) return "0"
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return value.toFixed(0)
}

export function formatPercent(value: number | null | undefined) {
  if (value == null) return "0%"
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`
}

export function KpiCard({ title, value, subtitle, icon: Icon, trend, trendValue, color = "blue" }: {
  title: string
  value: string | number
  subtitle?: string
  icon: ElementType
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

export const CustomTooltip = ({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
      <p className="text-xs font-semibold text-gray-900 dark:text-white mb-2">{label}</p>
      {payload.map((entry, index) => (
        <p key={index} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? formatCurrency(entry.value) : entry.value}
        </p>
      ))}
    </div>
  )
}
