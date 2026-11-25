"use client"
import { fmtPercent } from "@/lib/format"

// Hand-drawn visuals of the GPS comparison pages: verdict chips, a stacked verdict bar, a pair-of-bars mini chart and the daily km chart.
import {
  DISTANCE_HINT, DISTANCE_LABEL, POSITION_HINT, POSITION_LABEL, POSITION_TONE, DISTANCE_TONE, TONE_CHIP, TONE_COLOR, dayShort, distanceColor, groupedBars,
  kmText, miniBarHeights, positionColor, stackSegments, type DistanceVerdict, type GpsDayRow, type PositionVerdict, type Tone,
} from "@/lib/gps-view"
import {
  BASIS_HINT, CAUSE_HINT, CONFIDENCE_HINT, HEALTH_HINT, FLAG_HINT, basisLabel, basisTone, causeLabel, causeTone, confidenceLabel, flagLabel, flagTone, healthLabel, healthTone,
  isBasis, isCause, isConfidence, isFlag, isHealth,
} from "@/lib/gps-analytics"
import { CONFIDENCE_TONE } from "@/lib/gps-analytics"

export const WIALON_COLOR = "#2563eb"
export const GTK_COLOR = "#f97316"

export function Chip({ tone, children, title, testId }: { tone: Tone; children: React.ReactNode; title?: string; testId?: string }) {
  return <span title={title} data-testid={testId} className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${TONE_CHIP[tone]}`}>{children}</span>
}

export function PositionChip({ verdict }: { verdict: PositionVerdict }) {
  return <Chip tone={POSITION_TONE[verdict]} title={POSITION_HINT[verdict]}>{POSITION_LABEL[verdict]}</Chip>
}

export function DistanceChip({ verdict }: { verdict: DistanceVerdict }) {
  return <Chip tone={DISTANCE_TONE[verdict]} title={DISTANCE_HINT[verdict]}>{DISTANCE_LABEL[verdict]}</Chip>
}

export function CauseChip({ cause, title }: { cause?: string | null; title?: string }) {
  if (!cause) return <span className="text-xs text-gray-400">—</span>
  return <Chip tone={causeTone(cause)} title={title ?? (isCause(cause) ? CAUSE_HINT[cause] : undefined)} testId={`cause-${cause}`}>{causeLabel(cause)}</Chip>
}

export function HealthChip({ health }: { health?: string | null }) {
  if (!health) return <span className="text-xs text-gray-400">—</span>
  return <Chip tone={healthTone(health)} title={isHealth(health) ? HEALTH_HINT[health] : undefined}>{healthLabel(health)}</Chip>
}

export function ConfidenceChip({ level }: { level?: string | null }) {
  if (!level || !isConfidence(level)) return <span className="text-xs text-gray-400">—</span>
  return <Chip tone={CONFIDENCE_TONE[level]} title={CONFIDENCE_HINT[level]}>{confidenceLabel(level)}</Chip>
}

export function FlagChip({ flag }: { flag: string }) {
  return <Chip tone={flagTone(flag)} title={isFlag(flag) ? FLAG_HINT[flag] : undefined}>{flagLabel(flag)}</Chip>
}

export function BasisChip({ basis }: { basis: string }) {
  return <Chip tone={basisTone(basis)} title={isBasis(basis) ? BASIS_HINT[basis] : undefined}>{basisLabel(basis)}</Chip>
}

/** One horizontal bar cut into proportional segments; the legend under it is a list of buttons (when `onPick` is given). */
export function StackBar<K extends string>({
  order, counts, label, color, hint, active, onPick, testIdPrefix,
}: {
  order: K[]; counts: Record<string, number>; label: (k: K) => string; color: (k: K) => string; hint?: (k: K) => string
  active?: string | string[] | null; onPick?: (k: K) => void; testIdPrefix: string
}) {
  const isOn = (k: string) => (Array.isArray(active) ? active.includes(k) : active === k)
  const anyOn = Array.isArray(active) ? active.length > 0 : !!active
  const W = 600
  const segs = stackSegments(order, counts, W)
  const total = order.reduce((s, k) => s + (counts[k] ?? 0), 0)
  return (
    <div>
      {total === 0 ? <div className="h-4 rounded-full bg-gray-100 dark:bg-gray-800" /> : (
        <svg viewBox={`0 0 ${W} 18`} className="h-4 w-full" preserveAspectRatio="none" role="img" aria-label="распределение вердиктов">
          {segs.map((s) => (
            <rect key={s.key} x={s.x} y={0} width={Math.max(0, s.w - 1.5)} height={18} rx={4} fill={color(s.key)} opacity={anyOn && !isOn(s.key) ? 0.3 : 1}>
              <title>{`${label(s.key)}: ${s.value} (${fmtPercent(s.pct)})`}</title>
            </rect>
          ))}
        </svg>
      )}
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1.5 text-xs">
        {order.filter((k) => (counts[k] ?? 0) > 0).map((k) => {
          const body = (
            <>
              <i className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: color(k) }} />
              <span className="text-gray-700 dark:text-gray-200">{label(k)}</span>
              <b className="tabular-nums text-gray-900 dark:text-white">{counts[k]}</b>
            </>
          )
          return (
            <li key={k}>
              {onPick
                ? <button type="button" aria-pressed={isOn(k)} title={hint?.(k)} data-testid={`${testIdPrefix}-${k}`} onClick={() => onPick(k)} className={`inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 ring-1 transition ${isOn(k) ? "bg-gray-100 ring-gray-400 dark:bg-gray-800" : "ring-transparent hover:bg-gray-50 dark:hover:bg-gray-800"}`}>{body}</button>
                : <span title={hint?.(k)} data-testid={`${testIdPrefix}-${k}`} className="inline-flex items-center gap-1.5 px-1.5 py-0.5">{body}</span>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** Wialon (blue) and GTK (orange) km of every day as thin paired bars, oldest on the left. */
export function MiniPair({ days }: { days: GpsDayRow[] }) {
  const ordered = [...days].reverse()
  const h = miniBarHeights(ordered.map((d) => d.wialon_m), ordered.map((d) => d.gtk_m))
  const W = 7 * 2 + 2, H = 28
  const width = Math.max(1, ordered.length) * W
  return (
    <svg viewBox={`0 0 ${width} ${H}`} width={Math.min(150, width * 2.2)} height={H} role="img" aria-label="Пробег по дням: Wialon и GTK">
      {ordered.map((d, i) => (
        <g key={d.day}>
          <rect x={i * W} y={H - h.a[i] * (H - 2)} width={6} height={Math.max(0.5, h.a[i] * (H - 2))} rx={1} fill={WIALON_COLOR} opacity={0.9} />
          <rect x={i * W + 6.5} y={H - h.b[i] * (H - 2)} width={6} height={Math.max(0.5, h.b[i] * (H - 2))} rx={1} fill={GTK_COLOR} opacity={0.9} />
          <title>{`${dayShort(d.day)}: Wialon ${kmText(d.wialon_m)}, GTK ${kmText(d.gtk_m)} · ${DISTANCE_LABEL[d.verdict]}`}</title>
        </g>
      ))}
    </svg>
  )
}

/** Grouped daily-km chart; the strip under each pair is coloured by that day's verdict. */
export function DailyKmChart({ days }: { days: GpsDayRow[] }) {
  const ordered = [...days].reverse()
  const W = 760, H = 220, pad = { l: 54, r: 8, t: 12, b: 38 }
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b
  const { bars, max } = groupedBars(ordered.map((d) => ({ day: d.day, a: d.wialon_m, b: d.gtk_m })), plotW, plotH)
  const slot = ordered.length > 0 ? plotW / ordered.length : plotW
  const step = Math.max(1, Math.ceil(ordered.length / 12))
  if (ordered.length === 0) return <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">Нет дней в периоде</div>
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Пробег по дням: Wialon и GTK" data-testid="gps-daily-chart">
      {[0, 0.5, 1].map((f) => {
        const y = pad.t + (1 - f) * plotH
        return (
          <g key={f}>
            <line x1={pad.l} x2={W - pad.r} y1={y} y2={y} className="stroke-gray-200 dark:stroke-gray-800" strokeDasharray="3 4" />
            <text x={pad.l - 6} y={y + 3} textAnchor="end" className="fill-gray-500 text-[10px]">{kmText(max * f, false)}</text>
          </g>
        )
      })}
      <text x={pad.l - 6} y={pad.t - 3} textAnchor="end" className="fill-gray-400 text-[9px]">км</text>
      <g transform={`translate(${pad.l},${pad.t})`}>
        {bars.map((b, i) => (
          <g key={b.day}>
            <rect {...{ x: b.a.x, y: b.a.y, width: b.a.w, height: Math.max(b.a.h, b.a.v > 0 ? 1 : 0) }} rx={2} fill={WIALON_COLOR}><title>{`${dayShort(b.day)} · Wialon: ${kmText(b.a.v)}`}</title></rect>
            <rect {...{ x: b.b.x, y: b.b.y, width: b.b.w, height: Math.max(b.b.h, b.b.v > 0 ? 1 : 0) }} rx={2} fill={GTK_COLOR}><title>{`${dayShort(b.day)} · GTK: ${kmText(b.b.v)}`}</title></rect>
            <rect x={i * slot + slot * 0.1} y={plotH + 4} width={slot * 0.8} height={5} rx={2.5} fill={distanceColor(ordered[i].verdict)}><title>{`${dayShort(b.day)}: ${DISTANCE_LABEL[ordered[i].verdict]}`}</title></rect>
            {i % step === 0 && <text x={i * slot + slot / 2} y={plotH + 22} textAnchor="middle" className="fill-gray-500 text-[10px]">{dayShort(b.day)}</text>}
          </g>
        ))}
      </g>
    </svg>
  )
}

export function SourceLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-gray-300">
      <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: WIALON_COLOR }} />Wialon</span>
      <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: GTK_COLOR }} />GTK</span>
    </div>
  )
}

export { TONE_COLOR, positionColor }
