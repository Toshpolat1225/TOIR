import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

const MAINTENANCE_THRESHOLDS = [5000, 15000, 30000, 100000, 200000, 400000, 800000, 1600000]

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const assetId = searchParams.get("asset_id")
    const limit = parseInt(searchParams.get("limit") || "100")
    const days = parseInt(searchParams.get("days") || "30")
    
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - days)
    
    let query = supabase
      .from("mileage_history")
      .select(`
        id,
        asset_id,
        mileage,
        recorded_at,
        source,
        fixed_assets (
          id,
          name,
          asset_type,
          series
        )
      `)
      .gte("recorded_at", startDate.toISOString())
      .order("recorded_at", { ascending: true })
      .limit(limit)
    
    if (assetId) {
      query = query.eq("asset_id", assetId)
    }
    
    const { data: history, error } = await query
    
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 })
    }
    
    const chartData = (history || []).map((h: {
      id: string
      asset_id: string
      mileage: number
      recorded_at: string
      source: string
      fixed_assets: { id: string; name: string; asset_type: string; series: string } | null
    }) => {
      const mileage = h.mileage
      const nearestThreshold = MAINTENANCE_THRESHOLDS.find(t => 
        mileage >= t * 0.9 && mileage <= t * 1.1
      )
      const isOverThreshold = MAINTENANCE_THRESHOLDS.some(t => 
        mileage >= t && mileage < t * 1.05
      )
      
      return {
        id: h.id,
        date: new Date(h.recorded_at).toLocaleDateString("ru-RU"),
        datetime: h.recorded_at,
        mileage: h.mileage,
        asset_id: h.asset_id,
        asset_name: h.fixed_assets?.name || "Unknown",
        asset_type: h.fixed_assets?.asset_type,
        threshold: nearestThreshold,
        isOverThreshold,
        source: h.source
      }
    })
    
    const groupedByAsset = chartData.reduce((acc: Record<string, typeof chartData>, item) => {
      if (!acc[item.asset_id]) {
        acc[item.asset_id] = []
      }
      acc[item.asset_id].push(item)
      return acc
    }, {})
    
    return NextResponse.json({
      success: true,
      data: chartData,
      grouped: groupedByAsset,
      thresholds: MAINTENANCE_THRESHOLDS,
      total: chartData.length,
      period: {
        start: startDate.toISOString(),
        end: new Date().toISOString(),
        days
      }
    })
    
  } catch (error) {
    console.error("Mileage history API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}
