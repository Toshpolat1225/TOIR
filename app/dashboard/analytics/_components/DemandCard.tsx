"use client"

import { DollarSign, Package } from "@/components/ui/icons"
import { api, type PartsDemand, type StockRiskItem } from "@/lib/api"
import { fmtInt, fmtMoney, fmtNumber } from "@/lib/format"
import { daysText, stockCoverDays } from "@/lib/parts-analytics"
import { StatCard } from "./AnalyticsElements"
import { Body, Conclusion, Panel, TH, THR, useRemote } from "./parts-ui"

export function DemandCard({ sectionId, enabled, stock }: { sectionId: string | null; enabled: boolean; stock: StockRiskItem[] | null }) {
  const remote = useRemote<PartsDemand>(
    sectionId ?? "",
    () => api.analytics.partsDemand({ horizon: "all", section_id: sectionId ?? undefined, include_cycles: true, limit: 100 }),
    enabled,
  )
  const stockById = new Map((stock ?? []).map((s) => [s.nomenclature_id, s]))

  return (
    <Panel title="Потребность в запчастях" hint="Сколько и на какую сумму нужно на квартал, полгода и год" icon={Package}>
      <Body remote={remote} empty={(d) => d.items.length === 0}>
        {(d) => (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatCard title="На квартал" value={fmtMoney(d.summary.cost_quarter)} unit="сум" subtitle="90 дней" icon={DollarSign} color="indigo" />
              <StatCard title="На полгода" value={fmtMoney(d.summary.cost_half)} unit="сум" subtitle="180 дней" icon={DollarSign} color="purple" />
              <StatCard title="На год" value={fmtMoney(d.summary.cost_year)} unit="сум" subtitle="365 дней" icon={DollarSign} color="blue" />
            </div>

            <div className="mt-3 overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
              <table className="w-full min-w-[640px] text-xs">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className={TH}>Позиция</th>
                    <th className={THR}>Квартал</th><th className={THR}>Полгода</th><th className={THR}>Год</th>
                    <th className={THR}>Сумма за год</th><th className={THR}>Хватит на</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {d.items.slice(0, 10).map((i) => {
                    const st = stockById.get(i.nomenclature_id)
                    const cover = st ? stockCoverDays(st) : null
                    return (
                      <tr key={i.nomenclature_id} className="align-top">
                        <td className="max-w-[260px] px-2 py-1.5">
                          <p className="truncate font-medium text-gray-900 dark:text-white" title={i.name}>{i.name}</p>
                          <p className="text-[10px] text-gray-500">{[i.code, i.department].filter(Boolean).join(" · ")}</p>
                          {i.note && <p className="text-[10px] text-amber-700 dark:text-amber-300">{i.note}</p>}
                        </td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtNumber(i.qty_quarter)} {i.unit}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtNumber(i.qty_half)} {i.unit}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtNumber(i.qty_year)} {i.unit}</td>
                        <td className="px-2 py-1.5 text-right font-semibold tabular-nums">{fmtMoney(i.cost_year)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{cover !== null ? daysText(cover) : <span className="text-gray-400">нет остатка</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400">
              <span>Показано 10 из {fmtInt(d.total)} позиций</span>
              {d.summary.items_without_norm > 0 && <span className="text-amber-700 dark:text-amber-300">Позиций без нормы: {fmtInt(d.summary.items_without_norm)}</span>}
              {stock === null && <span>«Хватит на» появится после загрузки остатков (см. карточку «Склад и риск дефицита»).</span>}
            </div>

            {d.norm_gaps.length > 0 && (
              <details className="mt-2 rounded-lg border border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
                <summary className="cursor-pointer font-semibold text-gray-700 dark:text-gray-200">Пробелы в нормах ({fmtInt(d.norm_gaps.length)})</summary>
                <ul className="mt-2 space-y-1 text-gray-600 dark:text-gray-300">
                  {d.norm_gaps.map((g) => (
                    <li key={`${g.interval_code}-${g.department}`}>
                      {g.interval_code}{g.department ? ` (${g.department})` : ""}: {fmtInt(g.repairs_year)} ремонтов за год без нормы расхода. Привяжите интервал к виду работ.
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <Conclusion>
              На год нужно запчастей на {fmtMoney(d.summary.cost_year)} сум, на полгода {fmtMoney(d.summary.cost_half)} сум, на квартал {fmtMoney(d.summary.cost_quarter)} сум.
            </Conclusion>
          </>
        )}
      </Body>
    </Panel>
  )
}
