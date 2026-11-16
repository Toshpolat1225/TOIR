"use client"

import type { MaintenanceDisruption, MaintenanceKpis, Section } from "@/lib/api"
import { BLOCK_REASON_LABEL, formatDate } from "@/lib/maintenance-view"

function Card({ label, value, hint, tone }: { label: string; value: string; hint: string; tone: "red" | "amber" | "blue" | "green" | "gray" }) {
  const cls = {
    red: "border-red-200 bg-red-50/60 text-red-700 dark:border-red-900 dark:bg-red-950/20 dark:text-red-300",
    amber: "border-amber-200 bg-amber-50/60 text-amber-800 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-300",
    blue: "border-blue-200 bg-blue-50/60 text-blue-700 dark:border-blue-900 dark:bg-blue-950/20 dark:text-blue-300",
    green: "border-emerald-200 bg-emerald-50/60 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/20 dark:text-emerald-300",
    gray: "border-gray-200 bg-white text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200",
  }[tone]
  return (
    <div className={`rounded-2xl border p-4 ${cls}`}>
      <p className="text-xs font-semibold">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      <p className="mt-1 text-xs opacity-75">{hint}</p>
    </div>
  )
}

function scopeText(disruption: MaintenanceDisruption, sections: Section[], assetLabel: (id: string) => string): string {
  if (disruption.scope === "all") return "всё предприятие"
  if (disruption.scope === "section") return sections.find((section) => section.id === disruption.section_id)?.name ?? "участок"
  return disruption.asset_id ? assetLabel(disruption.asset_id) : "техника"
}

/** Health of the whole plan at a glance, plus the list of open disruptions. */
export function LiveOverview({ kpis, disruptions, sections, assetLabel, canUpdate, busyId, onClose, onCreate }: {
  kpis: MaintenanceKpis | null
  disruptions: MaintenanceDisruption[]
  sections: Section[]
  assetLabel: (id: string) => string
  canUpdate: boolean
  busyId: string | null
  onClose: (id: string) => void
  onCreate: () => void
}) {
  const reached = kpis ? kpis.over_limit + kpis.over_tolerance : 0
  return (
    <section aria-label={"Состояние плана"} className="space-y-3">
      {kpis && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Card tone="red" label={"Лимит достигнут"} value={String(reached)}
            hint={kpis.over_tolerance > 0 ? `из них за допуском: ${kpis.over_tolerance}` : "обязательства, которые уже пора выполнять"} />
          <Card tone="amber" label={"Окно плана открыто"} value={String(kpis.due_soon)} hint={"пора резервировать место и запчасти"} />
          <Card tone="gray" label={"Заблокировано"} value={String(kpis.blocked)} hint={"нет запчастей, бокса или бригады"} />
          <Card tone="blue" label={"Прогноз приблизительный"} value={String(kpis.low_confidence)}
            hint={`точка отсчёта предположительная: ${kpis.provisional_baseline}. Внесите дату последнего ТО`} />
          <Card tone="green" label={"Вовремя за 90 дней"} value={kpis.on_time_pct === null ? "—" : `${kpis.on_time_pct}%`}
            hint={kpis.completed_last_90d ? `${kpis.on_time_last_90d} из ${kpis.completed_last_90d} выполненных` : "выполненных ТО пока нет"} />
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{"Сбои и ограничения"}</h2>
            <p className="text-xs text-gray-500">{"Нет запчастей, бокса или бригады, авария, сбой датчика. Работы блокируются, но не теряются."}</p>
          </div>
          {canUpdate && (
            <button type="button" onClick={onCreate}
              className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
              {"Зафиксировать сбой…"}
            </button>
          )}
        </div>
        {disruptions.length === 0 ? (
          <p className="mt-3 text-xs text-gray-400">{"Открытых сбоев нет."}</p>
        ) : (
          <ul className="mt-3 divide-y divide-gray-100 dark:divide-gray-800">
            {disruptions.map((disruption) => (
              <li key={disruption.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-xs">
                <span className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                  {BLOCK_REASON_LABEL[disruption.kind] ?? disruption.kind}
                </span>
                <span className="font-medium text-gray-800 dark:text-gray-100">{scopeText(disruption, sections, assetLabel)}</span>
                <span className="text-gray-500">
                  {`${formatDate(disruption.starts_on)} — ${disruption.ends_on ? formatDate(disruption.ends_on) : "пока не закроют"}`}
                </span>
                <span className="text-gray-500">{`заблокировано планов: ${disruption.affected_plans}`}</span>
                {disruption.note && <span className="text-gray-500">{`· ${disruption.note}`}</span>}
                {canUpdate && (
                  <button type="button" disabled={busyId === disruption.id} onClick={() => onClose(disruption.id)}
                    className="ml-auto rounded-lg border border-gray-300 px-2.5 py-1 font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
                    {busyId === disruption.id ? "Закрываю…" : "Закрыть сбой"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
