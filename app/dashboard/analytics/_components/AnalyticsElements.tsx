import type { ElementType } from "react"
import { TrendingDown, TrendingUp } from "@/components/ui/icons"
import { fmtMoney } from "@/lib/format"

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

export type Tone = "blue" | "green" | "red" | "amber" | "purple" | "indigo"

const TONES: Record<Tone, { chip: string; bar: string; value: string }> = {
  blue: { chip: "bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400", bar: "from-blue-500 to-blue-400", value: "text-gray-900 dark:text-white" },
  green: { chip: "bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400", bar: "from-green-500 to-emerald-400", value: "text-green-600 dark:text-green-400" },
  red: { chip: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400", bar: "from-red-500 to-rose-400", value: "text-red-600 dark:text-red-400" },
  amber: { chip: "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400", bar: "from-amber-500 to-yellow-400", value: "text-gray-900 dark:text-white" },
  purple: { chip: "bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-400", bar: "from-purple-500 to-fuchsia-400", value: "text-gray-900 dark:text-white" },
  indigo: { chip: "bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400", bar: "from-violet-500 to-indigo-500", value: "text-gray-900 dark:text-white" },
}

/** One card style for every headline value on the page: KPI, money and AI figures. */
export function StatCard({ title, value, unit, subtitle, icon: Icon, trend, trendValue, color = "blue", colorValue = false }: {
  title: string
  value: string | number
  unit?: string
  subtitle?: string
  icon: ElementType
  trend?: "up" | "down" | "neutral"
  trendValue?: string
  color?: Tone
  /** paint the number itself with the tone (savings green / overrun red) */
  colorValue?: boolean
}) {
  const tone = TONES[color]
  return (
    <div className="relative overflow-hidden rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${tone.bar}`} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">{title}</p>
          <p className={`mt-2 flex flex-wrap items-baseline gap-x-1.5 text-2xl font-bold tabular-nums ${colorValue ? tone.value : "text-gray-900 dark:text-white"}`}>
            {value}
            {unit && <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{unit}</span>}
          </p>
          {subtitle && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>}
          {trend && trendValue && (
            <div className={`mt-2 flex items-center gap-1 text-xs font-medium ${
              trend === "up" ? "text-green-600 dark:text-green-400" : trend === "down" ? "text-red-600 dark:text-red-400" : "text-gray-500"
            }`}>
              {trend === "up" ? <TrendingUp className="h-3 w-3" /> : trend === "down" ? <TrendingDown className="h-3 w-3" /> : null}
              {trendValue}
            </div>
          )}
        </div>
        <div className={`shrink-0 rounded-xl p-3 ${tone.chip}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  )
}

export const KpiCard = StatCard

export const CustomTooltip = ({ active, payload, label, format = fmtMoney }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
  format?: (value: number, name: string) => string
}) => {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-700 dark:bg-gray-900">
      <p className="mb-2 text-xs font-semibold text-gray-900 dark:text-white">{label}</p>
      {payload.map((entry, index) => (
        <p key={index} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? format(entry.value, entry.name) : entry.value}
        </p>
      ))}
    </div>
  )
}
