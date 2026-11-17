"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { fmt, trainHref, wagonHref, wagonKey, tonnesCompact, type LocoCard } from "@/lib/scales-insights"
import { STATUS_LABEL, flagLabel, type MatchStatus } from "@/lib/scales-view"
import { Loader2 } from "@/components/ui/icons"
import { AssetFacts, Back, Badge, Fact, MaintenancePanel, PeriodPicker, TotalsStats, dt } from "../../_components/cards"
import { HBars, Panel, WorkBars } from "../../_components/viz"

export default function LocoPage() {
  const { id } = useParams<{ id: string }>()
  const [days, setDays] = useState(30)
  const [card, setCard] = useState<LocoCard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.scales.locoCard(id, days).then((value) => { if (!cancelled) { setCard(value); setError(null) } }).catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить локомотив") })
    return () => { cancelled = true }
  }, [id, days])

  if (error) return <div className="space-y-3 p-6"><Back /><p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p></div>
  if (!card) return <div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Загружаю локомотив…</div>

  const w = card.wialon
  const onlineAge = w?.last_message_at ? (Date.now() - new Date(w.last_message_at).getTime()) / 60000 : null
  const online = onlineAge !== null && onlineAge <= 15

  return (
    <div className="mx-auto min-h-screen max-w-[1500px] space-y-4 bg-gray-50 p-5 sm:p-7 dark:bg-gray-950" data-testid="loco-card">
      <div className="flex flex-wrap items-center justify-between gap-2"><Back /><PeriodPicker days={days} onChange={setDays} /></div>

      <header className="rounded-3xl bg-gradient-to-br from-blue-900 via-indigo-900 to-slate-900 p-5 text-white shadow-lg sm:p-6">
        <div className="flex flex-wrap items-center gap-2 text-sm text-blue-100/80">
          <span>{card.asset.asset_type_name ?? "Локомотив"}</span>
          {card.asset.status_name && <Badge tone="blue">{card.asset.status_name}</Badge>}
          {w && <Badge tone={online ? "green" : "gray"}>{online ? "на связи (Wialon)" : `Wialon: ${dt(w.last_message_at)}`}</Badge>}
        </div>
        <h1 className="mt-1 text-3xl font-bold" data-testid="loco-title">{card.asset.inv_number}</h1>
        <p className="mt-1 text-sm text-blue-100/80">{[card.asset.model_name, card.asset.section_name, card.gtk?.garage_number ? `гаражный № ${card.gtk.garage_number}` : null].filter(Boolean).join(" · ")}</p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[["Составов за период", fmt(card.period.trips)], ["Перевезено", tonnesCompact(card.period.tonnes)], ["Вагонов в составе", card.avg_cars ? fmt(card.avg_cars, 1) : "—"], ["За всё время", tonnesCompact(card.all_time.tonnes)]]
            .map(([l, v]) => <div key={l} className="rounded-2xl bg-white/10 p-3 ring-1 ring-white/10"><div className="text-[11px] uppercase tracking-wide text-blue-100/70">{l}</div><div className="mt-0.5 text-xl font-bold tabular-nums">{v}</div></div>)}
        </div>
      </header>

      <TotalsStats period={card.period} allTime={card.all_time} days={days} unit="составов" />

      <Panel title={`Тонн по дням, ${days} дн.`}><WorkBars points={card.daily} color="#2563eb" /></Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Откуда везёт" hint="груз / карьер"><HBars items={card.by_cargo.map((s) => ({ key: s.key, label: s.label, value: s.tonnes, hint: `${s.trips} сост.` }))} color="#0ea5e9" /></Panel>
        <Panel title="Под какими экскаваторами"><HBars items={card.by_excavator.map((s) => ({ key: s.key, label: s.label, value: s.tonnes, hint: `${s.trips} сост.` }))} color="#a855f7" /></Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2"><AssetFacts asset={card.asset} title="Локомотив как основное средство" /><MaintenancePanel m={card.maintenance} /></div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Связи с другими системами" hint="GTK, Wialon и как оператор называл этот локомотив на весах">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Fact label="В GTK">{card.gtk ? `${card.gtk.name ?? ""} · гар. ${card.gtk.garage_number ?? "—"}` : "не связан"}</Fact>
            <Fact label="Модель по GTK">{card.gtk?.model_name ?? "—"}</Fact>
            <Fact label="В Wialon">{w ? w.name : "не связан"}</Fact>
            <Fact label="Скорость сейчас">{w?.speed !== null && w?.speed !== undefined ? `${fmt(w.speed, 0)} км/ч` : "—"}</Fact>
            <Fact label="Позиция GPS">{w?.lat !== null && w?.lat !== undefined && w?.lon !== null && w?.lon !== undefined ? <a className="text-blue-600 hover:underline dark:text-blue-400" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${w.lat}&mlon=${w.lon}#map=14/${w.lat}/${w.lon}`}>{fmt(w.lat, 4)}, {fmt(w.lon, 4)}</a> : "нет"}</Fact>
            <Fact label="Номера, набранные на весах">{card.numbers_used.length ? card.numbers_used.join(", ") : "—"}</Fact>
          </dl>
          {card.numbers_used.length > 1 && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">На весах этот локомотив набирали под несколькими номерами: проверьте, нет ли опечаток (исправление: «Весовая → Не распознано»).</p>}
        </Panel>
        <Panel title="Какие вагоны тянул" hint="за период; нажмите, чтобы открыть вагон">
          <HBars
            color="#10b981" items={card.top_wagons.map((x) => ({ key: wagonKey(x), label: x.label, value: x.tonnes, hint: `${x.trips} рейсов` }))}
            hrefOf={(key) => { const x = card.top_wagons.find((y) => wagonKey(y) === key); return x ? wagonHref(x) : null }}
          />
        </Panel>
      </div>

      <Panel title="Последние составы" hint="нажмите на время, чтобы открыть состав: вагоны, тонны, замечания">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs text-gray-500"><tr>{["Когда", "Весы", "Груз в составе", "Вагонов", "Груз / карьер", "Статус", "Замечания"].map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {card.recent.map((t) => (
                <tr key={t.id} data-testid="loco-recent" className="border-t border-gray-100 dark:border-gray-800">
                  <td className="px-2 py-1.5 whitespace-nowrap"><Link className="text-blue-600 hover:underline dark:text-blue-400" href={trainHref(t.id)}>{dt(t.started_at)}</Link></td>
                  <td className="px-2 py-1.5">{t.post_code}</td><td className="px-2 py-1.5 whitespace-nowrap font-semibold">{t.tonnes !== null ? `${t.net_source === "estimated" ? "≈ " : ""}${fmt(t.tonnes)} т` : "—"}</td>
                  <td className="px-2 py-1.5">{t.cars}</td><td className="px-2 py-1.5">{t.cargo_name ?? "—"}</td>
                  <td className="px-2 py-1.5 text-xs">{STATUS_LABEL[t.match_status as MatchStatus] ?? t.match_status}</td>
                  <td className="px-2 py-1.5 text-xs text-gray-600 dark:text-gray-400">{t.flags.map(flagLabel).join("; ") || "—"}</td>
                </tr>
              ))}
              {card.recent.length === 0 && <tr><td colSpan={7} className="px-2 py-6 text-center text-gray-500">Составов нет.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
