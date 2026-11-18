"use client"

import Link from "next/link"
import { useEffect, useRef } from "react"
import {
  CAUSE_HINT, confidenceText, confidenceTone, fusedText, hoursText, isCause, okShareText, sumGap, worstDay, healthLabel,
} from "@/lib/gps-analytics"
import { POSITION_HINT, ageMinText, dayShort, distText, kmText, positionSentence, speedText, timeText, type GpsAssetRow, type GpsFix } from "@/lib/gps-view"
import { CauseChip, Chip, DistanceChip, GTK_COLOR, HealthChip, MiniPair, PositionChip, SourceLegend, WIALON_COLOR } from "./parts"

function Fix({ title, color, fix, linked }: { title: string; color: string; fix: GpsFix | null; linked: boolean }) {
  return (
    <div className="min-w-0 rounded-xl bg-gray-50 p-3 ring-1 ring-gray-200 dark:bg-gray-800/60 dark:ring-gray-700">
      <div className="flex items-center gap-2 text-xs font-semibold text-gray-900 dark:text-white"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />{title}</div>
      {!fix ? <p className="mt-1 text-xs text-gray-500">{linked ? "Привязан, координат нет" : "Не привязан"}</p> : (
        <dl className="mt-1 space-y-0.5 text-xs">
          <div className="flex justify-between gap-2"><dt className="text-gray-500">Время</dt><dd className="tabular-nums text-gray-900 dark:text-white">{timeText(fix.at)}</dd></div>
          <div className="flex items-center justify-between gap-2"><dt className="text-gray-500">Возраст</dt><dd><Chip tone={fix.fresh ? "ok" : "warn"}>{ageMinText(fix.age_min)}</Chip></dd></div>
          <div className="flex justify-between gap-2"><dt className="text-gray-500">Скорость</dt><dd className="tabular-nums text-gray-900 dark:text-white">{speedText(fix.speed)}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-gray-500">Позиция</dt><dd className="tabular-nums text-gray-900 dark:text-white">{fix.lat.toFixed(4)}, {fix.lon.toFixed(4)}</dd></div>
        </dl>
      )}
    </div>
  )
}

/** The right-hand drawer of a locomotive: both fixes, the verdict and its explanation, the worst recent day, the week and the links. */
export function GpsDrawer({ row, onClose }: { row: GpsAssetRow; onClose: () => void }) {
  const ref = useRef<HTMLElement | null>(null)
  useEffect(() => { ref.current?.focus() }, [row.asset_id])
  const worst = worstDay(row.days)
  const week = row.days.slice(0, 7)
  const gap = sumGap(row.days)
  return (
    <>
      <button type="button" aria-label="Закрыть панель" className="fixed inset-0 z-40 bg-slate-950/30 backdrop-blur-[1px] lg:hidden" onClick={onClose} tabIndex={-1} />
      <aside
        ref={ref} tabIndex={-1} role="dialog" aria-label={`Локомотив ${row.inv_number}`} data-testid="gps-drawer"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-full flex-col overflow-y-auto border-l border-gray-200 bg-white shadow-2xl outline-none sm:w-[460px] dark:border-gray-800 dark:bg-gray-900"
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-2 border-b border-gray-100 bg-white/95 p-4 backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
          <div className="min-w-0">
            <div className="truncate text-base font-bold text-gray-900 dark:text-white">{row.inv_number} · {row.name}</div>
            <div className="truncate text-xs text-gray-500 dark:text-gray-400">{[row.asset_type_name, row.model_name, row.section_name].filter(Boolean).join(" · ")}</div>
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть" data-testid="gps-drawer-close" className="rounded-lg px-2.5 py-1.5 text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50 dark:text-gray-300 dark:ring-gray-700">✕</button>
        </header>

        <div className="space-y-4 p-4">
          <section>
            <div className="flex flex-wrap items-center gap-2"><PositionChip verdict={row.position.verdict} /><HealthChip health={row.health?.health_class} /></div>
            <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">{row.explanation ?? positionSentence(row.position, row.wialon, row.gtk)}</p>
            {!row.explanation && <p className="mt-1 text-xs text-gray-500">{POSITION_HINT[row.position.verdict]}</p>}
          </section>

          <section className="grid grid-cols-2 gap-2">
            <Fix title="Wialon" color={WIALON_COLOR} fix={row.wialon} linked={row.wialon_linked} />
            <Fix title="GTK GPS" color={GTK_COLOR} fix={row.gtk} linked={row.gtk_linked} />
            {row.position.diff_m != null && <div className="col-span-2 text-center text-xs text-gray-600 dark:text-gray-300">Между точками <b>{distText(row.position.diff_m)}</b>{row.position.tolerance_m != null ? ` · допуск ${distText(row.position.tolerance_m)}` : ""}</div>}
          </section>

          {row.health && (
            <section className="rounded-xl bg-gray-50 p-3 text-sm ring-1 ring-gray-200 dark:bg-gray-800/60 dark:ring-gray-700">
              <div className="flex flex-wrap items-center justify-between gap-2"><b className="text-gray-900 dark:text-white">Трекер GTK: {healthLabel(row.health.health_class)}</b><span className="text-xs text-gray-500">{okShareText(row.health)}</span></div>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                Дней без записи: {row.health.none_days} · частично: {row.health.partial_days}
                {row.health.km_lost_m > 0 ? ` · потеряно ${kmText(row.health.km_lost_m)}` : ""}
                {row.health.last_gtk_fix_age_h != null ? ` · последняя точка ${row.health.last_gtk_fix_age_h < 48 ? `${Math.round(row.health.last_gtk_fix_age_h)} ч` : `${Math.round(row.health.last_gtk_fix_age_h / 24)} сут`} назад` : ""}
              </p>
            </section>
          )}

          {worst && (
            <section className="rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30" data-testid="gps-drawer-cause">
              <div className="flex flex-wrap items-center gap-2 text-sm"><b className="text-gray-900 dark:text-white">Худший день: {dayShort(worst.day)}</b><CauseChip cause={worst.cause} /><DistanceChip verdict={worst.verdict} /></div>
              <p className="mt-1.5 text-sm text-gray-800 dark:text-gray-200">{worst.explanation ?? (isCause(worst.cause) ? CAUSE_HINT[worst.cause] : "")}</p>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">Wialon {kmText(worst.wialon_m)} · GTK {kmText(worst.gtk_m)} · покрытие {hoursText(worst.wialon_cov_h)} / {hoursText(worst.gtk_cov_h)}</p>
            </section>
          )}

          <section>
            <div className="mb-1 flex items-center justify-between"><h3 className="text-sm font-semibold text-gray-900 dark:text-white">Последние 7 дней</h3><SourceLegend /></div>
            <MiniPair days={week} />
            <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-gray-50 p-2 dark:bg-gray-800/60"><div className="text-gray-500">Wialon</div><div className="font-bold tabular-nums text-gray-900 dark:text-white">{kmText(row.week_wialon_m)}</div></div>
              <div className="rounded-lg bg-gray-50 p-2 dark:bg-gray-800/60"><div className="text-gray-500">GTK</div><div className="font-bold tabular-nums text-gray-900 dark:text-white">{kmText(row.week_gtk_m)}</div></div>
              <div className="rounded-lg bg-gray-50 p-2 dark:bg-gray-800/60"><div className="text-gray-500">Единый</div><div className="font-bold tabular-nums text-gray-900 dark:text-white">{fusedText(row.week_fused_m ?? row.week_unified_m, gap)}</div></div>
            </div>
            {row.week_confidence != null && <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">Уверенность: <Chip tone={confidenceTone(row.week_confidence)}>{confidenceText(row.week_confidence)}</Chip></p>}
          </section>

          <div className="flex flex-wrap gap-2 pb-4 text-sm">
            <Link href={`/dashboard/gps/${row.asset_id}`} className="rounded-lg bg-indigo-600 px-3 py-2 font-medium text-white hover:bg-indigo-700" data-testid="gps-drawer-detail">Подробно →</Link>
            <Link href="/dashboard/map" className="rounded-lg bg-white px-3 py-2 font-medium text-gray-800 ring-1 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-700">Карта →</Link>
            <Link href={`/dashboard/map/history/${row.asset_id}`} className="rounded-lg bg-white px-3 py-2 font-medium text-gray-800 ring-1 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-700">Где был и с кем →</Link>
          </div>
        </div>
      </aside>
    </>
  )
}
