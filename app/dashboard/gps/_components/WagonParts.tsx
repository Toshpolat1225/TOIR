"use client"

// Visuals of the wagon pages: the honest banner, the segment timeline (hand-drawn SVG) and the candidates legend.
import { CONFIDENCE_COLOR, basisLabel, timelineBars } from "@/lib/gps-analytics"
import { dayShort, timeText, type WagonSegment } from "@/lib/gps-view"

export function WagonBanner({ historyFrom }: { historyFrom?: string | null }) {
  return (
    <aside className="rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-100" data-testid="wagons-banner" role="note">
      <b>У вагонов нет собственного GPS.</b> Ни Wialon, ни GTK не отслеживают вагон: положение и пробег <b>выводятся из локомотива</b>, который вёз состав, пока вагон числился в нём по данным GTK.
      Каждая цифра ниже помечена основанием и уверенностью.
      {historyFrom ? <> История состава GTK начинается с <b>{timeText(historyFrom)}</b>: раньше этой даты вагон нельзя привязать к локомотиву, и пробег за те дни не восстанавливается.</> : null}
    </aside>
  )
}

/** One lane per train; a bar per segment coloured by its confidence. */
export function SegmentTimeline({ segments, width = 900 }: { segments: WagonSegment[]; width?: number }) {
  if (segments.length === 0) return <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">За период вагон не числился ни в одном составе</div>
  const { bars, fromMs, toMs } = timelineBars(segments, width)
  const lanes = [...new Set(segments.map((s) => s.train_gtk_id))]
  const H = 28, pad = 22
  const height = pad + lanes.length * H + 6
  const fmt = (ms: number) => dayShort(new Date(ms).toISOString())
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Временная шкала сегментов вагона" data-testid="wagon-timeline">
      <text x={0} y={12} className="fill-gray-500 text-[10px]">{fmt(fromMs)}</text>
      <text x={width} y={12} textAnchor="end" className="fill-gray-500 text-[10px]">{fmt(toMs)}</text>
      <line x1={0} x2={width} y1={16} y2={16} className="stroke-gray-200 dark:stroke-gray-700" />
      {bars.map((b) => {
        const s = segments[b.index]
        const lane = lanes.indexOf(s.train_gtk_id)
        const y = pad + lane * H
        return (
          <g key={`${s.train_gtk_id}-${s.period_from}`}>
            <rect x={b.x} y={y} width={b.w} height={H - 8} rx={5} fill={CONFIDENCE_COLOR[s.confidence] ?? "#94a3b8"} opacity={s.open ? 0.75 : 0.95} stroke={s.open ? "#0f172a" : "none"} strokeDasharray={s.open ? "4 3" : undefined}>
              <title>{`Состав ${s.train_number ?? s.train_gtk_id} · ${s.loco_inv_number ?? "локомотив неизвестен"} · ${timeText(s.period_from)} – ${s.open ? "сейчас" : timeText(s.period_to)} · ${basisLabel(s.basis)}`}</title>
            </rect>
            {b.w > 56 && <text x={b.x + 6} y={y + 13} className="fill-white text-[10px] font-semibold">{`№ ${s.train_number ?? s.train_gtk_id}`}</text>}
          </g>
        )
      })}
    </svg>
  )
}

export const CANDIDATES: { key: "a" | "b" | "c" | "d"; field: "km_odometer" | "km_wialon" | "km_gtk" | "km_fused"; title: string; hint: string }[] = [
  { key: "a", field: "km_odometer", title: "A · Одометр", hint: "Приращение одометра локомотива между началом и концом периода (с интерполяцией между показаниями)." },
  { key: "b", field: "km_wialon", title: "B · Трек Wialon", hint: "Длина сохранённого трека Wialon за период." },
  { key: "c", field: "km_gtk", title: "C · Трек GTK", hint: "Длина сохранённого трека GTK за период." },
  { key: "d", field: "km_fused", title: "D · Единый трек", hint: "Wialon с заполнением провалов точками GTK." },
]

export function CandidatesLegend() {
  return (
    <dl className="grid gap-2 text-sm sm:grid-cols-2">
      {CANDIDATES.map((c) => (
        <div key={c.key}><dt className="font-semibold text-gray-900 dark:text-white">{c.title}</dt><dd className="text-xs text-gray-600 dark:text-gray-300">{c.hint}</dd></div>
      ))}
    </dl>
  )
}
