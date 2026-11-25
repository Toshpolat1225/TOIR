"use client"
import { fmtPercent } from "@/lib/format"

import { PeriodPicker } from "@/components/gps/PeriodPicker"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import { BASIS_HINT, BASIS_LABEL, CONFIDENCE_HINT, CONFIDENCE_LABEL, FLAG_HINT, segKm } from "@/lib/gps-analytics"
import { POSITION_HINT, POSITION_LABEL, ageMinText, timeText, type GpsWagonDetail, type PositionVerdict } from "@/lib/gps-view"
import { Empty, Panel, Stat } from "../../../scales/_components/viz"
import { ArrowLeft, Loader2 } from "@/components/ui/icons"
import { GpsMap, type GpsMarker } from "../../_components/GpsMap"
import { BasisChip, Chip, ConfidenceChip, FlagChip } from "../../_components/parts"
import { CANDIDATES, CandidatesLegend, SegmentTimeline, WagonBanner } from "../../_components/WagonParts"


export default function WagonDetailPage() {
  const { key: rawKey } = useParams<{ key: string }>()
  const key = decodeURIComponent(rawKey)
  const [days, setDays] = useState(14)
  const [range, setRange] = useState({ date_from: "", date_to: "" })
  const [data, setData] = useState<GpsWagonDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setData(null)
    api.gps.wagon(key, range.date_from || range.date_to ? { days, ...range } : { days })
      .then((value) => { if (!cancelled) { setData(value); setError(null) } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить вагон") })
    return () => { cancelled = true }
  }, [key, days, range])

  const row = data?.row
  const markers = useMemo<GpsMarker[]>(() => (row?.position ? [{ id: "wagon", lat: row.position.lat, lon: row.position.lon, color: "#7c3aed", hollow: row.confidence === "low" || row.confidence === "none", label: `${row.inv_number ?? row.name} · выведено из локомотива ${row.loco_inv_number ?? "—"}` }] : []), [row])

  if (error) {
    return (
      <div className="space-y-3 p-6">
        <Link href="/dashboard/gps/wagons" className="text-sm text-blue-600 hover:underline">← Вагоны (по составу)</Link>
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>
      </div>
    )
  }
  if (!data || !row) return <div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Загружаю вагон…</div>

  const segments = data.segments
  const total = segments.reduce((a, s) => a + (s.selected_km ?? 0), 0)
  const basisCount = segments.reduce<Record<string, number>>((a, s) => ({ ...a, [s.basis]: (a[s.basis] ?? 0) + 1 }), {})
  const worst = segments.find((s) => s.confidence === "low" || s.confidence === "none" || s.basis === "held" || s.basis === "conflict")

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] min-w-0 space-y-4 bg-gray-50 p-5 sm:p-7 dark:bg-gray-950" data-testid="wagon-detail-page">
      <nav className="flex flex-wrap items-center justify-between gap-2" aria-label="Навигация">
        <div className="flex min-w-0 flex-wrap items-center gap-1 text-sm text-blue-600 dark:text-blue-400">
          <Link href="/dashboard/gps/wagons" className="inline-flex items-center gap-1 hover:underline"><ArrowLeft className="h-4 w-4" /> Вагоны (по составу)</Link>
          <span className="text-gray-400">/</span>
          <span className="truncate text-gray-700 dark:text-gray-200">{row.inv_number ?? row.name}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-gray-500">Период:</span>
          <PeriodPicker days={days} dateFrom={range.date_from} dateTo={range.date_to} onChange={(n) => { setDays(n.days); setRange({ date_from: n.date_from, date_to: n.date_to }) }} />
        </div>
      </nav>

      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-teal-950 to-sky-900 p-5 text-white shadow-lg sm:p-6">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-sky-100/70">{[row.asset_type_name, row.section_name].filter(Boolean).join(" · ") || "Вагон"}{row.asset_id ? "" : " · не привязан к ОС"}</div>
          <h1 className="truncate text-2xl font-bold sm:text-3xl">{row.inv_number ?? row.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <ConfidenceChip level={row.confidence} />
            {row.in_train ? <span className="text-sky-100/90">в составе № {row.train_number ?? row.train_gtk_id} с {timeText(row.since)}</span> : <span className="text-sky-100/80">сейчас не в составе</span>}
            {row.loco_inv_number && (row.loco_asset_id ? <Link href={`/dashboard/gps/${row.loco_asset_id}`} className="rounded-lg bg-white/10 px-2 py-1 text-xs ring-1 ring-white/20 hover:bg-white/20">Локомотив {row.loco_inv_number} →</Link> : <span className="text-xs text-sky-100/80">локомотив {row.loco_inv_number}</span>)}
          </div>
          {row.flags.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm" data-testid="wagon-flags">
              {row.flags.map((f) => <li key={f} className="flex flex-wrap items-center gap-2"><FlagChip flag={f} /><span className="text-xs text-sky-100/80">{FLAG_HINT[f as keyof typeof FLAG_HINT] ?? ""}</span></li>)}
            </ul>
          )}
        </div>
      </header>

      <WagonBanner />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={`Выбранный пробег · ${days} дн.`} value={segKm(total)} hint="сумма выбранных значений по сегментам (источники не складываются)" tone="good" />
        <Stat label="Сегментов" value={segments.length} hint={segments.filter((s) => s.open).length ? "есть открытый" : "все закрыты"} />
        <Stat label="Основания" value={Object.keys(basisCount).length || "—"} hint={Object.entries(basisCount).map(([b, n]) => `${BASIS_LABEL[b as keyof typeof BASIS_LABEL] ?? b}: ${n}`).join(", ") || "нет сегментов"} />
        <Stat label="Положение сейчас" value={row.position ? (row.position_source === "gtk_gps" ? "GTK GPS" : "Wialon") : "нет"} hint={row.position ? `${ageMinText(row.position.age_min)}${row.position_verdict ? ` · ${POSITION_LABEL[row.position_verdict as PositionVerdict] ?? row.position_verdict}` : ""}` : CONFIDENCE_HINT.none} tone={row.position ? "plain" : "warn"} />
      </div>

      {data.explanation && <p className="rounded-xl bg-white p-4 text-sm text-gray-800 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-800" data-testid="wagon-explanation">{data.explanation}</p>}

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr] [&>*]:min-w-0">
        <Panel title="Сегменты по составам" hint="Каждая полоса — пребывание вагона в составе у одного локомотива. Цвет — уверенность, пунктирная рамка — сегмент ещё идёт.">
          <SegmentTimeline segments={segments} />
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-600 dark:text-gray-300">
            {(["high", "medium", "low", "none"] as const).map((c) => <span key={c} className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: { high: "#16a34a", medium: "#2563eb", low: "#d97706", none: "#94a3b8" }[c] }} />{CONFIDENCE_LABEL[c]}</span>)}
          </div>
        </Panel>
        <section className="min-w-0 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h2 className="mb-2 px-1 text-sm font-semibold text-gray-900 dark:text-white">Где вагон сейчас (выведено)</h2>
          <div className="h-[260px] min-w-0 overflow-hidden rounded-xl">
            {markers.length === 0 ? <div className="flex h-full items-center justify-center p-4 text-center text-sm text-gray-500">Нет выведенной позиции: вагон не в составе или у локомотива нет координат.</div>
              : mapError ? <div className="flex h-full items-center justify-center p-4 text-center text-sm text-amber-800">{`Карта OpenStreetMap недоступна: ${mapError}`}</div>
              : <GpsMap markers={markers} onError={setMapError} testId="wagon-map" ariaLabel="Положение вагона (OpenStreetMap)" fitKey={key} />}
          </div>
          {row.position_verdict && <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">{POSITION_HINT[row.position_verdict as PositionVerdict] ?? ""}</p>}
        </section>
      </div>

      <Panel title="Четыре варианта пробега по сегментам" hint="Значения в км. Выбранное выделено; основание и уверенность объясняют выбор. Источники не усредняются и не суммируются.">
        {segments.length === 0 ? <Empty text="За период нет сегментов" /> : (
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[1080px] text-left text-sm" data-testid="wagon-segments">
              <thead className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
                <tr>
                  <th className="px-2 py-2">Состав</th><th className="px-2 py-2">Локомотив</th><th className="px-2 py-2">С</th><th className="px-2 py-2">По</th>
                  {CANDIDATES.map((c) => <th key={c.key} className="px-2 py-2 text-right" title={c.hint}>{c.title}</th>)}
                  <th className="px-2 py-2 text-right">Выбрано</th><th className="px-2 py-2">Основание</th><th className="px-2 py-2">Уверенность</th><th className="px-2 py-2 text-right">Покрытие</th><th className="px-2 py-2">Признаки</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {segments.map((s) => (
                  <tr key={`${s.train_gtk_id}-${s.period_from}`} data-testid="wagon-segment" data-basis={s.basis} data-confidence={s.confidence}>
                    <td className="px-2 py-2 tabular-nums">№ {s.train_number ?? s.train_gtk_id}</td>
                    <td className="px-2 py-2 text-xs">{s.loco_asset_id ? <Link href={`/dashboard/gps/${s.loco_asset_id}`} className="text-blue-700 hover:underline dark:text-blue-400">{s.loco_inv_number}</Link> : s.loco_inv_number ?? "—"}</td>
                    <td className="px-2 py-2 text-xs tabular-nums">{timeText(s.period_from)}</td>
                    <td className="px-2 py-2 text-xs tabular-nums">{s.open ? <Chip tone="info">идёт</Chip> : timeText(s.period_to)}</td>
                    {CANDIDATES.map((c) => {
                      const value = s[c.field]
                      const chosen = value != null && s.selected_km != null && Math.abs(value - s.selected_km) < 0.0005
                      return (
                        <td key={c.key} data-testid={`wagon-candidate-${c.key}`} data-chosen={chosen} className={`px-2 py-2 text-right tabular-nums ${chosen ? "rounded bg-emerald-50 font-bold text-emerald-900 ring-1 ring-inset ring-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-200" : value == null ? "text-gray-400" : ""}`}>
                          {segKm(value)}
                        </td>
                      )
                    })}
                    <td className="px-2 py-2 text-right font-semibold tabular-nums">{segKm(s.selected_km)}</td>
                    <td className="px-2 py-2"><span title={BASIS_HINT[s.basis]}><BasisChip basis={s.basis} /></span></td>
                    <td className="px-2 py-2"><ConfidenceChip level={s.confidence} /></td>
                    <td className="px-2 py-2 text-right text-xs tabular-nums">{s.coverage == null ? "—" : fmtPercent(s.coverage * 100)}</td>
                    <td className="px-2 py-2"><div className="flex flex-wrap gap-1">{s.flags.length === 0 ? <span className="text-xs text-gray-400">—</span> : s.flags.map((f) => <FlagChip key={f} flag={f} />)}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {worst && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">Есть сегмент с пониженной уверенностью или конфликтом источников ({BASIS_LABEL[worst.basis]}): его значение приблизительное.</p>}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <Panel title="Что означают варианты"><CandidatesLegend /></Panel>
        <Panel title="Как выбирается значение">
          <ul className="space-y-1.5 text-sm text-gray-700 dark:text-gray-300">
            {(Object.keys(BASIS_LABEL) as (keyof typeof BASIS_LABEL)[]).map((b) => <li key={b}><b className="text-gray-900 dark:text-white">{BASIS_LABEL[b]}.</b> {BASIS_HINT[b]}</li>)}
          </ul>
        </Panel>
      </div>
    </div>
  )
}
