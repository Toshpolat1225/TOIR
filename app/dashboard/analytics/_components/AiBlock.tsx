"use client"

import type { ReactNode } from "react"
import { AlertTriangle, Brain, CheckCircle, Clock, HeartPulse, Shield, Sparkles, Target, XCircle, Zap } from "@/components/ui/icons"
import { fmtInt, fmtMoney, fmtNumber, fmtPercent } from "@/lib/format"
import type { AiInsight, EquipmentWithRisk, FleetHealth, MlInsight, SectionEfficiency } from "./useAnalyticsData"

type Severity = MlInsight["severity"]

const SEVERITY: Record<Severity, { label: string; badge: string; border: string; bar: string; rank: number }> = {
  critical: { label: "Критично", badge: "bg-red-100 text-red-700 dark:bg-red-900/60 dark:text-red-200", border: "border-l-red-500", bar: "bg-red-500", rank: 4 },
  high: { label: "Высокий", badge: "bg-orange-100 text-orange-700 dark:bg-orange-900/60 dark:text-orange-200", border: "border-l-orange-500", bar: "bg-orange-500", rank: 3 },
  medium: { label: "Средний", badge: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/60 dark:text-yellow-200", border: "border-l-yellow-500", bar: "bg-yellow-500", rank: 2 },
  low: { label: "Низкий", badge: "bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200", border: "border-l-slate-400", bar: "bg-slate-400", rank: 1 },
}

const TYPE = {
  anomaly: { label: "Аномалия", chip: "bg-rose-100 text-rose-700 dark:bg-rose-900/60 dark:text-rose-200", icon: XCircle },
  prediction: { label: "Прогноз", chip: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-200", icon: Clock },
  efficiency: { label: "Эффективность", chip: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-200", icon: CheckCircle },
} as const

const SCENARIO: Record<string, string> = {
  accident: "Происшествие",
  delay: "Задержка ремонта",
  overuse: "Перерасход ТМЦ",
  human_factor: "Человеческий фактор",
}

function dnum(details: Record<string, unknown>, key: string): number | null {
  const value = details[key]
  if (value === null || value === undefined || value === "") return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function dtext(details: Record<string, unknown>, key: string): string {
  const value = details[key]
  return typeof value === "string" || typeof value === "number" ? String(value) : ""
}

/** Exact numbers from insight.details as short "label: value" facts. */
function facts(insight: MlInsight): { label: string; value: string; hot?: boolean }[] {
  const d = insight.details
  const out: { label: string; value: string; hot?: boolean }[] = []
  if (insight.probability > 0) out.push({ label: "Вероятность", value: fmtPercent(insight.probability * 100), hot: insight.probability >= 0.8 })
  const remaining = dnum(d, "remaining_days")
  if (remaining !== null) out.push({ label: "Осталось", value: `${fmtInt(remaining)} дн.`, hot: remaining <= 14 })
  const failKm = dnum(d, "predicted_failure_km")
  if (failKm !== null) out.push({ label: "Отказ на пробеге", value: `${fmtNumber(failKm)} км` })
  const overdue = dnum(d, "overdue_km")
  if (overdue !== null) out.push({ label: `Просрочено ${dtext(d, "interval")}`.trim(), value: `${fmtNumber(overdue)} км`, hot: true })
  const over = dnum(d, "over_factor")
  if (over !== null) out.push({ label: "Расход к норме", value: `×${fmtNumber(over)}`, hot: over >= 1.5 })
  const time = dnum(d, "time_factor")
  if (time !== null) out.push({ label: "Время к норме", value: `×${fmtNumber(time)}`, hot: time >= 1.5 })
  const delay = dnum(d, "delay_days")
  if (delay !== null) out.push({ label: "Задержка", value: `${fmtNumber(delay)} дн.`, hot: delay >= 3 })
  const order = dtext(d, "work_order") || insight.work_order_number
  if (order) out.push({ label: "Наряд", value: order })
  const executor = dtext(d, "executor")
  if (executor) out.push({ label: "Исполнитель", value: executor })
  return out
}

function isPositive(i: MlInsight) {
  return i.details.positive === true || (i.insight_type === "efficiency" && i.severity === "low")
}

function assetLabel(i: MlInsight) {
  return i.asset_name || "Без привязки к технике"
}

function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-violet-200/70 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-violet-900/60 dark:bg-gray-900/70 ${className}`}>
      {children}
    </div>
  )
}

function PanelTitle({ icon: Icon, title, hint, count }: { icon: typeof Brain; title: string; hint?: string; count?: number }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <div className="rounded-lg bg-violet-100 p-1.5 text-violet-600 dark:bg-violet-900/60 dark:text-violet-300">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h4>
        {hint && <p className="text-[11px] text-gray-500 dark:text-gray-400">{hint}</p>}
      </div>
      {count !== undefined && (
        <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-bold text-violet-700 dark:bg-violet-900/60 dark:text-violet-200">{count}</span>
      )}
    </div>
  )
}

function FleetRing({ percent }: { percent: number }) {
  const value = Math.max(0, Math.min(100, percent))
  const r = 52
  const c = 2 * Math.PI * r
  const color = value >= 85 ? "#22c55e" : value >= 65 ? "#f59e0b" : "#ef4444"
  return (
    <div className="relative mx-auto h-36 w-36 shrink-0">
      <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90" role="img" aria-label={`Надёжность парка ${fmtPercent(value)}`}>
        <circle cx="64" cy="64" r={r} fill="none" strokeWidth="12" className="stroke-violet-100 dark:stroke-violet-950" />
        <circle cx="64" cy="64" r={r} fill="none" strokeWidth="12" strokeLinecap="round" stroke={color}
          strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} style={{ transition: "stroke-dashoffset 600ms ease" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold tabular-nums text-gray-900 dark:text-white">{fmtPercent(value)}</span>
        <span className="text-[11px] text-gray-500 dark:text-gray-400">надёжность</span>
      </div>
    </div>
  )
}

function InsightCard({ insight }: { insight: MlInsight }) {
  const sev = SEVERITY[insight.severity]
  const type = TYPE[insight.insight_type]
  const TypeIcon = type.icon
  const list = facts(insight)
  const scenario = SCENARIO[dtext(insight.details, "scenario")] ?? ""
  return (
    <div className={`rounded-lg border border-l-4 border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900 ${sev.border} ${insight.is_resolved ? "opacity-60" : ""}`}>
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${type.chip}`}>
          <TypeIcon className="h-3 w-3" />{type.label}
        </span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${sev.badge}`}>{sev.label}</span>
        {scenario && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600 dark:bg-gray-800 dark:text-gray-300">{scenario}</span>}
        {insight.details.accident === true && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] text-red-700 dark:bg-red-900/60 dark:text-red-200">Происшествие</span>}
        {insight.details.human_factor === true && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-900/60 dark:text-amber-200">Человеческий фактор</span>}
        {insight.is_resolved && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500 dark:bg-gray-800">Обработано</span>}
      </div>
      <p className="text-xs font-semibold text-violet-700 dark:text-violet-300">{assetLabel(insight)}</p>
      <p className="mt-0.5 text-xs leading-snug text-gray-800 dark:text-gray-100">{insight.message}</p>
      {list.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {list.map((f) => (
            <span key={f.label} className={`rounded-md px-1.5 py-0.5 text-[10px] ${f.hot
              ? "bg-red-50 font-semibold text-red-700 dark:bg-red-950/50 dark:text-red-300"
              : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"}`}>
              {f.label}: <b>{f.value}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Group({ icon, title, hint, items, empty, limit = 6 }: {
  icon: typeof Brain
  title: string
  hint: string
  items: MlInsight[]
  empty: string
  limit?: number
}) {
  return (
    <Panel>
      <PanelTitle icon={icon} title={title} hint={hint} count={items.length} />
      <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
        {items.length === 0 ? (
          <p className="py-4 text-center text-xs text-gray-400">{empty}</p>
        ) : items.slice(0, limit).map((i) => <InsightCard key={i.id} insight={i} />)}
      </div>
      {items.length > limit && <p className="mt-2 text-center text-[11px] text-gray-500">и ещё {fmtInt(items.length - limit)}</p>}
    </Panel>
  )
}

type Recommendation = { key: string; rank: number; title: string; action: string; facts: { label: string; value: string; hot?: boolean }[]; money?: { value: number; note: string } }

function buildRecommendations(insights: MlInsight[], risk: EquipmentWithRisk[], sections: SectionEfficiency[]): Recommendation[] {
  const out: Recommendation[] = []
  const covered = new Set<string>()
  for (const i of insights) {
    if (i.is_resolved || isPositive(i) || !i.suggested_action) continue
    if (i.asset_id) covered.add(i.asset_id)
    out.push({
      key: `i-${i.id}`,
      rank: SEVERITY[i.severity].rank * 10 + i.probability,
      title: assetLabel(i),
      action: i.suggested_action,
      facts: facts(i).filter((f) => f.label !== "Наряд" && f.label !== "Исполнитель"),
    })
  }
  for (const eq of risk) {
    if (covered.has(eq.id) || eq.failure_probability < 0.5) continue
    out.push({
      key: `r-${eq.id}`,
      rank: (eq.failure_probability >= 0.8 ? 4 : 3) * 10 + eq.failure_probability,
      title: eq.name,
      action: "Провести диагностику и поставить в плановый осмотр",
      facts: [
        { label: "Вероятность отказа", value: fmtPercent(eq.failure_probability * 100), hot: eq.failure_probability >= 0.8 },
        ...(eq.predicted_failure_km > 0 ? [{ label: "Отказ на пробеге", value: `${fmtNumber(eq.predicted_failure_km)} км` }] : []),
        { label: "Индекс здоровья", value: fmtNumber(eq.health_score) },
      ],
    })
  }
  out.sort((a, b) => b.rank - a.rank)
  const top = out.slice(0, 6)
  const overruns = sections.filter((s) => s.total_savings < 0).sort((a, b) => a.total_savings - b.total_savings).slice(0, 3)
  for (const s of overruns) {
    const pct = s.total_norm_cost > 0 ? (-s.total_savings / s.total_norm_cost) * 100 : 0
    top.push({
      key: `s-${s.section_id}`,
      rank: 0,
      title: `Участок ${s.section}`,
      action: "Проверить списание ТМЦ по нарядам с превышением норматива",
      facts: [
        { label: "Превышений", value: fmtInt(s.total_overruns), hot: s.total_overruns > 0 },
        { label: "Факт", value: `${fmtMoney(s.total_actual_cost)} сум` },
        { label: "Норматив", value: `${fmtMoney(s.total_norm_cost)} сум` },
        { label: "К норме", value: fmtPercent(pct, true), hot: true },
      ],
      money: { value: s.total_savings, note: "перерасход относительно норматива" },
    })
  }
  return top
}

export function AiBlock({ loading, fleetHealth, riskEquipment, mlInsights, aiSummary, sections }: {
  loading: boolean
  fleetHealth: FleetHealth | null
  riskEquipment: EquipmentWithRisk[]
  mlInsights: MlInsight[]
  aiSummary: AiInsight[]
  sections: SectionEfficiency[]
}) {
  const shell = "rounded-2xl border border-violet-300/60 bg-gradient-to-br from-violet-50 via-indigo-50 to-white p-4 shadow-md dark:border-violet-800/60 dark:from-violet-950/60 dark:via-indigo-950/40 dark:to-gray-950 sm:p-6"

  if (loading) {
    return (
      <div className={`${shell} animate-pulse`}>
        <div className="mb-4 h-10 w-64 rounded-lg bg-violet-200/60 dark:bg-violet-900/40" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-56 rounded-xl bg-violet-100/70 dark:bg-violet-900/30" />)}
        </div>
      </div>
    )
  }

  const open = mlInsights.filter((i) => !i.is_resolved)
  const bySeverity = (a: MlInsight, b: MlInsight) => SEVERITY[b.severity].rank - SEVERITY[a.severity].rank || b.probability - a.probability
  const problems = mlInsights.filter((i) => i.insight_type === "anomaly" && !isPositive(i)).sort(bySeverity)
  const forecasts = mlInsights.filter((i) => i.insight_type === "prediction").sort(bySeverity)
  const positive = mlInsights.filter(isPositive)
  const recommendations = buildRecommendations(mlInsights, riskEquipment, sections)
  const critical = open.filter((i) => i.severity === "critical" || i.severity === "high").length
  const unresolvedSummary = aiSummary.reduce((sum, i) => sum + Number(i.details.unresolved_count ?? 0), 0)

  return (
    <section className={shell} aria-label="ИИ-Аналитика">
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 p-2.5 text-white shadow">
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">ИИ-Аналитика</h2>
          <p className="text-xs text-gray-600 dark:text-gray-400">Что система обнаружила, что прогнозирует и что рекомендует сделать</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-violet-600 px-3 py-1 font-semibold text-white">Открыто: {fmtInt(open.length || unresolvedSummary)}</span>
          {critical > 0 && <span className="rounded-full bg-red-600 px-3 py-1 font-semibold text-white">Срочно: {fmtInt(critical)}</span>}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel>
          <PanelTitle icon={HeartPulse} title="Здоровье парка" hint="Надёжность оборудования" />
          {fleetHealth ? (
            <>
              <FleetRing percent={fleetHealth.reliability_percent} />
              <div className="mt-4 grid grid-cols-4 gap-2 text-center">
                {[
                  { label: "Норма", value: fleetHealth.healthy_count, cls: "text-green-600 dark:text-green-400" },
                  { label: "Внимание", value: fleetHealth.warning_count, cls: "text-yellow-600 dark:text-yellow-400" },
                  { label: "Риск", value: fleetHealth.risk_count, cls: "text-orange-600 dark:text-orange-400" },
                  { label: "Критично", value: fleetHealth.critical_count, cls: "text-red-600 dark:text-red-400" },
                ].map((c) => (
                  <div key={c.label} className="rounded-lg bg-violet-50 p-2 dark:bg-violet-950/50">
                    <p className={`text-lg font-bold tabular-nums ${c.cls}`}>{fmtInt(c.value)}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400">{c.label}</p>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-center text-[11px] text-gray-500 dark:text-gray-400">
                Всего единиц: {fmtInt(fleetHealth.total_assets)} · средний индекс здоровья {fmtNumber(fleetHealth.avg_health_score)}
              </p>
            </>
          ) : <p className="py-6 text-center text-xs text-gray-400">Нет данных о надёжности парка</p>}
        </Panel>

        <Panel className="lg:col-span-2">
          <PanelTitle icon={Target} title="Топ техники в зоне риска" hint="Вероятность отказа по прогнозу модели" count={riskEquipment.length} />
          {riskEquipment.length === 0 ? (
            <div className="py-6 text-center text-gray-400">
              <Shield className="mx-auto mb-2 h-8 w-8 opacity-50" />
              <p className="text-xs">Нет оборудования в зоне риска</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {riskEquipment.map((eq, idx) => {
                const p = eq.failure_probability
                const bar = p >= 0.7 ? "bg-red-500" : p >= 0.5 ? "bg-orange-500" : "bg-yellow-500"
                const text = p >= 0.7 ? "text-red-600 dark:text-red-400" : p >= 0.5 ? "text-orange-600 dark:text-orange-400" : "text-yellow-600 dark:text-yellow-400"
                return (
                  <li key={eq.id}>
                    <div className="flex items-baseline justify-between gap-3">
                      <p className="min-w-0 truncate text-sm font-semibold text-gray-900 dark:text-white">
                        <span className="mr-2 text-xs text-violet-500">#{idx + 1}</span>{eq.name}
                      </p>
                      <p className={`shrink-0 text-lg font-bold tabular-nums ${text}`}>{fmtPercent(p * 100)}</p>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                      <div className={`h-full rounded-full ${bar}`} style={{ width: `${Math.min(100, p * 100)}%` }} />
                    </div>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                      {eq.predicted_failure_km > 0 ? `Прогноз отказа на пробеге ${fmtNumber(eq.predicted_failure_km)} км` : "Требуется диагностика"}
                      {" · "}индекс здоровья {fmtNumber(eq.health_score)}
                    </p>
                  </li>
                )
              })}
            </ul>
          )}
        </Panel>
      </div>

      {mlInsights.length === 0 ? (
        <Panel className="mt-4">
          <PanelTitle icon={Zap} title="События AI по участкам" hint="Сводка (детальные инсайты недоступны)" />
          {aiSummary.length === 0 ? (
            <p className="py-4 text-center text-xs text-gray-400">Нет уведомлений</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {aiSummary.slice(0, 9).map((i) => (
                <div key={i.id} className={`rounded-lg border border-l-4 border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900 ${SEVERITY[i.severity].border}`}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${TYPE[i.insight_type].chip}`}>{TYPE[i.insight_type].label}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${SEVERITY[i.severity].badge}`}>{SEVERITY[i.severity].label}</span>
                  </div>
                  <p className="mt-1 text-xs text-gray-800 dark:text-gray-100">{i.message}</p>
                  {i.probability > 0 && <p className="mt-1 text-[11px] text-gray-500">Ср. вероятность: <b>{fmtPercent(i.probability * 100)}</b></p>}
                </div>
              ))}
            </div>
          )}
        </Panel>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Group icon={AlertTriangle} title="Что обнаружила система" hint="Проблемы и аномалии по нарядам" items={problems} empty="Проблем не найдено" />
          <Group icon={Clock} title="Прогнозы" hint="Ожидаемые отказы и просроченные ТО" items={forecasts} empty="Прогнозов нет" />
          <Group icon={CheckCircle} title="Хорошие результаты" hint="Что работает лучше нормы" items={positive} empty="Пока нет" />
        </div>
      )}

      <Panel className="mt-4">
        <PanelTitle icon={Brain} title="Рекомендации" hint="Что сделать в первую очередь, с точными цифрами" count={recommendations.length} />
        {recommendations.length === 0 ? (
          <p className="py-4 text-center text-xs text-gray-400">Срочных рекомендаций нет</p>
        ) : (
          <ol className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {recommendations.map((r, idx) => (
              <li key={r.key} className="flex gap-3 rounded-lg border border-violet-100 bg-white p-3 dark:border-violet-900/50 dark:bg-gray-900">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-600 to-indigo-600 text-xs font-bold text-white">{idx + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{r.title}</p>
                  <p className="mt-0.5 text-xs text-gray-700 dark:text-gray-300">{r.action}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {r.facts.map((f) => (
                      <span key={f.label} className={`rounded-md px-1.5 py-0.5 text-[10px] ${f.hot
                        ? "bg-red-50 font-semibold text-red-700 dark:bg-red-950/50 dark:text-red-300"
                        : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"}`}>
                        {f.label}: <b>{f.value}</b>
                      </span>
                    ))}
                  </div>
                  {r.money && (
                    <p className="mt-2 text-xs font-semibold text-red-600 dark:text-red-400">
                      {fmtMoney(r.money.value)} сум <span className="font-normal text-gray-500 dark:text-gray-400">{r.money.note}</span>
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </section>
  )
}
