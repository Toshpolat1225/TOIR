"use client"

import { useState, useEffect, useCallback } from "react"
import { api, type ReportName } from "@/lib/api"
import { useSectionView } from "@/lib/section-view-context"
import {
  FileText, ClipboardList, Landmark, Package,
  Calendar, Download, BarChart3, PieChart,
} from "@/components/ui/icons"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart as RechartsPie, Pie, Cell, Legend,
} from "recharts"

const REPORT_TYPES = [
  { id: "work-orders", label: "Наряд-заказы", icon: ClipboardList },
  { id: "fixed-assets", label: "Основные средства", icon: Landmark },
  { id: "tmc-documents", label: "ТМЦ документы", icon: Package },
] as const

type ReportId = ReportName

const WO_STATUS_LABEL: Record<string, string> = {
  pending: "Запланировано",
  in_progress: "Выполняется",
  completed: "Выполнено",
}
const ASSET_STATUS_LABEL: Record<string, string> = {
  operational: "В эксплуатации",
  maintenance: "На ТО",
  repair: "Ремонт",
  out_of_service: "Выведен",
}
const ASSET_TYPE_LABEL: Record<string, string> = {
  locomotive: "Локомотив",
  wagon: "Вагон",
}

function parseDateStr(s: string): Date | null {
  if (!s) return null
  const [d, m, y] = s.split(".").map(Number)
  if (y && m && d) return new Date(y, m - 1, d)
  const iso = s.slice(0, 10)
  const t = new Date(iso)
  return isNaN(t.getTime()) ? null : t
}

function formatDate(d: Date) {
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" })
}

function toIsoDate(value: string): string | undefined {
  const parsed = parseDateStr(value)
  if (!parsed) return undefined
  return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, "0")}-${String(parsed.getDate()).padStart(2, "0")}`
}

async function resolveSectionId(sectionName: string | null): Promise<string | undefined> {
  if (!sectionName) return undefined
  const sections = await api.sections.list({ limit: 1000, offset: 0 })
  const section = sections.items.find((item) => item.name === sectionName)
    ?? sections.items.find((item) => item.id === sectionName)
  if (!section) throw new Error(`Участок «${sectionName}» не найден`)
  return section.id
}

export default function ReportsPage() {
  const { effectiveSection } = useSectionView()
  const [reportType, setReportType] = useState<ReportId>("work-orders")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reportTotal, setReportTotal] = useState(0)
  const [woData, setWoData] = useState<Record<string, unknown>[]>([])
  const [assetsData, setAssetsData] = useState<Record<string, unknown>[]>([])
  const [tmcData, setTmcData] = useState<Record<string, unknown>[]>([])

  const loadReport = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const sectionId = await resolveSectionId(effectiveSection)
      const response = await api.reports.list(reportType, {
        limit: 1000,
        offset: 0,
        section_id: sectionId,
        date_from: toIsoDate(dateFrom),
        date_to: toIsoDate(dateTo),
      })
      setReportTotal(response.total)
      if (reportType === "work-orders") setWoData(response.items)
      else if (reportType === "fixed-assets") setAssetsData(response.items)
      else setTmcData(response.items)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить отчёт")
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, effectiveSection, reportType])

  useEffect(() => {
    void loadReport()
  }, [loadReport])

  const setDefaultDates = () => {
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth(), 1)
    setDateFrom(formatDate(start))
    setDateTo(formatDate(now))
  }

  const filteredWo = woData
  const filteredAssetsData = assetsData

  const downloadReport = async (report: ReportId, filename: string) => {
    setError(null)
    try {
      const sectionId = await resolveSectionId(effectiveSection)
      const blob = await api.reports.downloadCsv(report, {
        section_id: sectionId,
        date_from: toIsoDate(dateFrom),
        date_to: toIsoDate(dateTo),
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = filename
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось скачать CSV")
    }
  }

  const woByStatus = filteredWo.reduce<Record<string, number>>((acc, row) => {
    const s = (row.status as string) || "pending"
    acc[s] = (acc[s] ?? 0) + 1
    return acc
  }, {})

  const woBySection = filteredWo.reduce<Record<string, number>>((acc, row) => {
    const s = (row.section as string) || "—"
    acc[s] = (acc[s] ?? 0) + 1
    return acc
  }, {})

  const woChartData = Object.entries(woByStatus).map(([k, v]) => ({
    name: WO_STATUS_LABEL[k] || k,
    value: v,
    fill: k === "completed" ? "#10b981" : k === "in_progress" ? "#f59e0b" : "#3b82f6",
  }))

  const sectionChartData = Object.entries(woBySection)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name, count]) => ({ name, count }))

  const assetsByStatus = filteredAssetsData.reduce<Record<string, number>>((acc, row) => {
    const s = (row.status as string) || "operational"
    acc[s] = (acc[s] ?? 0) + 1
    return acc
  }, {})

  const assetsByType = filteredAssetsData.reduce<Record<string, number>>((acc, row) => {
    const t = (row.asset_type as string) || "locomotive"
    acc[t] = (acc[t] ?? 0) + 1
    return acc
  }, {})

  const assetsPieData = [
    ...Object.entries(assetsByStatus).map(([k, v]) => ({ name: ASSET_STATUS_LABEL[k] || k, value: v })),
  ]
  const PIE_COLORS = ["#10b981", "#f59e0b", "#f97316", "#ef4444", "#6366f1"]

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <FileText className="w-7 h-7 text-blue-600"/>
            Отчёты
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Аналитика по наряд-заказам, основным средствам и ТМЦ
          </p>
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Выбор типа отчёта */}
      <div className="flex flex-wrap gap-2">
        {REPORT_TYPES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setReportType(id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
              reportType === id
                ? "bg-blue-600 text-white shadow-md"
                : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
            }`}
          >
            <Icon className="w-4 h-4"/>
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-gray-400 gap-2">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
          Загрузка данных...
        </div>
      ) : (
        <>
          {/* Отчёт: Наряд-заказы */}
          {reportType === "work-orders" && (
            <div className="space-y-6">
              <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex flex-wrap items-end gap-4">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-gray-500"/>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Период</span>
                  </div>
                  <input
                    type="text"
                    placeholder="ДД.ММ.ГГГГ"
                    value={dateFrom}
                    onChange={e => setDateFrom(e.target.value)}
                    className="w-32 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
                  />
                  <span className="text-gray-400">—</span>
                  <input
                    type="text"
                    placeholder="ДД.ММ.ГГГГ"
                    value={dateTo}
                    onChange={e => setDateTo(e.target.value)}
                    className="w-32 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
                  />
                  <button
                    type="button"
                    onClick={setDefaultDates}
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                  >
                    Текущий месяц
                  </button>
                  <button
                    type="button"
                    onClick={() => void downloadReport("work-orders", `naryad-zakazy_${new Date().toISOString().slice(0,10)}.csv`)}
                    className="ml-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium"
                  >
                    <Download className="w-4 h-4"/> Скачать CSV
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4 flex items-center gap-2">
                    <PieChart className="w-4 h-4"/> По статусам
                  </h3>
                  {woChartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <RechartsPie>
                        <Pie data={woChartData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                          {woChartData.map((e, i) => (
                            <Cell key={e.name} fill={e.fill}/>
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: number) => [v, "шт."]}/>
                        <Legend/>
                      </RechartsPie>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-sm text-gray-400 py-8 text-center">Нет данных за выбранный период</p>
                  )}
                </div>
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4"/> По участкам (топ-10)
                  </h3>
                  {sectionChartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={sectionChartData} layout="vertical" margin={{ left: 0, right: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" horizontal={false}/>
                        <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false}/>
                        <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }}/>
                        <Tooltip/>
                        <Bar dataKey="count" name="Нарядов" fill="#3b82f6" radius={[0,4,4,0]}/>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-sm text-gray-400 py-8 text-center">Нет данных</p>
                  )}
                </div>
              </div>

              <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Список наряд-заказов</h3>
                  <span className="text-xs text-gray-500">Всего: {reportTotal}</span>
                </div>
                <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-800/50 sticky top-0">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">№</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Единица</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Участок</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Вид работ</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Статус</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Дата создания</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {filteredWo.slice(0, 100).map((row, i) => (
                        <tr key={(row.id as string) || i} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                          <td className="px-4 py-2.5 font-mono text-gray-600 dark:text-gray-300">{(row.number as string) || (row.id as string)}</td>
                          <td className="px-4 py-2.5">{(row.unit as string) || "—"}</td>
                          <td className="px-4 py-2.5">{row.section as string}</td>
                          <td className="px-4 py-2.5">{(row.work_type as string) || "—"}</td>
                          <td className="px-4 py-2.5">{WO_STATUS_LABEL[row.status as string] || (row.status as string)}</td>
                          <td className="px-4 py-2.5">{(row.created_at as string) || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {reportTotal > 100 && (
                  <p className="px-4 py-2 text-xs text-gray-500 border-t border-gray-100 dark:border-gray-800">
                    Показаны первые 100 из {reportTotal}. Скачайте CSV для полного списка.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Отчёт: Основные средства */}
          {reportType === "fixed-assets" && (
            <div className="space-y-6">
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => void downloadReport("fixed-assets", `os_${new Date().toISOString().slice(0,10)}.csv`)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium"
                >
                  <Download className="w-4 h-4"/> Скачать CSV
                </button>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4">По статусу</h3>
                  {assetsPieData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <RechartsPie>
                        <Pie data={assetsPieData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                          {assetsPieData.map((e, i) => (
                            <Cell key={e.name} fill={PIE_COLORS[i % PIE_COLORS.length]}/>
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: number) => [v, "ед."]}/>
                        <Legend/>
                      </RechartsPie>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-sm text-gray-400 py-8 text-center">Нет данных</p>
                  )}
                </div>
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4">По типу техники</h3>
                  <ul className="space-y-2">
                    {Object.entries(assetsByType).map(([type, count]) => (
                      <li key={type} className="flex justify-between text-sm">
                        <span className="text-gray-600 dark:text-gray-300">{ASSET_TYPE_LABEL[type] || type}</span>
                        <span className="font-semibold text-gray-900 dark:text-white">{count} ед.</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Реестр ОС</h3>
                  <span className="text-xs text-gray-500">Всего: {reportTotal}</span>
                </div>
                <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-800/50 sticky top-0">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Инв. №</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Наименование</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Тип</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Серия</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Статус</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Дата ввода</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {filteredAssetsData.slice(0, 100).map((row, i) => (
                        <tr key={(row.id as string) || i} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                          <td className="px-4 py-2.5 font-mono">{row.inv_number as string}</td>
                          <td className="px-4 py-2.5">{(row.name as string) || "—"}</td>
                          <td className="px-4 py-2.5">{ASSET_TYPE_LABEL[row.asset_type as string] || (row.asset_type as string)}</td>
                          <td className="px-4 py-2.5">{row.series as string}</td>
                          <td className="px-4 py-2.5">{ASSET_STATUS_LABEL[row.status as string] || (row.status as string)}</td>
                          <td className="px-4 py-2.5">{row.comm_date as string}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {reportTotal > 100 && (
                  <p className="px-4 py-2 text-xs text-gray-500 border-t border-gray-100 dark:border-gray-800">
                    Показаны первые 100 из {reportTotal}. Скачайте CSV для полного списка.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Отчёт: ТМЦ */}
          {reportType === "tmc-documents" && (
            <div className="space-y-6">
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => void downloadReport("tmc-documents", `tmc_${new Date().toISOString().slice(0,10)}.csv`)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium"
                >
                  <Download className="w-4 h-4"/> Скачать CSV
                </button>
              </div>
              <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Документы ТМЦ</h3>
                  <span className="text-xs text-gray-500">Всего: {reportTotal}</span>
                </div>
                <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-800/50 sticky top-0">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">№ док.</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Дата</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Наряд</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Депо</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Статус</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {tmcData.slice(0, 100).map((row, i) => (
                        <tr key={(row.id as string) || i} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                          <td className="px-4 py-2.5 font-mono">{row.doc_no as string}</td>
                          <td className="px-4 py-2.5">{row.doc_date as string}</td>
                          <td className="px-4 py-2.5">{(row.work_order_number as string) || (row.work_order_id as string)}</td>
                          <td className="px-4 py-2.5">{(row.section as string) || (row.warehouse as string)}</td>
                          <td className="px-4 py-2.5">{row.status as string}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {tmcData.length === 0 && (
                  <p className="px-5 py-12 text-center text-gray-400 text-sm">Нет документов ТМЦ</p>
                )}
                {reportTotal > 100 && (
                  <p className="px-4 py-2 text-xs text-gray-500 border-t border-gray-100 dark:border-gray-800">
                    Показаны первые 100 из {reportTotal}. Скачайте CSV для полного списка.
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
