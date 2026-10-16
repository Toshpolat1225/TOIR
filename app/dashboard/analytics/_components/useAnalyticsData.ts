"use client"

import { useCallback, useEffect, useState } from "react"
import { api } from "@/lib/api"
import { ApiHttpError } from "@/lib/api"

export type SectionEfficiency = {
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

export type WorkTypeEfficiency = {
  section: string
  section_id: string
  repair_kind: string
  total_orders: number
  total_actual_cost: number
  total_norm_cost: number
  total_savings: number
  avg_savings_percent: number
  avg_deviation_percent: number
  avg_mileage_between: number
  total_overruns: number
}

export type MonthlyEfficiency = {
  month: string
  section: string
  section_id: string
  orders_count: number
  actual_cost: number
  norm_cost: number
  savings: number
  avg_savings_percent: number
}

export type AiInsight = {
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

export type FleetHealth = {
  total_assets: number
  healthy_count: number
  warning_count: number
  risk_count: number
  critical_count: number
  avg_health_score: number
  reliability_percent: number
}

export type EquipmentWithRisk = {
  id: string
  name: string
  failure_probability: number
  health_score: number
  predicted_failure_km: number
  last_ml_update: string
}

type AnalyticsData = {
  sectionData: SectionEfficiency[]
  workTypeData: WorkTypeEfficiency[]
  monthlyData: MonthlyEfficiency[]
  aiInsights: AiInsight[]
  fleetHealth: FleetHealth | null
  riskEquipment: EquipmentWithRisk[]
  loading: boolean
  loadingMain: boolean
  loadingAi: boolean
  error: string | null
  reload: () => Promise<void>
}

const numeric = (row: Record<string, unknown>, key: string) => Number(row[key] ?? 0)

function mapSection(row: Record<string, unknown>): SectionEfficiency {
  return {
    section: String(row.section ?? "—"),
    section_id: String(row.section_id ?? ""),
    total_orders: numeric(row, "total_orders"),
    completed_orders: numeric(row, "completed_orders"),
    total_tmc_items: numeric(row, "total_tmc_items"),
    total_actual_cost: numeric(row, "total_actual_cost"),
    total_norm_cost: numeric(row, "total_norm_cost"),
    total_savings: numeric(row, "total_savings"),
    avg_savings_percent: numeric(row, "avg_savings_percent"),
    avg_deviation_percent: numeric(row, "avg_deviation_percent"),
    total_overruns: numeric(row, "total_overruns"),
    avg_mileage_between: numeric(row, "avg_mileage_between"),
    avg_days_between: numeric(row, "avg_days_between"),
  }
}

export function useAnalyticsData(): AnalyticsData {
  const [sectionData, setSectionData] = useState<SectionEfficiency[]>([])
  const [workTypeData, setWorkTypeData] = useState<WorkTypeEfficiency[]>([])
  const [monthlyData, setMonthlyData] = useState<MonthlyEfficiency[]>([])
  const [aiInsights, setAiInsights] = useState<AiInsight[]>([])
  const [fleetHealth, setFleetHealth] = useState<FleetHealth | null>(null)
  const [riskEquipment, setRiskEquipment] = useState<EquipmentWithRisk[]>([])
  const [loadingMain, setLoadingMain] = useState(true)
  const [loadingAi, setLoadingAi] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    setLoadingMain(true)
    setLoadingAi(true)
    const mainRequest = Promise.all([
      api.analytics.list("section-efficiency", { limit: 1000, offset: 0 }),
      api.analytics.list("work-type-efficiency", { limit: 1000, offset: 0 }),
      api.analytics.list("monthly-efficiency", { limit: 1000, offset: 0 }),
    ]).then(([sections, workTypes, months]) => {
      setSectionData(sections.items.map((row) => mapSection(row as Record<string, unknown>)))
      setWorkTypeData(workTypes.items.map((item) => {
        const row = item as Record<string, unknown>
        return {
          section: String(row.section ?? "—"),
          section_id: String(row.section_id ?? ""),
          repair_kind: String(row.repair_kind ?? "—"),
          total_orders: numeric(row, "total_orders"),
          total_actual_cost: numeric(row, "total_actual_cost"),
          total_norm_cost: numeric(row, "total_norm_cost"),
          total_savings: numeric(row, "total_savings"),
          avg_savings_percent: numeric(row, "avg_savings_percent"),
          avg_deviation_percent: numeric(row, "avg_deviation_percent"),
          avg_mileage_between: numeric(row, "avg_mileage_between"),
          total_overruns: numeric(row, "total_overruns"),
        }
      }))
      setMonthlyData(months.items.map((item) => {
        const row = item as Record<string, unknown>
        return {
          month: String(row.month ?? ""),
          section: String(row.section ?? "—"),
          section_id: String(row.section_id ?? ""),
          orders_count: numeric(row, "orders_count"),
          actual_cost: numeric(row, "actual_cost"),
          norm_cost: numeric(row, "norm_cost"),
          savings: numeric(row, "savings"),
          avg_savings_percent: numeric(row, "avg_savings_percent"),
        }
      }))
    }).catch((cause: unknown) => {
      setError(cause instanceof ApiHttpError && cause.status === 404
        ? "Bu bo‘lim keyingi bosqichda ko‘chiriladi"
        : cause instanceof Error ? cause.message : "Не удалось загрузить аналитику")
      setSectionData([])
      setWorkTypeData([])
      setMonthlyData([])
    }).finally(() => setLoadingMain(false))

    const aiRequest = Promise.all([
      api.analytics.list("ai-insights-summary", { limit: 1000, offset: 0 }),
      api.analytics.list("fleet-health", { limit: 1000, offset: 0 }),
      api.fixedAssets.list({ limit: 1000, offset: 0 }),
    ]).then(([insights, health, assets]) => {
      setAiInsights(insights.items.map((item, index) => {
        const row = item as Record<string, unknown>
        const type = row.insight_type === "anomaly" || row.insight_type === "prediction"
          ? row.insight_type
          : "efficiency"
        const severity = ["low", "medium", "high", "critical"].includes(String(row.severity))
          ? row.severity as AiInsight["severity"]
          : "low"
        return {
          id: `${String(row.section_id ?? "fleet")}-${type}-${severity}-${index}`,
          equipment_id: String(row.section_id ?? ""),
          work_order_id: "",
          insight_type: type,
          probability: numeric(row, "avg_probability"),
          severity,
          message: `${numeric(row, "total_count")} событий; не обработано: ${numeric(row, "unresolved_count")}`,
          suggested_action: "",
          details: row,
          is_resolved: numeric(row, "unresolved_count") === 0,
          created_at: String(row.last_created ?? ""),
        }
      }))
      const rows = health.items as Array<Record<string, unknown>>
      const total = rows.reduce((sum, row) => sum + numeric(row, "total_assets"), 0)
      if (!total) {
        setFleetHealth(null)
      } else {
        const weightedAverage = (field: string) => rows.reduce(
          (sum, row) => sum + numeric(row, field) * numeric(row, "total_assets"),
          0,
        ) / total
        setFleetHealth({
          total_assets: total,
          healthy_count: rows.reduce((sum, row) => sum + numeric(row, "healthy_count"), 0),
          warning_count: rows.reduce((sum, row) => sum + numeric(row, "warning_count"), 0),
          risk_count: rows.reduce((sum, row) => sum + numeric(row, "risk_count"), 0),
          critical_count: rows.reduce((sum, row) => sum + numeric(row, "critical_count"), 0),
          avg_health_score: weightedAverage("avg_health_score"),
          reliability_percent: weightedAverage("reliability_percent"),
        })
      }
      setRiskEquipment(
        assets.items
          .filter((asset) => Number(asset.failure_probability ?? 0) > 0.3)
          .sort((first, second) => Number(second.failure_probability ?? 0) - Number(first.failure_probability ?? 0))
          .slice(0, 5)
          .map((asset) => ({
            id: asset.id,
            name: asset.name,
            failure_probability: Number(asset.failure_probability ?? 0),
            health_score: Number(asset.health_score ?? 0),
            predicted_failure_km: Number(asset.predicted_failure_km ?? 0),
            last_ml_update: asset.last_ml_update ?? "",
          })),
      )
    }).catch((cause: unknown) => {
      setError((current) => current ?? (cause instanceof ApiHttpError && cause.status === 404
        ? "Bu bo‘lim keyingi bosqichda ko‘chiriladi"
        : cause instanceof Error ? cause.message : "Не удалось загрузить AI-аналитику"))
      setAiInsights([])
      setFleetHealth(null)
      setRiskEquipment([])
    }).finally(() => setLoadingAi(false))

    await Promise.all([mainRequest, aiRequest])
    setLoading(false)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  return {
    sectionData,
    workTypeData,
    monthlyData,
    aiInsights,
    fleetHealth,
    riskEquipment,
    loading,
    loadingMain,
    loadingAi,
    error,
    reload,
  }
}
