import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const status = searchParams.get("status")
    const assetId = searchParams.get("asset_id")
    
    let query = supabase
      .from("maintenance_plan")
      .select(`
        *,
        fixed_assets (
          id,
          name,
          asset_type,
          series,
          mileage,
          wialon_online
        )
      `)
      .order("scheduled_date", { ascending: true })
    
    if (status) {
      query = query.eq("status", status)
    }
    
    if (assetId) {
      query = query.eq("asset_id", assetId)
    }
    
    const { data: plans, error } = await query
    
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 })
    }
    
    const enrichedPlans = (plans || []).map((plan: {
      id: string
      asset_id: string
      asset_name: string
      maintenance_type: string
      status: string
      trigger_mileage: number
      scheduled_date: string
      created_at: string
      fixed_assets: { mileage: string } | null
    }) => {
      const currentMileage = parseInt(plan.fixed_assets?.mileage || "0") || 0
      const remainingKm = plan.trigger_mileage - currentMileage
      
      let urgency: "normal" | "warning" | "critical" | "overdue" = "normal"
      if (remainingKm <= 0) urgency = "overdue"
      else if (remainingKm <= 500) urgency = "critical"
      else if (remainingKm <= 1000) urgency = "warning"
      
      return {
        ...plan,
        current_mileage: currentMileage,
        remaining_km: remainingKm,
        urgency
      }
    })
    
    return NextResponse.json({
      success: true,
      data: enrichedPlans,
      total: enrichedPlans.length,
      summary: {
        scheduled: enrichedPlans.filter((p: { status: string }) => p.status === "Scheduled").length,
        inProgress: enrichedPlans.filter((p: { status: string }) => p.status === "InProgress").length,
        overdue: enrichedPlans.filter((p: { urgency: string }) => p.urgency === "overdue").length,
        critical: enrichedPlans.filter((p: { urgency: string }) => p.urgency === "critical").length
      }
    })
    
  } catch (error) {
    console.error("Maintenance plan API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { asset_id, asset_name, maintenance_type, trigger_mileage, scheduled_date } = body
    
    if (!asset_id || !maintenance_type || !trigger_mileage) {
      return NextResponse.json(
        { error: "asset_id, maintenance_type, and trigger_mileage are required" },
        { status: 400 }
      )
    }
    
    const { data, error } = await supabase
      .from("maintenance_plan")
      .upsert({
        asset_id,
        asset_name: asset_name || "",
        maintenance_type,
        status: "Scheduled",
        trigger_mileage,
        scheduled_date: scheduled_date || new Date().toISOString().split("T")[0]
      }, {
        onConflict: "asset_id,maintenance_type,trigger_mileage"
      })
      .select()
      .single()
    
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 })
    }
    
    return NextResponse.json({
      success: true,
      data,
      message: "Maintenance plan created/updated successfully"
    })
    
  } catch (error) {
    console.error("Maintenance plan POST error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json()
    const { id, status, completed_date, notes } = body
    
    if (!id) {
      return NextResponse.json(
        { error: "id is required" },
        { status: 400 }
      )
    }
    
    const updateData: Record<string, unknown> = { updated_at: new Date().toISOString() }
    if (status) updateData.status = status
    if (completed_date) updateData.completed_date = completed_date
    if (notes !== undefined) updateData.notes = notes
    
    const { data, error } = await supabase
      .from("maintenance_plan")
      .update(updateData)
      .eq("id", id)
      .select()
      .single()
    
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 })
    }
    
    return NextResponse.json({
      success: true,
      data,
      message: "Maintenance plan updated successfully"
    })
    
  } catch (error) {
    console.error("Maintenance plan PATCH error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}
