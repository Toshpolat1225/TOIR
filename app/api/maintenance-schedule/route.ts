import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

const AVG_KM_PER_DAY = 10

type ScheduleItem = {
  id: string
  unit: string
  type: string
  startDate: string
  durationH: number
  depot: string
  tech: string
  status: string
  note?: string
  mileage?: number
  remainingKm?: number
  nextThreshold?: number
}

function dateToDdMmYyyy(isoDate: string): string {
  if (!isoDate) return ""
  const [y, m, d] = isoDate.split("T")[0].split("-")
  return [d, m, y].join(".")
}

function nextTriggerKm(currentMileage: number, intervalKm: number): number {
  if (intervalKm <= 0) return currentMileage
  return (Math.floor(currentMileage / intervalKm) + 1) * intervalKm
}

export async function GET(request: NextRequest) {
  try {
    const monthParam = request.nextUrl.searchParams.get("month")
    const now = new Date()
    let year = now.getFullYear()
    let month = now.getMonth()
    if (monthParam) {
      const [y, m] = monthParam.split("-").map(Number)
      if (!isNaN(y) && !isNaN(m) && m >= 1 && m <= 12) {
        year = y
        month = m - 1
      }
    }
    const rangeStart = new Date(year, month, 1)
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())

    const [
      { data: woData },
      { data: planData },
      { data: assetsData },
      { data: intervalsData },
    ] = await Promise.all([
      supabase
        .from("work_orders")
        .select("id,unit,repair_kind,work_type,date_start,section,depot,tech,status,note")
        .order("date_start", { ascending: true })
        .limit(500),
      supabase
        .from("maintenance_plan")
        .select("id,asset_id,asset_name,maintenance_type,trigger_mileage,scheduled_date,status")
        .in("status", ["Scheduled", "InProgress"]),
      supabase
        .from("fixed_assets")
        .select("id,name,mileage,depot,asset_type")
        .in("asset_type", ["locomotive", "diesel"]),
      supabase
        .from("maintenance_intervals")
        .select("code,name,interval_km,asset_types,is_active")
        .eq("is_active", true),
    ])

    const assets = assetsData || []
    const assetMileage: Record<string, number> = {}
    const assetDepot: Record<string, string> = {}
    const mileageByUnit: Record<string, number> = {}
    for (const a of assets) {
      const m = parseInt(String((a as { mileage?: string }).mileage || "0"), 10) || 0
      const id = (a as { id: string }).id
      const name = (a as { name?: string }).name
      const depot = (a as { depot?: string }).depot
      assetMileage[id] = m
      assetDepot[id] = depot || ""
      mileageByUnit[name?.trim() || ""] = m
    }

    const woStatus: Record<string, string> = {
      pending: "upcoming",
      in_progress: "in_progress",
      completed: "completed",
    }
    const todayStr = [
      String(today.getDate()).padStart(2, "0"),
      String(today.getMonth() + 1).padStart(2, "0"),
      today.getFullYear(),
    ].join(".")
    const woItems: ScheduleItem[] = (woData || []).map((r: Record<string, unknown>) => ({
      id: String(r.id),
      unit: String(r.unit || ""),
      type: String(r.repair_kind || r.work_type || "ТО"),
      startDate: String(r.date_start || todayStr),
      durationH: 8,
      depot: String(r.section || r.depot || ""),
      tech: String(r.tech || ""),
      status: woStatus[String(r.status)] ?? "upcoming",
      note: r.note as string | undefined,
      mileage: mileageByUnit[String(r.unit || "").trim()],
    }))

    const planItems: ScheduleItem[] = (planData || []).map((mp: Record<string, unknown>) => {
      const trigger = Number(mp.trigger_mileage) || 0
      const currentMileage = assetMileage[mp.asset_id as string] ?? 0
      const remainingKm = trigger - currentMileage
      const status = mp.status === "InProgress" ? "in_progress" : remainingKm < 0 ? "overdue" : "upcoming"
      return {
        id: `plan-${mp.id}`,
        unit: String(mp.asset_name || ""),
        type: String(mp.maintenance_type || "ТО"),
        startDate: dateToDdMmYyyy(String(mp.scheduled_date || "")) || todayStr,
        durationH: 8,
        depot: assetDepot[mp.asset_id as string] ?? "",
        tech: "",
        status,
        mileage: currentMileage,
        remainingKm: remainingKm < 0 ? 0 : remainingKm,
        nextThreshold: trigger,
      }
    })

    const existingPlanKeys = new Set(
      (planData || []).map(
        (mp: Record<string, unknown>) =>
          `${mp.asset_id}-${mp.maintenance_type}-${mp.trigger_mileage}`
      )
    )
    const intervals = intervalsData || []
    const rawIntervalItems: ScheduleItem[] = []
    for (const a of assets) {
      const mileage = parseInt(String((a as { mileage?: string }).mileage || "0"), 10) || 0
      const assetTypes = [(a as { asset_type?: string }).asset_type].filter(Boolean) as string[]
      const aTypes = assetTypes.length ? assetTypes : ["locomotive", "diesel"]
      for (const iv of intervals as { code: string; name: string; interval_km: number; asset_types: string[] | null; is_active: boolean }[]) {
        if (!iv.is_active || !iv.interval_km) continue
        const types = iv.asset_types || ["locomotive", "diesel"]
        if (!aTypes.some((t: string) => types.includes(t))) continue
        const nextTr = nextTriggerKm(mileage, iv.interval_km)
        const key = `${(a as { id: string }).id}-${iv.code}-${nextTr}`
        if (existingPlanKeys.has(key)) continue
        const remainingKm = nextTr - mileage
        rawIntervalItems.push({
          id: `interval-${key}`,
          unit: (a as { name?: string }).name || "",
          type: iv.code || iv.name,
          startDate: todayStr,
          durationH: 8,
          depot: (a as { depot?: string }).depot || "",
          tech: "",
          status: "upcoming",
          mileage,
          remainingKm: remainingKm < 0 ? 0 : remainingKm,
          nextThreshold: nextTr,
        })
      }
    }

    const overdueOrDue = rawIntervalItems.filter((i) => (i.remainingKm ?? 0) <= 0)
    const future = rawIntervalItems.filter((i) => (i.remainingKm ?? 0) > 0)
    overdueOrDue.sort((a, b) => {
      const aOver = (a.mileage ?? 0) - (a.nextThreshold ?? 0)
      const bOver = (b.mileage ?? 0) - (b.nextThreshold ?? 0)
      return bOver - aOver
    })
    const dueItems: ScheduleItem[] = overdueOrDue.map((item, i) => {
      const dayOffset = Math.min(i, 6)
      const d = new Date(rangeStart.getFullYear(), rangeStart.getMonth(), rangeStart.getDate() + dayOffset)
      const startDate = [
        String(d.getDate()).padStart(2, "0"),
        String(d.getMonth() + 1).padStart(2, "0"),
        d.getFullYear(),
      ].join(".")
      const status = (item.remainingKm ?? 0) < 0 ? "overdue" : "upcoming"
      return { ...item, startDate, status }
    })
    future.sort((a, b) => (a.remainingKm ?? 0) - (b.remainingKm ?? 0))
    const futureItems: ScheduleItem[] = future.map((item) => {
      const remainingKm = item.remainingKm ?? 0
      const estimatedDays = Math.ceil(remainingKm / AVG_KM_PER_DAY)
      const d = new Date(today)
      d.setDate(d.getDate() + estimatedDays)
      const startDate = [
        String(d.getDate()).padStart(2, "0"),
        String(d.getMonth() + 1).padStart(2, "0"),
        d.getFullYear(),
      ].join(".")
      return { ...item, startDate }
    })

    const schedule = [...woItems, ...planItems, ...dueItems, ...futureItems]
    return NextResponse.json({ schedule })
  } catch (e) {
    console.error("maintenance-schedule API:", e)
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Ошибка формирования графика" },
      { status: 500 }
    )
  }
}
