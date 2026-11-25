"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import {
  DISTANCE_HINT, DISTANCE_LABEL, POSITION_HINT, POSITION_LABEL, ageMinText, distText, kmText, positionColor, positionSentence, ratioText, signedDistText, speedText,
  timeText, dayShort, type GpsAssetDetail, type GpsFix, type GpsTrackPoint, type PositionVerdict,
} from "@/lib/gps-view"
import { CAUSE_HINT, confidenceText, confidenceTone, filterTrackToDay, fusedText, hoursText, isCause, okShareText, sumGap, worstDay } from "@/lib/gps-analytics"
import { Empty, Panel, Stat } from "../../scales/_components/viz"
import { ArrowLeft, Loader2 } from "@/components/ui/icons"
import { GpsMap, type GpsLine, type GpsMarker } from "../_components/GpsMap"
import { CauseChip, Chip, DailyKmChart, DistanceChip, GTK_COLOR, HealthChip, PositionChip, SourceLegend, WIALON_COLOR } from "../_components/parts"

const DAY_OPTIONS = [1, 3, 7, 14, 31]
const TRACK_OPTIONS = [1, 2, 3, 7, 14]
const toLine = (points: GpsTrackPoint[]): [number, number][] => points.map((p) => [p.lat, p.lon])
const seg = "inline-flex overflow-hidden rounded-full ring-1 ring-gray-300 dark:ring-gray-700"
const segBtn = (on: boolean) => `px-3 py-1 text-sm ${on ? "bg-indigo-600 text-white" : "bg-white text-gray-800 dark:bg-gray-900 dark:text-gray-100"}`

export default function GpsDetailPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const [days, setDays] = useState(7)
  const [trackDays, setTrackDays] = useState(2)
  const [data, setData] = useState<GpsAssetDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [selectedDay, setSelectedDay] = useState<string | null>(null) // a local day picked in the table: the three maps show only that day

  useEffect(() => {
    let cancelled = false
    setData(null)
    api.gps.asset(assetId, { days, track_days: Math.min(trackDays, days) })
      .then((value) => { if (!cancelled) { setData(value); setError(null) } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить сравнение GPS") })
    return () => { cancelled = true }
  }, [assetId, days, trackDays])

  const row = data?.row
  const offsetHours = data?.feed.utc_offset_hours ?? 5
  const wialonPts = useMemo(() => (data ? (selectedDay ? filterTrackToDay(data.wialon_track, selectedDay, offsetHours) : data.wialon_track) : []), [data, selectedDay, offsetHours])
  const gtkPts = useMemo(() => (data ? (selectedDay ? filterTrackToDay(data.gtk_track, selectedDay, offsetHours) : data.gtk_track) : []), [data, selectedDay, offsetHours])
  const wialonLine = useMemo<GpsLine[]>(() => (data ? [{ id: "w", points: toLine(wialonPts), color: WIALON_COLOR, ends: true, label: "Wialon" }] : []), [data, wialonPts])
  const gtkLine = useMemo<GpsLine[]>(() => (data ? [{ id: "g", points: toLine(gtkPts), color: GTK_COLOR, ends: true, label: "GTK" }] : []), [data, gtkPts])
  const overlayLines = useMemo<GpsLine[]>(() => (data ? [
    { id: "w", points: toLine(wialonPts), color: WIALON_COLOR, weight: 5, label: "Wialon" },
    { id: "g", points: toLine(gtkPts), color: GTK_COLOR, weight: 3, label: "GTK" },
  ] : []), [data, wialonPts, gtkPts])
  const fixMarkers = useMemo<GpsMarker[]>(() => {
    if (!row) return []
    const out: GpsMarker[] = []
    if (row.wialon) out.push({ id: "fix-w", lat: row.wialon.lat, lon: row.wialon.lon, color: WIALON_COLOR, hollow: !row.wialon.fresh, label: `Wialon сейчас · ${ageMinText(row.wialon.age_min)}` })
    if (row.gtk) out.push({ id: "fix-g", lat: row.gtk.lat, lon: row.gtk.lon, color: GTK_COLOR, hollow: !row.gtk.fresh, label: `GTK сейчас · ${ageMinText(row.gtk.age_min)}` })
    return out
  }, [row])

  if (error) {
    return (
      <div className="space-y-3 p-6">
        <Link href="/dashboard/gps" className="text-sm text-blue-600 hover:underline">← GPS: Wialon ↔ GTK</Link>
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>
      </div>
    )
  }
  if (!data || !row) return <div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Сравниваю трекеры…</div>

  const verdict = row.position.verdict as PositionVerdict
  const totals = row.days.reduce((a, d) => ({ w: a.w + (d.wialon_m ?? 0), g: a.g + (d.gtk_m ?? 0), u: a.u + (d.fused_m ?? d.unified_m ?? 0) }), { w: 0, g: 0, u: 0 })
  const gap = sumGap(row.days)
  const worst = worstDay(row.days)
  const dayNote = selectedDay ? ` · ${dayShort(selectedDay)}` : ""
  const maps: { key: string; title: string; note: string; markers: GpsMarker[]; lines: GpsLine[]; testId: string }[] = [
    { key: "w", title: `Трек Wialon${dayNote}`, note: `${wialonPts.length} сохранённых точек`, markers: fixMarkers.filter((m) => m.id === "fix-w"), lines: wialonLine, testId: "gps-detail-map-wialon" },
    { key: "g", title: `Трек GTK${dayNote}`, note: `${gtkPts.length} сохранённых точек`, markers: fixMarkers.filter((m) => m.id === "fix-g"), lines: gtkLine, testId: "gps-detail-map-gtk" },
    { key: "t", title: `Карта НейроТОиР (единая): оба трека${dayNote}`, note: "синий — Wialon, оранжевый — GTK; кружки — живые позиции", markers: fixMarkers, lines: overlayLines, testId: "gps-detail-map-toir" },
  ]

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] min-w-0 space-y-4 bg-gray-50 p-5 sm:p-7 dark:bg-gray-950" data-testid="gps-detail-page">
      <nav className="flex flex-wrap items-center justify-between gap-2" aria-label="Навигация">
        <div className="flex min-w-0 flex-wrap items-center gap-1 text-sm text-blue-600 dark:text-blue-400">
          <Link href="/dashboard/gps" className="inline-flex items-center gap-1 hover:underline"><ArrowLeft className="h-4 w-4" /> GPS: Wialon ↔ GTK</Link>
          <span className="text-gray-400">/</span>
          <span className="truncate text-gray-700 dark:text-gray-200">{row.inv_number}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-gray-500">Таблица:</span>
          <div className={seg} role="group" aria-label="Период таблицы">
            {DAY_OPTIONS.map((d) => <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)} className={segBtn(days === d)}>{d === 1 ? "сутки" : `${d} дн.`}</button>)}
          </div>
          <span className="text-gray-500">Треки:</span>
          <div className={seg} role="group" aria-label="Период треков">
            {TRACK_OPTIONS.filter((d) => d <= days).map((d) => <button key={d} type="button" aria-pressed={Math.min(trackDays, days) === d} onClick={() => setTrackDays(d)} className={segBtn(Math.min(trackDays, days) === d)}>{d === 1 ? "сутки" : `${d} дн.`}</button>)}
          </div>
        </div>
      </nav>

      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-sky-900 p-5 text-white shadow-lg sm:p-6">
        <div className="relative flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wide text-sky-100/70">{row.asset_type_name ?? "Локомотив"}{row.model_name ? ` · ${row.model_name}` : ""}{row.section_name ? ` · ${row.section_name}` : ""}</div>
            <h1 className="truncate text-2xl font-bold sm:text-3xl">{row.inv_number} · {row.name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2"><PositionChip verdict={verdict} /><span data-testid="gps-detail-health"><HealthChip health={row.health?.health_class} /></span><span className="text-sm text-sky-100/80">{row.explanation ?? POSITION_HINT[verdict]}</span></div>
            {row.health && <p className="mt-1 text-xs text-sky-100/70">Трекер GTK за окно: {okShareText(row.health)}{row.health.km_lost_m > 0 ? ` · потеряно ${kmText(row.health.km_lost_m)}` : ""}</p>}
          </div>
          <div className="flex shrink-0 flex-wrap gap-2 text-sm">
            <Link href={`/dashboard/map/history/${row.asset_id}`} className="rounded-lg bg-white/10 px-3 py-2 font-medium ring-1 ring-white/20 hover:bg-white/20">Где был и с кем →</Link>
            <Link href="/dashboard/map" className="rounded-lg bg-white/10 px-3 py-2 font-medium ring-1 ring-white/20 hover:bg-white/20">Единая карта →</Link>
          </div>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr_1fr]">
        <FixCard title="Wialon сейчас" color={WIALON_COLOR} fix={row.wialon} linked={row.wialon_linked} />
        <section className="min-w-0 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900" data-testid="gps-detail-verdict">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Вердикт по положению</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2"><PositionChip verdict={verdict} /><span className="text-sm text-gray-700 dark:text-gray-200">между точками <b>{row.position.diff_m == null ? "—" : distText(row.position.diff_m)}</b></span></div>
          <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">{positionSentence(row.position, row.wialon, row.gtk)}</p>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{row.position.best ? `На единой карте рисуется ${row.position.best === "gtk" ? "GTK GPS" : "Wialon"}: это более свежая точка.` : "На единой карте позиции нет."}</p>
        </section>
        <FixCard title="GTK сейчас" color={GTK_COLOR} fix={row.gtk} linked={row.gtk_linked} />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={`Км Wialon · ${days} дн.`} value={kmText(totals.w)} />
        <Stat label={`Км GTK · ${days} дн.`} value={kmText(totals.g)} hint={totals.w > 0 ? `${ratioText(totals.g / totals.w)} от Wialon` : undefined} />
        <Stat label="Единый пробег" value={fusedText(totals.u, gap)} hint={row.week_confidence != null ? `уверенность: ${confidenceText(row.week_confidence)}` : "единый трек: Wialon + заполнение из GTK"} tone="good" />
        <Stat label="Проблемных дней" value={`${row.distance_issues} из ${row.days.length}`} tone={row.distance_issues > 0 ? "warn" : "good"} hint={worst ? `хуже всего: ${dayShort(worst.day)}` : "разница или провал одного из трекеров"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {maps.map((m) => (
          <section key={m.key} className="min-w-0 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <header className="mb-2 px-1"><h2 className="text-sm font-semibold text-gray-900 dark:text-white">{m.title}</h2><p className="text-xs text-gray-500 dark:text-gray-400">{m.note}</p></header>
            <div className="h-[42vh] min-h-[300px] min-w-0 overflow-hidden rounded-xl">
              {mapError ? <div className="flex h-full items-center justify-center p-4 text-center text-sm text-amber-800">{`Карта OpenStreetMap недоступна: ${mapError}`}</div>
                : <GpsMap markers={m.markers} lines={m.lines} onError={setMapError} testId={m.testId} ariaLabel={`${m.title} (OpenStreetMap)`} fitKey={`${assetId}-${trackDays}-${data.track_from}-${selectedDay ?? "all"}`} />}
            </div>
          </section>
        ))}
      </div>

      <Panel title="Пробег по дням" hint="Столбики: Wialon (длина сохранённого трека) и GTK (его собственный пробег). Полоска под парой — вердикт дня.">
        <DailyKmChart days={row.days} />
        <div className="mt-2"><SourceLegend /></div>
      </Panel>

      <Panel title="День за днём" hint="Новые дни сверху. Нажмите на день: три карты покажут только его. Точки — сохранённые (с прореживанием); «исходных» — сколько точек вернул GTK.">
        {selectedDay && <div className="mb-2 flex items-center gap-2 text-sm"><Chip tone="info">Выбран день {dayShort(selectedDay)}</Chip><button type="button" onClick={() => setSelectedDay(null)} className="text-xs text-blue-600 underline" data-testid="gps-detail-day-clear">показать весь период</button></div>}
        {row.days.length === 0 ? <Empty text="Нет дней в периоде" /> : (
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[1180px] text-left text-sm" data-testid="gps-detail-days">
              <thead className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
                <tr>
                  <th className="px-2 py-2">День</th><th className="px-2 py-2 text-right">Wialon, км</th><th className="px-2 py-2 text-right">GTK, км</th>
                  <th className="px-2 py-2 text-right">GTK / Wialon</th><th className="px-2 py-2 text-right">Разница</th><th className="px-2 py-2">Вердикт</th><th className="px-2 py-2">Причина</th>
                  <th className="px-2 py-2 text-right">Единый, км ±</th><th className="px-2 py-2 text-right" title="Дельта одометра Wialon за сутки: третий независимый источник">Одометр, км</th><th className="px-2 py-2">Уверенность</th><th className="px-2 py-2 text-right">Покрытие W / G</th><th className="px-2 py-2 text-right">Точек W / G</th><th className="px-2 py-2 text-right">Остановок GTK</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {row.days.map((d) => (
                  <tr key={d.day} data-testid="gps-detail-day" data-verdict={d.verdict} data-cause={d.cause} className={selectedDay === d.day ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}>
                    <td className="px-2 py-2 font-medium"><button type="button" aria-pressed={selectedDay === d.day} onClick={() => setSelectedDay(selectedDay === d.day ? null : d.day)} className="rounded px-1 text-blue-700 underline-offset-2 hover:underline dark:text-blue-400" data-testid="gps-detail-day-pick" title="Показать этот день на картах">{dayShort(d.day)}</button>{!d.gtk_final && d.verdict !== "not_collected" && <span className="ml-2"><Chip tone="info" title="Сутки ещё не закончились (или GTK не закрыт): цифра может вырасти.">день не закрыт</Chip></span>}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{kmText(d.wialon_m, false)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{kmText(d.gtk_m, false)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{ratioText(d.ratio)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{signedDistText(d.diff_m)}</td>
                    <td className="px-2 py-2"><DistanceChip verdict={d.verdict} /></td>
                    <td className="px-2 py-2">
                      <CauseChip cause={d.cause} />
                      {(d.explanation || (d.cause && isCause(d.cause) && d.cause !== "ok")) && <div className="mt-0.5 max-w-[260px] text-xs leading-tight text-gray-500 dark:text-gray-400" data-testid="gps-detail-explanation">{d.explanation ?? (isCause(d.cause) ? CAUSE_HINT[d.cause] : "")}</div>}
                    </td>
                    <td className="px-2 py-2 text-right font-semibold tabular-nums">{fusedText(d.fused_m ?? d.unified_m, d.unknown_gap_m)}</td>
                    <td className="px-2 py-2 text-right tabular-nums" data-testid="gps-detail-odo">
                      {d.odo_m == null ? "—" : <span className="inline-flex items-center justify-end gap-1">{kmText(d.odo_m, false)}{d.odo_agrees === true ? <Chip tone="ok">✓</Chip> : d.odo_agrees === false ? <Chip tone="bad">≠</Chip> : null}</span>}
                    </td>
                    <td className="px-2 py-2">{d.confidence == null ? <span className="text-xs text-gray-400">—</span> : <Chip tone={confidenceTone(d.confidence)}>{confidenceText(d.confidence)}</Chip>}</td>
                    <td className="px-2 py-2 text-right text-xs tabular-nums">{hoursText(d.wialon_cov_h)} / {hoursText(d.gtk_cov_h)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{d.wialon_points} / {d.gtk_points} <span className="text-xs text-gray-400">({d.gtk_raw_points})</span></td>
                    <td className="px-2 py-2 text-right tabular-nums">{d.idle_events ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Что означают вердикты" hint="Положение сейчас">
          <ul className="space-y-2 text-sm">
            {(Object.keys(POSITION_LABEL) as PositionVerdict[]).map((v) => (
              <li key={v} className={`flex gap-2 ${v === verdict ? "rounded-lg bg-indigo-50 p-1.5 dark:bg-indigo-950/40" : ""}`}>
                <i className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: positionColor(v) }} />
                <span><b className="text-gray-900 dark:text-white">{POSITION_LABEL[v]}.</b> <span className="text-gray-700 dark:text-gray-300">{POSITION_HINT[v]}</span></span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Что означают вердикты по дням" hint="Пробег за сутки">
          <ul className="space-y-2 text-sm">
            {(Object.keys(DISTANCE_LABEL) as (keyof typeof DISTANCE_LABEL)[]).map((v) => (
              <li key={v}><b className="text-gray-900 dark:text-white">{DISTANCE_LABEL[v]}.</b> <span className="text-gray-700 dark:text-gray-300">{DISTANCE_HINT[v]}</span></li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}

function FixCard({ title, color, fix, linked }: { title: string; color: string; fix: GpsFix | null; linked: boolean }) {
  return (
    <section className="min-w-0 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900" data-testid={`gps-fix-${title.startsWith("W") ? "wialon" : "gtk"}`}>
      <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white"><i className="h-3 w-3 rounded-sm" style={{ background: color }} />{title}</h2>
      {!fix ? <p className="mt-2 text-sm text-gray-500">{linked ? "Привязан, но координат нет." : "Трекер не привязан к локомотиву."}</p> : (
        <dl className="mt-2 space-y-1 text-sm">
          <div className="flex justify-between gap-3"><dt className="text-gray-500">Позиция</dt><dd className="tabular-nums text-gray-900 dark:text-white">{fix.lat.toFixed(5)}, {fix.lon.toFixed(5)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-gray-500">Время фикса</dt><dd className="tabular-nums text-gray-900 dark:text-white">{timeText(fix.at)}</dd></div>
          <div className="flex items-center justify-between gap-3"><dt className="text-gray-500">Возраст</dt><dd><Chip tone={fix.fresh ? "ok" : "warn"}>{ageMinText(fix.age_min)}{fix.fresh ? " · свежий" : " · устарел"}</Chip></dd></div>
          <div className="flex justify-between gap-3"><dt className="text-gray-500">Скорость</dt><dd className="tabular-nums text-gray-900 dark:text-white">{speedText(fix.speed)}</dd></div>
        </dl>
      )}
    </section>
  )
}
