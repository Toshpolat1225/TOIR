"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import { fmt, locoHref, parseWagonKey, tonnesCompact, trainHref, wagonHref } from "@/lib/scales-insights"
import {
  ACTIVITY_LABEL, hoursText, historyHref, historyNote, kmText, pointAt, segmentAt, segmentColor, segmentHours, segmentSentence, type AssetHistory,
} from "@/lib/map-history"
import { ArrowLeft, Loader2 } from "@/components/ui/icons"
import { TrackMap } from "../../_components/TrackMap"

const DAY_OPTIONS = [1, 3, 7, 14, 30, 90]
const dt = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—")
const card = "min-w-0 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"

export default function HistoryPage() {
  const { key } = useParams<{ key: string }>()
  const [days, setDays] = useState(7)
  const [data, setData] = useState<AssetHistory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [active, setActive] = useState<number | null>(null)
  const [scrub, setScrub] = useState<number | null>(null)
  const params = useMemo(() => parseWagonKey(key), [key])

  useEffect(() => {
    let cancelled = false
    setData(null)
    api.assetMap.history({ ...params, days })
      .then((value) => { if (!cancelled) { setData(value); setError(null); setActive(null); setScrub(null) } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить историю") })
    return () => { cancelled = true }
  }, [params, days])

  if (error) return <div className="space-y-3 p-6"><Link href="/dashboard/map" className="text-sm text-blue-600 hover:underline">← Карта</Link><p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p></div>
  if (!data) return <div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Собираю историю…</div>

  const isLoco = data.kind === "locomotive"
  const title = data.asset?.inv_number ?? data.gtk_carriage?.inventory_number ?? data.gtk_carriage?.name ?? "вагон"
  const first = data.track.length ? new Date(data.track[0].at).getTime() : null
  const last = data.track.length ? new Date(data.track[data.track.length - 1].at).getTime() : null
  const scrubPoint = scrub !== null ? pointAt(data.track, scrub) : null
  const scrubSegment = scrub !== null ? segmentAt(data.segments, scrub) : null
  const c = data.current
  const stateText = !c ? "положение не записано" : isLoco ? (c.speed && c.speed >= 3 ? `едет, ${Math.round(c.speed)} км/ч` : "стоит") : c.in_train ? `в составе за ${c.loco_label ?? "локомотивом"}` : "не в составе"
  const sliderMin = first ?? new Date(data.segments.at(-1)?.from_at ?? Date.now()).getTime()
  const sliderMax = last ?? Date.now()

  return (
    <div className="mx-auto min-h-screen max-w-[1600px] space-y-4 bg-gray-50 p-5 sm:p-7 dark:bg-gray-950" data-testid="history-page">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href="/dashboard/map" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline dark:text-blue-400"><ArrowLeft className="h-4 w-4" /> Карта</Link>
        <div className="inline-flex overflow-hidden rounded-full ring-1 ring-gray-300 dark:ring-gray-700" role="group" aria-label="Период">
          {DAY_OPTIONS.map((d) => <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)} className={`px-3 py-1 text-sm ${days === d ? "bg-indigo-600 text-white" : "bg-white text-gray-800 dark:bg-gray-900 dark:text-gray-100"}`}>{d === 1 ? "сутки" : `${d} дн.`}</button>)}
        </div>
      </div>

      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-950 via-violet-900 to-slate-900 p-5 text-white shadow-lg sm:p-6">
        <div className="pointer-events-none absolute -right-10 -top-10 h-56 w-56 rounded-full bg-fuchsia-400/10 blur-3xl" />
        <div className="relative">
          <div className="flex flex-wrap items-center gap-2 text-sm text-violet-100/80">
            <span>{isLoco ? "История локомотива" : "История вагона"}</span>
            {data.asset?.status_name && <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-xs">{data.asset.status_name}</span>}
            {data.asset?.section_name && <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-xs">{data.asset.section_name}</span>}
            {!data.asset && <span className="rounded-full bg-amber-400/90 px-2.5 py-0.5 text-xs text-amber-950">не связан с ОС</span>}
          </div>
          <h1 className="mt-1 text-3xl font-bold" data-testid="history-title">{title}</h1>
          <p className="mt-1 text-sm text-violet-100/80">{[data.asset?.model_name ?? data.gtk_carriage?.model_name ?? data.gtk_loco?.model_name, data.gtk_carriage?.name ?? data.gtk_loco?.name].filter(Boolean).join(" · ")}</p>
          <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-sm ring-1 ring-white/15">
            <span className={`h-2.5 w-2.5 rounded-full ${c ? (c.in_train || (c.speed ?? 0) >= 3 ? "bg-emerald-400" : "bg-amber-300") : "bg-gray-400"}`} />
            Сейчас: {stateText}{c ? <span className="text-violet-100/70"> · {dt(c.at)}</span> : null}
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            {data.asset && <Link className="underline decoration-white/40 hover:decoration-white" href={`/dashboard/directories/assets?q=${encodeURIComponent(data.asset.inv_number)}`}>Карточка ОС →</Link>}
            {data.asset && !isLoco && <Link className="underline decoration-white/40 hover:decoration-white" href={wagonHref({ asset_id: data.asset.asset_id, carriage_gtk_id: 0 })}>Рейсы и тонны по весам →</Link>}
            {data.asset && isLoco && <Link className="underline decoration-white/40 hover:decoration-white" href={locoHref(data.asset.asset_id)}>Работа по весам →</Link>}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {[
          [isLoco ? "Тянул составов" : "Составов (отрезков)", fmt(data.stats.segments), null],
          ["Время в составах", hoursText(data.stats.coupled_hours), `из ${days === 1 ? "суток" : `${days} дн.`}`],
          ["Пройдено", kmText(data.stats.km), "по записанному треку"],
          [isLoco ? "Разных вагонов" : "Разных локомотивов", fmt(data.stats.distinct_partners), null],
          ["Взвешиваний", fmt(data.stats.trips), null],
          ["Перевезено", tonnesCompact(data.stats.tonnes), null],
          ["Последнее движение", dt(data.stats.last_move_at), null],
        ].map(([label, value, hint]) => (
          <div key={label as string} className={card}><div className="text-xs text-gray-500 dark:text-gray-400">{label}</div><div className="mt-0.5 text-xl font-bold tabular-nums text-gray-900 dark:text-white">{value}</div>{hint && <div className="text-xs text-gray-500">{hint}</div>}</div>
        ))}
      </div>

      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-xs text-indigo-900 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200">
        {historyNote(data).map((n) => <p key={n}>{n}</p>)}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section className={card} aria-label="Трек">
          <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Где был: трек на карте</h2>
          <div className="h-[460px]">
            {mapError ? <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">Карта недоступна: {mapError} (нет интернета?). Лента событий ниже работает без карты.</div>
              : data.track.length === 0 ? <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">За выбранный период позиций нет. Вагон передвигается без собственного GPS: его положение берётся у локомотива состава, как только GTK и Wialon накопят историю.</div>
              : <TrackMap track={data.track} segments={data.segments} activeIndex={active} scrubAt={scrub} onPick={setActive} onError={setMapError} />}
          </div>
          {data.track.length > 1 && first !== null && last !== null && (
            <div className="mt-3 rounded-xl bg-gray-50 p-3 dark:bg-gray-800/60" data-testid="scrubber">
              <label className="text-xs text-gray-500">Где он был в момент: <b className="text-gray-900 dark:text-white">{scrub !== null ? dt(new Date(scrub).toISOString()) : "двигайте ползунок"}</b></label>
              <input type="range" aria-label="Момент времени" className="mt-1 w-full" min={sliderMin} max={sliderMax} step={60_000} value={scrub ?? sliderMax} onChange={(e) => setScrub(Number(e.target.value))} />
              {scrubPoint && (
                <p className="mt-1 text-sm text-gray-800 dark:text-gray-200" data-testid="scrub-answer">
                  {scrubSegment ? <>{isLoco ? "Тянул состав" : "Стоял в составе"} <b>{scrubSegment.loco_label ?? "локомотив не определён"}</b> ({scrubSegment.cars} ваг.). </> : <>{isLoco ? "Не тянул состав. " : "Вне состава. "}</>}
                  Координаты {scrubPoint.lat.toFixed(4)}, {scrubPoint.lon.toFixed(4)}{scrubPoint.speed !== null ? `, скорость ${Math.round(scrubPoint.speed)} км/ч` : ""} (запись {dt(scrubPoint.at)}).
                </p>
              )}
            </div>
          )}
        </section>

        <section className={card} aria-label="Лента событий">
          <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">С кем и что делал: лента</h2>
          {data.segments.length === 0 ? <p className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">За период {isLoco ? "локомотив не числился головным в составах GTK" : "вагон не числился в составах GTK"}.</p> : (
            <ol className="relative max-h-[560px] space-y-3 overflow-y-auto border-l-2 border-gray-200 pl-4 dark:border-gray-700">
              {data.segments.map((s, i) => (
                <li key={`${s.train_gtk_id}-${s.from_at}`} data-testid="history-segment">
                  <button type="button" onClick={() => setActive(active === i ? null : i)} className={`block w-full rounded-xl p-3 text-left ring-1 transition ${active === i ? "bg-indigo-50 ring-indigo-300 dark:bg-indigo-950/40 dark:ring-indigo-700" : "bg-white ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:ring-gray-800 dark:hover:bg-gray-800"}`}>
                    <span className="absolute -left-[22px] mt-1 h-3 w-3 rounded-full ring-4 ring-white dark:ring-gray-900" style={{ background: segmentColor(i) }} />
                    <span className="flex flex-wrap items-center gap-x-2 text-xs text-gray-500"><b className="text-gray-800 dark:text-gray-200">{dt(s.from_at)} — {s.is_open ? "сейчас" : dt(s.to_at)}</b><span>· {hoursText(segmentHours(s))}</span><span className={`rounded-full px-2 py-0.5 ${s.activity === "moving" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" : s.activity === "standing" ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"}`}>{ACTIVITY_LABEL[s.activity]}</span></span>
                    <span className="mt-1 block text-sm text-gray-800 dark:text-gray-100">{segmentSentence(data.kind, s)}</span>
                    {s.trips > 0 && <span className="mt-1 block text-xs text-indigo-700 dark:text-indigo-300">Взвешен на весах: {s.trips} раз, {tonnesCompact(s.tonnes)}</span>}
                  </button>
                  <div className="mt-1 flex flex-wrap gap-2 px-1 text-xs">
                    {!isLoco && s.loco_asset_id && <Link className="text-blue-600 hover:underline dark:text-blue-400" href={historyHref({ asset_id: s.loco_asset_id })}>История локомотива {s.loco_inv_number ?? ""} →</Link>}
                    {isLoco && s.wagons.slice(0, 8).map((w) => <Link key={w.carriage_gtk_id} className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-200" href={historyHref({ asset_id: w.asset_id, carriage_gtk_id: w.carriage_gtk_id })}>{w.label}</Link>)}
                    {isLoco && s.wagons.length > 8 && <span className="text-gray-500">и ещё {s.wagons.length - 8}</span>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {!isLoco && (
          <section className={card}>
            <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Кто тянул: сколько времени за каким локомотивом</h2>
            {data.by_loco.length === 0 ? <p className="text-sm text-gray-500">Нет данных.</p> : (
              <ul className="space-y-2">{data.by_loco.map((l) => {
                const max = Math.max(...data.by_loco.map((x) => x.hours), 0.01)
                return <li key={`${l.loco_asset_id}-${l.label}`}><div className="flex justify-between text-sm"><span>{l.loco_asset_id ? <Link className="text-blue-600 hover:underline dark:text-blue-400" href={historyHref({ asset_id: l.loco_asset_id })}>{l.label}</Link> : l.label}</span><span className="tabular-nums text-gray-600 dark:text-gray-300">{hoursText(l.hours)} · {l.segments} раз</span></div><div className="mt-1 h-2 rounded-full bg-gray-100 dark:bg-gray-800"><div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-400" style={{ width: `${Math.max(3, (l.hours / max) * 100)}%` }} /></div></li>
              })}</ul>
            )}
          </section>
        )}
        <section className={`${card} ${isLoco ? "lg:col-span-2" : ""}`}>
          <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Взвешивания: что и сколько везли</h2>
          {data.trips.length === 0 ? <p className="text-sm text-gray-500">За период взвешиваний нет.</p> : (
            <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm">
              <thead className="text-xs text-gray-500"><tr>{["Когда", "Весы", isLoco ? "Груз в составе" : "Тонн", "Груз / карьер", "Локомотив"].map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}</tr></thead>
              <tbody>{data.trips.slice(0, 30).map((t) => (
                <tr key={t.train_id} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="px-2 py-1.5 whitespace-nowrap"><Link className="text-blue-600 hover:underline dark:text-blue-400" href={trainHref(t.train_id)}>{dt(t.started_at)}</Link></td>
                  <td className="px-2 py-1.5">{t.post_code}</td><td className="px-2 py-1.5 font-semibold">{t.tonnes !== null ? `${t.basis === "own" || t.basis === null ? "" : "≈ "}${fmt(t.tonnes)} т` : "—"}</td>
                  <td className="px-2 py-1.5">{t.cargo_name ?? "—"}</td><td className="px-2 py-1.5">{t.loco_number ?? "—"}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </section>
      </div>
    </div>
  )
}
