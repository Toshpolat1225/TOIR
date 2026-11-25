"use client"

import { AlertTriangle, TrendingUp } from "@/components/ui/icons"
import { api, type PartsConsumption } from "@/lib/api"
import { fmtMoney, fmtNumber } from "@/lib/format"
import { ASSET_TYPE_LABEL, savingConclusion, trendView } from "@/lib/parts-analytics"
import { StatCard } from "./AnalyticsElements"
import { Body, Conclusion, Panel, useRemote } from "./parts-ui"

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="text-[10px] text-gray-400">—</span>
  const w = 96
  const h = 26
  const max = Math.max(...values, 1)
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - (v / max) * (h - 4)}`).join(" ")
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-6 w-24 shrink-0" role="img" aria-label="Расход по месяцам">
      <polyline points={pts} fill="none" stroke="#8b5cf6" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export function ConsumptionCard({ sectionId, enabled }: { sectionId: string | null; enabled: boolean }) {
  const remote = useRemote<PartsConsumption>(
    sectionId ?? "",
    () => api.analytics.partsConsumption({ months: 8, section_id: sectionId ?? undefined, limit: 30 }),
    enabled,
  )

  return (
    <Panel title="Что расходуется быстрее всего" hint="По выданным документам ТМЦ за 8 месяцев, ранг по сумме" icon={TrendingUp}>
      <Body remote={remote} empty={(c) => c.items.length === 0}>
        {(c) => {
          const growing = new Set(c.fastest_growing)
          return (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <StatCard title="Расход за период" value={fmtMoney(c.totals.cost)} unit="сум" subtitle={`с ${c.date_from}, позиций: ${c.totals.items}`} icon={TrendingUp} color="indigo" />
                <StatCard title="Потенциал экономии" value={fmtMoney(c.totals.overuse_cost)} unit="сум" subtitle="расход сверх нормы" icon={AlertTriangle} color={c.totals.overuse_cost > 0 ? "red" : "green"} colorValue />
              </div>

              <ol className="mt-3 space-y-2">
                {c.items.slice(0, 10).map((i) => {
                  const t = trendView(i.trend, i.trend_pct)
                  return (
                    <li key={i.nomenclature_id} className="rounded-lg border border-gray-200 p-2.5 dark:border-gray-700">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-100 text-[11px] font-bold text-violet-700 dark:bg-violet-900/60 dark:text-violet-200">{i.rank}</span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-semibold text-gray-900 dark:text-white" title={i.name}>
                            {i.name}
                            {growing.has(i.nomenclature_id) && <span className="ml-1.5 rounded bg-red-100 px-1 py-0.5 text-[9px] text-red-700 dark:bg-red-900/60 dark:text-red-200">быстрый рост</span>}
                          </p>
                          <p className="text-[10px] text-gray-500">
                            {fmtNumber(i.total_qty)} {i.unit} · {fmtMoney(i.total_cost)} сум · в среднем {fmtNumber(i.monthly_avg)} {i.unit}/мес
                          </p>
                        </div>
                        <Sparkline values={i.series.map((s) => s.qty)} />
                        <span className={`w-20 shrink-0 text-right text-xs font-semibold tabular-nums ${t.cls}`}>{t.arrow} {t.text}</span>
                      </div>
                      {(i.top_work_types.length > 0 || i.top_asset_types.length > 0 || i.over_cost > 0) && (
                        <div className="mt-1.5 flex flex-wrap gap-1.5 pl-8 text-[10px]">
                          {i.top_work_types.slice(0, 2).map((w) => (
                            <span key={w.work_type} className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700 dark:bg-gray-800 dark:text-gray-300">{w.work_type}: <b>{fmtNumber(w.qty)}</b></span>
                          ))}
                          {i.top_asset_types.slice(0, 2).map((a) => (
                            <span key={a.asset_type} className="rounded bg-violet-50 px-1.5 py-0.5 text-violet-700 dark:bg-violet-950/50 dark:text-violet-200">{ASSET_TYPE_LABEL[a.asset_type] ?? a.asset_type}: <b>{fmtNumber(a.qty)}</b></span>
                          ))}
                          {i.over_cost > 0 && <span className="rounded bg-red-50 px-1.5 py-0.5 font-semibold text-red-700 dark:bg-red-950/50 dark:text-red-300">сверх нормы: {fmtNumber(i.over_qty)} {i.unit} · {fmtMoney(i.over_cost)}</span>}
                        </div>
                      )}
                    </li>
                  )
                })}
              </ol>
              {c.note && <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">{c.note}</p>}
              <Conclusion>{savingConclusion(c)}</Conclusion>
            </>
          )
        }}
      </Body>
    </Panel>
  )
}
