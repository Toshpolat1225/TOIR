"use client"

import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import {
  deltaPercent, fmt, locoHref, n, percent, tonnesCompact, wagonHref, wagonKey, type Overview as OverviewData,
} from "@/lib/scales-insights"
import { flagLabel } from "@/lib/scales-view"
import { Loader2 } from "@/components/ui/icons"
import { DailyBars, DayLanes, Delta, Empty, HBars, HourHeat, Legend, Panel, Sparkline } from "./viz"

const PERIODS = [7, 30, 90] as const

export default function Overview() {
  const [days, setDays] = useState<number>(30)
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.scales.overview(days)
      .then((value) => { if (!cancelled) { setData(value); setError(null) } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить обзор") })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [days])

  const codes = useMemo(() => [...new Set([...(data?.daily ?? []).map((d) => d.post_code), ...(data?.hourly ?? []).map((h) => h.post_code), ...(data?.today ?? []).map((t) => t.post_code)])].sort(), [data])
  const dailyTotals = useMemo(() => {
    const per = new Map<string, number>()
    for (const p of data?.daily ?? []) per.set(p.day, (per.get(p.day) ?? 0) + n(p.tonnes))
    return [...per.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, v]) => v)
  }, [data])

  if (error) return <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>
  if (!data) return <div className="flex items-center gap-2 rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-gray-800 dark:bg-gray-900"><Loader2 className="h-4 w-4 animate-spin" /> Загружаю обзор…</div>

  const k = data.kpi
  const p = data.previous
  const tiles: { label: string; value: string; delta?: number | null; hint?: string; invert?: boolean }[] = [
    { label: "Составов", value: fmt(k.trains), delta: deltaPercent(k.trains, p.trains) },
    { label: "Рейсов вагонов", value: fmt(k.wagon_trips), delta: deltaPercent(k.wagon_trips, p.wagon_trips), hint: `${fmt(k.active_wagons)} разных вагонов` },
    { label: "Средний состав", value: tonnesCompact(k.avg_train_t), delta: k.avg_train_t && p.avg_train_t ? deltaPercent(k.avg_train_t, p.avg_train_t) : null },
    { label: "В среднем на вагон", value: k.avg_car_t ? `${fmt(k.avg_car_t, 1)} т` : "—", hint: "грузоподъёмность 105 т" },
    { label: "Составы с перегрузом", value: percent(k.overload_share), delta: k.overload_share !== null && p.overload_share ? deltaPercent(k.overload_share, p.overload_share) : null, invert: true, hint: "хотя бы один вагон выше 105 т" },
    { label: "Распознано (GTK)", value: percent(k.matched_share), hint: `${fmt(k.active_locos)} локомотивов в работе` },
  ]

  return (
    <div className="space-y-4" data-testid="scales-overview">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-900 p-5 text-white shadow-lg sm:p-7">
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-sky-400/10 blur-3xl" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-3 opacity-30" style={{ backgroundImage: "repeating-linear-gradient(90deg, #fff 0 10px, transparent 10px 22px)" }} />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-sky-200/80">
              <span>Перевезено за {data.days} дн.</span>
              <div className="ml-2 inline-flex overflow-hidden rounded-full ring-1 ring-white/25" role="group" aria-label="Период">
                {PERIODS.map((d) => (
                  <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)} className={`px-3 py-1 text-xs transition ${days === d ? "bg-white text-slate-900" : "text-sky-100 hover:bg-white/10"}`}>{d} дн.</button>
                ))}
              </div>
              {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            </div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-5xl font-extrabold tracking-tight tabular-nums sm:text-6xl" data-testid="hero-tonnes">{tonnesCompact(k.tonnes)}</span>
              <Delta delta={deltaPercent(k.tonnes, p.tonnes)} />
            </div>
            <p className="mt-1 text-sm text-sky-100/80">{data.date_from.split("-").reverse().join(".")} — {data.date_to.split("-").reverse().join(".")} · по двум весам, груз считается по взвешиванию вагонов</p>
          </div>
          <div className="w-full max-w-sm lg:w-80"><Sparkline values={dailyTotals} color="#7dd3fc" height={56} /><p className="mt-1 text-right text-[11px] text-sky-200/70">тонн по дням</p></div>
        </div>
        <div className="relative mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {tiles.map((t) => (
            <div key={t.label} className="rounded-2xl bg-white/10 p-3 ring-1 ring-white/10 backdrop-blur">
              <div className="text-[11px] uppercase tracking-wide text-sky-100/70">{t.label}</div>
              <div className="mt-0.5 text-2xl font-bold tabular-nums">{t.value}</div>
              <div className="mt-0.5 flex items-center gap-2">{t.delta !== undefined && <Delta delta={t.delta} invert={t.invert} />}{t.hint && <span className="text-[11px] text-sky-100/60">{t.hint}</span>}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-5">
        <Panel title="Тонн по дням" hint="цвет = весы (путь)" className="xl:col-span-3">
          <DailyBars points={data.daily} codes={codes} />
          <div className="mt-2"><Legend codes={codes} label={(c) => `Весы ${c}`} /></div>
        </Panel>
        <Panel title="Сегодня на путях" hint="каждый блок — состав: ширина = время взвешивания, высота = тонны; клик откроет состав" className="xl:col-span-2">
          {data.today.length === 0 ? <Empty text="Сегодня взвешиваний ещё не было" /> : <DayLanes trains={data.today} codes={codes} />}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <Panel title="Когда работают весы" hint="составов по часам суток за период">
          <HourHeat points={data.hourly} codes={codes} />
        </Panel>
        <Panel title="Откуда везут (груз / карьер)" hint="тонн за период">
          <HBars items={data.by_cargo.map((c) => ({ key: c.key, label: c.label, value: c.tonnes, hint: `${c.trains} сост.` }))} color="#0ea5e9" />
        </Panel>
        <Panel title="Экскаваторы" hint="кто погрузил больше всего">
          <HBars items={data.by_excavator.slice(0, 8).map((e) => ({ key: e.key, label: e.label, value: e.tonnes, hint: `${e.trains} сост.` }))} color="#a855f7" />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Локомотивы: кто перевёз больше" hint="нажмите, чтобы открыть карточку локомотива: ТО, GPS, вагоны, рейсы">
          <HBars
            color="#2563eb"
            items={data.top_locomotives.map((l) => ({
              key: l.asset_id ?? `n-${l.loco_number}`, label: l.inv_number ? `${l.inv_number} · ${l.model_name ?? "локомотив"}` : `№ ${l.loco_number ?? "?"} (не связан с ОС)`,
              value: l.tonnes, hint: `${l.trains} сост. · ${fmt(l.avg_train_t)} т/сост.`,
            }))}
            hrefOf={(key) => (key.startsWith("n-") ? null : locoHref(key))}
          />
        </Panel>
        <Panel title="Вагоны: больше всего тонн" hint="нажмите, чтобы открыть карточку вагона: рейсы, ТО, наработка с последнего ТО">
          <HBars
            color="#10b981"
            items={data.top_wagons.map((w) => ({ key: wagonKey(w), label: w.label, value: w.tonnes, hint: `${w.trips} рейсов` }))}
            hrefOf={(key) => { const w = data.top_wagons.find((x) => wagonKey(x) === key); return w ? wagonHref(w) : null }}
          />
        </Panel>
      </div>

      <Panel title="Качество данных" hint="что система доверяет, а что оценила или не смогла определить">
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(data.quality.by_status).map(([status, count]) => (
            <span key={status} className="rounded-full bg-gray-100 px-3 py-1 text-gray-700 dark:bg-gray-800 dark:text-gray-200">{({ ok: "распознано", no_loco: "локомотив не определён", no_gtk_train: "нет состава GTK", pending: "в обработке" } as Record<string, string>)[status] ?? status}: <b>{count}</b></span>
          ))}
          {Object.entries(data.quality.flags).sort((a, b) => b[1] - a[1]).map(([flag, count]) => (
            <span key={flag} className="rounded-full bg-amber-50 px-3 py-1 text-amber-800 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900">{flagLabel(flag)}: <b>{count}</b></span>
          ))}
        </div>
        {data.quality.before_gtk_history > 0 && (
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">{data.quality.before_gtk_history} составов за период взвешены раньше, чем GTK начал вести историю составов: по ним известен локомотив и масса, но какие именно вагоны были в составе — нет.</p>
        )}
      </Panel>
    </div>
  )
}
