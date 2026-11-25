"use client"

import { useState, type ComponentType } from "react"
import { useSectionView } from "@/lib/section-view-context"
import {
  FileText, ClipboardList, Landmark, Package, CheckCircle, DollarSign, Clock, RefreshCw, Users, HeartPulse,
  Gauge, AlertTriangle, BarChart3, Target,
} from "@/components/ui/icons"
import { PeriodBar, periodDays, type Period, type ReportProps } from "./_components/common"
import { PlanReport, TmcNormReport, DowntimeReport, RepeatsReport, ExecutorsReport } from "./_components/ReportsA"
import { FleetReport, MileageReport, EmergencyReport, NomenclatureReport, SummaryReport } from "./_components/ReportsB"
import { RegistryReports } from "./_components/RegistryReports"

type Icon = ComponentType<{ className?: string }>

type ReportDef = {
  id: string
  label: string
  hint: string
  icon: Icon
  group: "analytics" | "registry"
  usesPeriod: boolean
  render: (props: ReportProps) => React.ReactNode
}

const REPORTS: ReportDef[] = [
  { id: "summary", label: "Сводка для руководства", hint: "Ключевые цифры и сравнение с прошлым периодом", icon: Target, group: "analytics", usesPeriod: true, render: (p) => <SummaryReport {...p} /> },
  { id: "plan", label: "Исполнение плана ТО", hint: "В срок, с опозданием, просрочено", icon: CheckCircle, group: "analytics", usesPeriod: true, render: (p) => <PlanReport {...p} /> },
  { id: "tmc-norm", label: "ТМЦ: факт и норма", hint: "Перерасход по участкам и видам ремонта", icon: DollarSign, group: "analytics", usesPeriod: true, render: (p) => <TmcNormReport {...p} /> },
  { id: "downtime", label: "Простои и причины", hint: "Дни простоя и затронутые ТО", icon: Clock, group: "analytics", usesPeriod: true, render: (p) => <DowntimeReport {...p} /> },
  { id: "repeats", label: "Повторные отказы", hint: "Повторный ремонт в течение N дней", icon: RefreshCw, group: "analytics", usesPeriod: true, render: (p) => <RepeatsReport {...p} /> },
  { id: "executors", label: "Исполнители", hint: "Загрузка, часы, просрочки, перерасход", icon: Users, group: "analytics", usesPeriod: true, render: (p) => <ExecutorsReport {...p} /> },
  { id: "fleet", label: "Состояние парка", hint: "Готовность по месяцам и участкам", icon: HeartPulse, group: "analytics", usesPeriod: false, render: (p) => <FleetReport {...p} /> },
  { id: "mileage", label: "Пробег и ближайшие ТО", hint: "Прогноз по плану и остаток км", icon: Gauge, group: "analytics", usesPeriod: false, render: (p) => <MileageReport {...p} /> },
  { id: "emergency", label: "Аварии и происшествия", hint: "Аварийные и критические наряды", icon: AlertTriangle, group: "analytics", usesPeriod: true, render: (p) => <EmergencyReport {...p} /> },
  { id: "nomenclature", label: "ТМЦ по номенклатуре", hint: "Топ-20 по стоимости и количеству", icon: BarChart3, group: "analytics", usesPeriod: true, render: (p) => <NomenclatureReport {...p} /> },
  { id: "work-orders", label: "Реестр: наряд-заказы", hint: "Список, фильтры, CSV", icon: ClipboardList, group: "registry", usesPeriod: false, render: () => <RegistryReports reportType="work-orders" /> },
  { id: "fixed-assets", label: "Реестр: основные средства", hint: "Список, статусы, CSV", icon: Landmark, group: "registry", usesPeriod: false, render: () => <RegistryReports reportType="fixed-assets" /> },
  { id: "tmc-documents", label: "Реестр: документы ТМЦ", hint: "Список документов, CSV", icon: Package, group: "registry", usesPeriod: false, render: () => <RegistryReports reportType="tmc-documents" /> },
]

export default function ReportsPage() {
  const { effectiveSection } = useSectionView()
  const [activeId, setActiveId] = useState("summary")
  const [period, setPeriod] = useState<Period>(() => periodDays(90))
  const active = REPORTS.find((r) => r.id === activeId) ?? REPORTS[0]

  const card = (r: ReportDef) => {
    const Icon = r.icon
    const on = r.id === active.id
    return (
      <button
        key={r.id}
        type="button"
        onClick={() => setActiveId(r.id)}
        aria-pressed={on}
        className={`text-left rounded-xl border px-4 py-3 transition-all ${
          on
            ? "bg-blue-600 border-blue-600 text-white shadow-md"
            : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 text-gray-800 dark:text-gray-200 hover:border-blue-400 dark:hover:border-blue-600"
        }`}
      >
        <span className="flex items-center gap-2 text-sm font-semibold"><Icon className="w-4 h-4 shrink-0" />{r.label}</span>
        <span className={`block text-xs mt-1 ${on ? "text-blue-100" : "text-gray-500 dark:text-gray-400"}`}>{r.hint}</span>
      </button>
    )
  }

  return (
    <div className="p-4 sm:p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileText className="w-7 h-7 text-blue-600" />
          {"Отчёты"}
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {"Управленческая аналитика по плану ТО, ТМЦ, простоям, надёжности, исполнителям и парку"}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
        {REPORTS.filter((r) => r.group === "analytics").map(card)}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {REPORTS.filter((r) => r.group === "registry").map(card)}
      </div>

      {active.group === "analytics" && (
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{active.label}</h2>
      )}
      {active.usesPeriod && <PeriodBar period={period} onChange={setPeriod} />}

      <div key={active.id}>{active.render({ section: effectiveSection ?? undefined, period })}</div>
    </div>
  )
}
