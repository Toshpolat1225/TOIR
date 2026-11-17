"use client"

// Hand-drawn SVG/CSS visuals of the weighing-scale screens: no chart library, so every shape can carry the railway meaning.
import Link from "next/link"
import {
  axisTicks, dayFraction, dayLabel, deltaText, deltaTone, durationMinutes, fillRatio, fmt, n, postColor, trainHref, wagonHref,
  type DayPoint, type HourPoint, type LaneTrain, type Num, type UnitRow, type WorkDayPoint,
} from "@/lib/scales-insights"

// ───────────────────────── small parts ─────────────────────────
export function Delta({ delta, invert = false }: { delta: number | null; invert?: boolean }) {
  const tone = deltaTone(delta)
  const good = tone === "flat" ? null : (tone === "up") !== invert
  const color = good === null ? "text-white/60" : good ? "text-emerald-300" : "text-rose-300"
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${color}`} title={deltaText(delta)}>
      {tone === "up" ? "▲" : tone === "down" ? "▼" : "■"} {delta === null ? "—" : `${delta > 0 ? "+" : ""}${Math.round(delta)}%`}
    </span>
  )
}

export function Sparkline({ values, color = "#60a5fa", height = 36 }: { values: number[]; color?: string; height?: number }) {
  if (values.length < 2) return <div style={{ height }} className="text-xs text-white/40">мало данных</div>
  const w = 120
  const max = Math.max(...values, 1)
  const step = w / (values.length - 1)
  const pts = values.map((v, i) => [i * step, height - 3 - (v / max) * (height - 8)] as const)
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ")
  const id = `sp-${color.replace("#", "")}-${values.length}`
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="w-full" style={{ height }} preserveAspectRatio="none" role="img" aria-label="динамика">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.45" /><stop offset="100%" stopColor={color} stopOpacity="0" /></linearGradient>
      </defs>
      <path d={`${line} L${w},${height} L0,${height} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.6" fill={color} />
    </svg>
  )
}

export function Legend({ codes, label }: { codes: string[]; label: (code: string) => string }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-gray-600 dark:text-gray-400">
      {codes.map((c) => <span key={c} className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: postColor(c, codes) }} />{label(c)}</span>)}
    </div>
  )
}

const axisTonnes = (v: number): string => (v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)} млн` : v >= 1000 ? `${Math.round(v / 1000)} тыс.` : fmt(v))

// ───────────────────────── tonnes by day, stacked by scale ─────────────────────────
export function DailyBars({ points, codes }: { points: DayPoint[]; codes: string[] }) {
  const days = [...new Set(points.map((p) => p.day))].sort()
  if (days.length === 0) return <Empty text="Нет взвешиваний за период" />
  const totals = days.map((d) => points.filter((p) => p.day === d).reduce((s, p) => s + n(p.tonnes), 0))
  const max = Math.max(...totals, 1)
  const W = 720, H = 190, pad = { l: 52, r: 8, t: 10, b: 24 }
  const bw = (W - pad.l - pad.r) / days.length
  const ticks = [0, 0.5, 1].map((f) => ({ y: pad.t + (1 - f) * (H - pad.t - pad.b), v: max * f }))
  const labels = axisTicks(days.map((d, i) => ({ d, i })), 9)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Тонн по дням">
      {ticks.map((t) => (
        <g key={t.y}>
          <line x1={pad.l} x2={W - pad.r} y1={t.y} y2={t.y} className="stroke-gray-200 dark:stroke-gray-800" strokeDasharray="3 4" />
          <text x={pad.l - 6} y={t.y + 3} textAnchor="end" className="fill-gray-500 text-[10px]">{axisTonnes(t.v)}</text>
        </g>
      ))}
      {days.map((d, i) => {
        let y = H - pad.b
        return (
          <g key={d}>
            {codes.map((code) => {
              const p = points.find((x) => x.day === d && x.post_code === code)
              const h = p ? (n(p.tonnes) / max) * (H - pad.t - pad.b) : 0
              y -= h
              return h > 0 ? (
                <rect key={code} x={pad.l + i * bw + bw * 0.12} y={y} width={bw * 0.76} height={h} rx="2" fill={postColor(code, codes)} opacity="0.92">
                  <title>{`${dayLabel(d)} · Весы ${code}: ${fmt(p!.tonnes)} т, ${p!.trains} составов`}</title>
                </rect>
              ) : null
            })}
          </g>
        )
      })}
      {labels.map(({ d, i }) => <text key={d} x={pad.l + i * bw + bw / 2} y={H - 8} textAnchor="middle" className="fill-gray-500 text-[10px]">{dayLabel(d)}</text>)}
    </svg>
  )
}

// ───────────────────────── when the scales are busy: 24 h heat strip per scale ─────────────────────────
export function HourHeat({ points, codes }: { points: HourPoint[]; codes: string[] }) {
  const max = Math.max(...points.map((p) => p.trains), 1)
  return (
    <div className="space-y-2">
      {codes.map((code) => {
        const color = postColor(code, codes)
        return (
          <div key={code} className="flex items-center gap-2">
            <span className="w-14 shrink-0 text-xs text-gray-500">Весы {code}</span>
            <div className="grid flex-1 grid-cols-24 gap-[2px]" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
              {Array.from({ length: 24 }, (_, h) => {
                const p = points.find((x) => x.post_code === code && x.hour === h)
                const share = p ? p.trains / max : 0
                return (
                  <div key={h} className={`h-8 rounded-[3px] ${share ? "" : "bg-gray-100 dark:bg-gray-800"}`} title={`${String(h).padStart(2, "0")}:00 · ${p?.trains ?? 0} составов${p ? `, ${fmt(p.tonnes)} т` : ""}`}
                    style={share ? { background: color, opacity: 0.18 + share * 0.82 } : undefined} />
                )
              })}
            </div>
          </div>
        )
      })}
      <div className="flex pl-16 text-[10px] text-gray-500" style={{ justifyContent: "space-between" }}>
        {[0, 6, 12, 18, 23].map((h) => <span key={h}>{String(h).padStart(2, "0")}:00</span>)}
      </div>
    </div>
  )
}

// ───────────────────────── bars with labels (cargo, excavators, top lists) ─────────────────────────
export function HBars({
  items, color = "#2563eb", unit = "т", hrefOf,
}: { items: { key: string; label: string; value: Num; hint?: string }[]; color?: string; unit?: string; hrefOf?: (key: string) => string | null }) {
  if (items.length === 0) return <Empty text="Нет данных" />
  const max = Math.max(...items.map((i) => n(i.value)), 1)
  return (
    <ul className="space-y-2">
      {items.map((i) => {
        const href = hrefOf?.(i.key) ?? null
        const inner = (
          <>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-medium text-gray-800 dark:text-gray-100">{i.label}</span>
              <span className="shrink-0 tabular-nums text-gray-600 dark:text-gray-300">{fmt(i.value)} {unit}{i.hint ? <span className="ml-2 text-xs text-gray-400">{i.hint}</span> : null}</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
              <div className="h-full rounded-full" style={{ width: `${Math.max(2, (n(i.value) / max) * 100)}%`, background: `linear-gradient(90deg, ${color}, ${color}aa)` }} />
            </div>
          </>
        )
        return <li key={i.key}>{href ? <Link href={href} className="block rounded-md p-1 hover:bg-gray-50 dark:hover:bg-gray-800">{inner}</Link> : <div className="p-1">{inner}</div>}</li>
      })}
    </ul>
  )
}

// ───────────────────────── today on the rails: a 24 h lane per scale ─────────────────────────
const LANE_STATUS: Record<string, string> = { ok: "#10b981", no_loco: "#ef4444", no_gtk_train: "#f59e0b", pending: "#94a3b8", excluded: "#cbd5e1" }

export function DayLanes({ trains, codes }: { trains: LaneTrain[]; codes: string[] }) {
  const nowFraction = dayFraction(new Date().toISOString()) ?? 0
  const maxTonnes = Math.max(...trains.map((t) => n(t.tonnes)), 1)
  return (
    <div className="space-y-3">
      {codes.map((code) => {
        const mine = trains.filter((t) => t.post_code === code)
        return (
          <div key={code} className="flex items-center gap-2">
            <span className="w-14 shrink-0 text-xs text-gray-500">Весы {code}<br /><b className="text-gray-700 dark:text-gray-200">{mine.length}</b></span>
            <div className="relative h-12 flex-1 overflow-hidden rounded-lg bg-slate-100 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800"
              style={{ backgroundImage: "repeating-linear-gradient(90deg, transparent 0, transparent calc(100%/24 - 1px), rgba(100,116,139,.25) calc(100%/24 - 1px), rgba(100,116,139,.25) calc(100%/24))" }}>
              <div className="absolute inset-x-0 top-1/2 h-[3px] -translate-y-1/2 bg-slate-300/80 dark:bg-slate-700" />
              {mine.map((t) => {
                const start = dayFraction(t.started_at)
                if (start === null) return null
                const minutes = durationMinutes(t.started_at, t.finished_at) ?? 8
                const width = Math.max(0.55, (minutes / 1440) * 100)
                const height = 14 + (n(t.tonnes) / maxTonnes) * 26
                return (
                  <Link key={t.id} href={trainHref(t.id)} title={`${new Date(t.started_at!).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} · ${t.loco_number ? `лок. ${t.loco_number}` : "локомотив не указан"} · ${fmt(t.tonnes)} т`}
                    className="absolute top-1/2 -translate-y-1/2 rounded-[3px] ring-1 ring-white/60 transition hover:z-10 hover:scale-y-110 dark:ring-black/40"
                    style={{ left: `${start * 100}%`, width: `${width}%`, height, background: LANE_STATUS[t.match_status] ?? "#94a3b8" }} />
                )
              })}
              <div className="absolute inset-y-0 w-px bg-rose-500" style={{ left: `${nowFraction * 100}%` }} title="сейчас" />
            </div>
          </div>
        )
      })}
      <div className="flex pl-16 text-[10px] text-gray-500" style={{ justifyContent: "space-between" }}>
        {[0, 4, 8, 12, 16, 20, 24].map((h) => <span key={h}>{String(h).padStart(2, "0")}</span>)}
      </div>
      <div className="flex flex-wrap gap-3 pl-16 text-[11px] text-gray-500">
        {[["ok", "распознан"], ["no_gtk_train", "нет состава GTK"], ["no_loco", "локомотив не определён"]].map(([k, l]) => (
          <span key={k} className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: LANE_STATUS[k] }} />{l}</span>
        ))}
        <span className="inline-flex items-center gap-1"><i className="h-3 w-px bg-rose-500" />сейчас · высота блока = тонны</span>
      </div>
    </div>
  )
}

// ───────────────────────── the train as it stood on the scale ─────────────────────────
export function TrainStrip({ units }: { units: UnitRow[] }) {
  if (units.length === 0) return <Empty text="Строки по вагонам не переданы весами" />
  return (
    <div className="overflow-x-auto pb-2">
      <div className="flex min-w-max items-end gap-1.5 px-1">
        {units.map((u, i) => {
          if (u.kind === "traction") {
            return (
              <div key={`${u.position}-${i}`} className="flex w-20 flex-col items-center gap-1" title={`Тяговый агрегат: тара ${fmt(u.tare_t, 1)} т`}>
                <div className="relative h-24 w-full rounded-t-2xl rounded-b-md bg-gradient-to-b from-slate-600 to-slate-800 ring-1 ring-slate-900/40">
                  <div className="absolute inset-x-2 top-2 h-5 rounded bg-sky-200/80" />
                  <div className="absolute inset-x-0 bottom-2 text-center text-lg text-amber-300">⚡</div>
                </div>
                <div className="text-center text-[11px] leading-tight text-gray-500">поз. {u.position}<br />тяга · {fmt(u.tare_t, 0)} т</div>
              </div>
            )
          }
          const ratio = fillRatio(u.net_t, u.capacity_t)
          const over = ratio > 1
          const heavy = ratio > 1.1
          const fill = heavy ? "linear-gradient(#f43f5e,#be123c)" : over ? "linear-gradient(#fbbf24,#d97706)" : "linear-gradient(#34d399,#059669)"
          const body = (
            <>
              <div className="relative h-24 w-full overflow-hidden rounded-md bg-gray-100 ring-1 ring-gray-300 dark:bg-gray-800 dark:ring-gray-700" style={{ clipPath: "polygon(0 0, 100% 0, 92% 100%, 8% 100%)" }}>
                <div className="absolute inset-x-0 bottom-0" style={{ height: `${Math.min(100, ratio * 100)}%`, background: fill }} />
                {over && <div className={`absolute inset-x-0 top-0 h-1.5 ${heavy ? "bg-rose-700" : "bg-amber-600"}`} />}
                <div className="absolute inset-0 flex items-center justify-center text-sm font-semibold text-white mix-blend-normal drop-shadow">{fmt(u.net_t, 0)}</div>
              </div>
              <div className="w-full truncate text-center text-[11px] leading-tight text-gray-600 dark:text-gray-300">
                поз. {u.position}<br />{u.inv_number ?? u.carriage_name ?? <span className="text-gray-400">вагон не определён</span>}
              </div>
            </>
          )
          return u.carriage_gtk_id !== null ? (
            <Link key={`${u.position}-${i}`} href={wagonHref({ asset_id: u.asset_id, carriage_gtk_id: u.carriage_gtk_id })} className="flex w-20 flex-col items-center gap-1 transition hover:-translate-y-1" title={`${fmt(u.net_t, 1)} т из ${fmt(u.capacity_t, 0)} т${over ? ": перегруз" : ""}`}>{body}</Link>
          ) : <div key={`${u.position}-${i}`} className="flex w-20 flex-col items-center gap-1">{body}</div>
        })}
      </div>
      <div className="mt-3 h-1.5 min-w-max rounded-full bg-gradient-to-r from-slate-400 via-slate-300 to-slate-400 opacity-60" />
    </div>
  )
}

// ───────────────────────── work per day for one wagon / locomotive ─────────────────────────
export function WorkBars({ points, color = "#2563eb", unit = "т" }: { points: WorkDayPoint[]; color?: string; unit?: string }) {
  if (points.length === 0) return <Empty text="За период рейсов нет" />
  const max = Math.max(...points.map((p) => n(p.tonnes)), 1)
  return (
    <div className="flex h-28 items-end gap-[3px]" role="img" aria-label="Тонн по дням">
      {points.map((p) => (
        <div key={p.day} className="group relative flex-1 rounded-t-sm" style={{ height: `${Math.max(4, (n(p.tonnes) / max) * 100)}%`, background: `linear-gradient(${color}, ${color}88)` }}
          title={`${dayLabel(p.day)}: ${fmt(p.tonnes)} ${unit}, рейсов: ${p.trips}`} />
      ))}
    </div>
  )
}

export function Empty({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">{text}</div>
}

export function Panel({ title, hint, children, className = "" }: { title: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900 ${className}`}>
      <header className="mb-3"><h2 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h2>{hint && <p className="text-xs text-gray-500 dark:text-gray-400">{hint}</p>}</header>
      {children}
    </section>
  )
}

export function Stat({ label, value, hint, tone = "plain" }: { label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: "plain" | "good" | "warn" | "bad" }) {
  const ring = { plain: "", good: "ring-emerald-200 dark:ring-emerald-900", warn: "ring-amber-200 dark:ring-amber-900", bad: "ring-rose-200 dark:ring-rose-900" }[tone]
  return (
    <div className={`rounded-xl bg-gray-50 p-3 ring-1 ring-gray-200 dark:bg-gray-800/60 dark:ring-gray-700 ${ring}`}>
      <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
      <div className="mt-0.5 text-xl font-bold tabular-nums text-gray-900 dark:text-white">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{hint}</div>}
    </div>
  )
}
