"use client"

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { AlertTriangle, Calendar, Wrench } from "@/components/ui/icons"
import { api, type PartsHorizon, type RepairForecast } from "@/lib/api"
import { fmtInt } from "@/lib/format"
import { ASSET_TYPE_LABEL, COHORT_LABEL, daysText, forecastConclusion, HORIZONS } from "@/lib/parts-analytics"
import { CustomTooltip, StatCard } from "./AnalyticsElements"
import { Body, Conclusion, Panel, THR, TH, useRemote } from "./parts-ui"

const GRID = { strokeDasharray: "3 3", stroke: "#9ca3af", strokeOpacity: 0.25 }
const TICK = { fontSize: 11, fill: "#9ca3af" }

export function ForecastCard({ horizon, sectionId, enabled }: { horizon: PartsHorizon; sectionId: string | null; enabled: boolean }) {
  const remote = useRemote<RepairForecast>(
    `${horizon}|${sectionId ?? ""}`,
    () => api.analytics.repairForecast({ horizon, section_id: sectionId ?? undefined, include_cycles: true }),
    enabled,
  )
  const label = HORIZONS.find((h) => h.value === horizon)?.label ?? horizon

  return (
    <Panel title="Что придёт в ремонт" hint={`Горизонт: ${label}. Плановые и расчётные (повторы по интервалу) ремонты`} icon={Wrench}>
      <Body remote={remote} empty={(f) => f.summary.total === 0 && f.upcoming.length === 0}>
        {(f) => {
          const chart = f.items.slice(0, 12).map((i) => ({ name: i.interval_code, ...i.by_asset_type }))
          return (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatCard title="Всего ремонтов" value={fmtInt(f.summary.total)} subtitle={`до ${f.date_to}`} icon={Wrench} color="indigo" />
                <StatCard title="По плану" value={fmtInt(f.summary.planned)} subtitle="реальные строки плана" icon={Calendar} color="blue" />
                <StatCard title="Расчётные" value={fmtInt(f.summary.projected)} subtitle="повторы интервалов (оценка)" icon={Calendar} color="purple" />
                <StatCard title="Просрочено" value={fmtInt(f.summary.overdue)} subtitle="плановые, дата прошла" icon={AlertTriangle} color={f.summary.overdue > 0 ? "red" : "green"} colorValue />
              </div>

              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                <div className="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
                  <p className="mb-1 text-[11px] font-semibold text-gray-600 dark:text-gray-300">По видам ремонта и типу техники</p>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={chart}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey="name" tick={TICK} />
                      <YAxis tick={TICK} width={48} tickFormatter={(v: number) => fmtInt(v)} />
                      <Tooltip content={<CustomTooltip format={(v: number) => fmtInt(v)} />} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="locomotive" name={ASSET_TYPE_LABEL.locomotive} stackId="a" fill="#6366f1" />
                      <Bar dataKey="diesel" name={ASSET_TYPE_LABEL.diesel} stackId="a" fill="#06b6d4" />
                      <Bar dataKey="wagon" name={ASSET_TYPE_LABEL.wagon} stackId="a" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                    {(["new", "middle", "old", "unknown"] as const).map((k) => (
                      <span key={k} className="rounded-md bg-gray-100 px-1.5 py-0.5 text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                        {COHORT_LABEL[k]}: <b>{fmtInt(f.summary.by_age[k])}</b>
                      </span>
                    ))}
                  </div>
                </div>

                <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 dark:bg-gray-800">
                      <tr><th className={TH}>Ремонт</th><th className={THR}>План</th><th className={THR}>Расчёт</th><th className={THR}>Новые</th><th className={THR}>Средн.</th><th className={THR}>Старые</th></tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {f.items.map((i) => (
                        <tr key={i.interval_code}>
                          <td className="px-2 py-1.5 font-medium text-gray-900 dark:text-white">{i.interval_name || i.interval_code}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{fmtInt(i.planned)}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums text-violet-600 dark:text-violet-300">{fmtInt(i.projected)}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{fmtInt(i.by_age.new)}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{fmtInt(i.by_age.middle)}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{fmtInt(i.by_age.old + i.by_age.unknown)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {f.upcoming.length > 0 && (
                <div className="mt-3">
                  <p className="mb-1 text-[11px] font-semibold text-gray-600 dark:text-gray-300">Ближайшие плановые ремонты</p>
                  <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {f.upcoming.slice(0, 8).map((u) => (
                      <li key={`${u.asset_id}-${u.interval_code}-${u.scheduled_date}`} className={`flex items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-xs ${u.overdue
                        ? "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30"
                        : "border-gray-200 dark:border-gray-700"}`}>
                        <span className="min-w-0 truncate"><b>{u.inv_number}</b> · {u.interval_name || u.interval_code}</span>
                        <span className={`shrink-0 tabular-nums ${u.overdue ? "font-semibold text-red-600 dark:text-red-400" : "text-gray-500"}`}>{u.scheduled_date} · {daysText(u.overdue ? -Math.abs(u.days_left) : u.days_left)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Conclusion>{forecastConclusion(f, label)}</Conclusion>
            </>
          )
        }}
      </Body>
    </Panel>
  )
}
