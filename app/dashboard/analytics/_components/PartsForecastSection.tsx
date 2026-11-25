"use client"

import { useEffect, useRef, useState } from "react"
import { Package } from "@/components/ui/icons"
import { api, type PartsHorizon, type StockRisk } from "@/lib/api"
import { useSectionView } from "@/lib/section-view-context"
import { HORIZONS } from "@/lib/parts-analytics"
import { ConsumptionCard } from "./ConsumptionCard"
import { DemandCard } from "./DemandCard"
import { ForecastCard } from "./ForecastCard"
import { Segmented, useRemote } from "./parts-ui"
import { StockRiskCard } from "./StockRiskCard"

/** Spare-parts forecast. Nothing is requested until the block scrolls into view. */
export function PartsForecastSection() {
  const { effectiveSection } = useSectionView()
  const [horizon, setHorizon] = useState<PartsHorizon>("year")
  const [visible, setVisible] = useState(false)
  const anchor = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const el = anchor.current
    if (!el) return
    if (typeof IntersectionObserver === "undefined") { setVisible(true); return }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setVisible(true); io.disconnect() }
    }, { rootMargin: "300px" })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  const stock = useRemote<StockRisk>(
    effectiveSection ?? "",
    () => api.analytics.stockRisk({ section_id: effectiveSection ?? undefined, limit: 100, include_cycles: true }),
    visible,
  )

  return (
    <section
      ref={anchor}
      aria-label="Запчасти и ремонты: прогноз"
      className="rounded-2xl border border-violet-300/60 bg-gradient-to-br from-violet-50 via-indigo-50 to-white p-4 shadow-md dark:border-violet-800/60 dark:from-violet-950/60 dark:via-indigo-950/40 dark:to-gray-950 sm:p-6"
    >
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 p-2.5 text-white shadow"><Package className="h-5 w-5" /></div>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Запчасти и ремонты: прогноз</h2>
          <p className="text-xs text-gray-600 dark:text-gray-400">Что придёт в ремонт, сколько запчастей понадобится и где грозит дефицит</p>
        </div>
        <Segmented label="Горизонт прогноза" value={horizon} onChange={setHorizon} options={HORIZONS.map((h) => ({ value: h.value, label: h.label }))} />
      </div>

      <div className="grid grid-cols-1 gap-4">
        <ForecastCard horizon={horizon} sectionId={effectiveSection} enabled={visible} />
        <DemandCard sectionId={effectiveSection} enabled={visible} stock={stock.data ? stock.data.items : null} />
        <ConsumptionCard sectionId={effectiveSection} enabled={visible} />
        <StockRiskCard remote={stock} />
      </div>
    </section>
  )
}
