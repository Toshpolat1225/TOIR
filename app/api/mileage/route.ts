import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

const MAINTENANCE_THRESHOLDS: Record<string, number> = {
  "ТО-1": 5000,
  "ТО-2": 15000,
  "ТО-3": 30000,
  "ТР-1": 100000,
  "ТР-2": 200000,
  "ТР-3": 400000,
  "СР": 800000,
  "КР": 1600000,
}

type MaintenancePrediction = {
  asset_id: string
  asset_name: string
  current_mileage: number
  maintenance_type: string
  trigger_mileage: number
  remaining_km: number
  status: "upcoming" | "due" | "overdue"
  scheduled_date: string
  auto_scheduled: boolean
}

function predictMaintenance(
  assetId: string,
  assetName: string,
  currentMileage: number
): MaintenancePrediction[] {
  const predictions: MaintenancePrediction[] = []
  
  const sortedThresholds = Object.entries(MAINTENANCE_THRESHOLDS)
    .sort(([, a], [, b]) => a - b)
  
  for (const [maintenanceType, threshold] of sortedThresholds) {
    const cycleNumber = Math.floor(currentMileage / threshold)
    const nextThreshold = (cycleNumber + 1) * threshold
    const remainingKm = nextThreshold - currentMileage
    
    let status: "upcoming" | "due" | "overdue" = "upcoming"
    if (remainingKm <= 0) {
      status = "overdue"
    } else if (remainingKm <= threshold * 0.1) {
      status = "due"
    }
    
    const avgDailyMileage = 200
    const daysUntilDue = remainingKm > 0 ? Math.ceil(remainingKm / avgDailyMileage) : 0
    const scheduledDate = new Date()
    scheduledDate.setDate(scheduledDate.getDate() + daysUntilDue)
    
    predictions.push({
      asset_id: assetId,
      asset_name: assetName,
      current_mileage: currentMileage,
      maintenance_type: maintenanceType,
      trigger_mileage: nextThreshold,
      remaining_km: remainingKm,
      status,
      scheduled_date: scheduledDate.toISOString().split("T")[0],
      auto_scheduled: status === "due" || status === "overdue"
    })
  }
  
  return predictions
}

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const assetId = searchParams.get("asset_id")
    
    let query = supabase
      .from("fixed_assets")
      .select("id, name, asset_type, series, mileage, wialon_id, wialon_online, wialon_last_sync")
      .in("asset_type", ["locomotive", "diesel"])
    
    if (assetId) {
      query = query.eq("id", assetId)
    }
    
    const { data: assets, error } = await query.order("name")
    
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 })
    }
    
    const results = []
    
    for (const asset of assets || []) {
      const currentMileage = parseInt(asset.mileage || "0") || 0
      const predictions = predictMaintenance(asset.id, asset.name, currentMileage)
      
      const dueOrOverdue = predictions.filter(p => p.status === "due" || p.status === "overdue")
      
      for (const prediction of dueOrOverdue) {
        const { error: upsertError } = await supabase
          .from("maintenance_plan")
          .upsert({
            asset_id: prediction.asset_id,
            asset_name: prediction.asset_name,
            maintenance_type: prediction.maintenance_type,
            status: "Scheduled",
            trigger_mileage: prediction.trigger_mileage,
            scheduled_date: prediction.scheduled_date,
          }, { 
            onConflict: "asset_id,maintenance_type,trigger_mileage" 
          })
        
        if (upsertError) {
          console.error("Failed to upsert maintenance plan:", upsertError)
        }
      }
      
      results.push({
        asset,
        predictions,
        alerts: dueOrOverdue.map(p => ({
          type: p.status === "overdue" ? "error" : "warning",
          message: `${asset.name}: ${p.maintenance_type} ${p.status === "overdue" ? "просрочен" : `через ${p.remaining_km.toLocaleString()} км`}`
        }))
      })
    }
    
    return NextResponse.json({
      success: true,
      data: results,
      total: results.length,
      timestamp: new Date().toISOString()
    })
    
  } catch (error) {
    console.error("Mileage API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { asset_id, mileage } = body
    
    if (!asset_id || mileage === undefined) {
      return NextResponse.json(
        { error: "asset_id and mileage are required" },
        { status: 400 }
      )
    }
    
    const { data: asset, error: fetchError } = await supabase
      .from("fixed_assets")
      .select("id, name, asset_type, mileage")
      .eq("id", asset_id)
      .single()
    
    if (fetchError || !asset) {
      return NextResponse.json(
        { error: "Asset not found" },
        { status: 404 }
      )
    }
    
    const { error: updateError } = await supabase
      .from("fixed_assets")
      .update({ 
        mileage: mileage.toString(),
        wialon_last_sync: new Date().toISOString()
      })
      .eq("id", asset_id)
    
    if (updateError) {
      return NextResponse.json(
        { error: updateError.message },
        { status: 500 }
      )
    }
    
    const predictions = predictMaintenance(asset.id, asset.name, mileage)
    const dueOrOverdue = predictions.filter(p => p.status === "due" || p.status === "overdue")
    
    for (const prediction of dueOrOverdue) {
      await supabase
        .from("maintenance_plan")
        .upsert({
          asset_id: prediction.asset_id,
          asset_name: prediction.asset_name,
          maintenance_type: prediction.maintenance_type,
          status: "Scheduled",
          trigger_mileage: prediction.trigger_mileage,
          scheduled_date: prediction.scheduled_date,
        }, { 
          onConflict: "asset_id,maintenance_type,trigger_mileage" 
        })
    }
    
    return NextResponse.json({
      success: true,
      asset_id,
      new_mileage: mileage,
      predictions,
      alerts: dueOrOverdue.map(p => ({
        type: p.status === "overdue" ? "error" : "warning",
        title: p.status === "overdue" ? "Требуется ремонт!" : "Приближение к ТО",
        message: `${asset.name}: ${p.maintenance_type} ${p.status === "overdue" ? "просрочен" : `через ${p.remaining_km.toLocaleString()} км`}`
      }))
    })
    
  } catch (error) {
    console.error("Mileage POST error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}
