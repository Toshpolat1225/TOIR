"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import { fmt, parseWagonKey, trainHref, type WagonCard } from "@/lib/scales-insights"
import { BASIS_LABEL, tripTonnes } from "@/lib/scales-view"
import { Loader2 } from "@/components/ui/icons"
import { AssetFacts, Back, Badge, Fact, MaintenancePanel, PeriodPicker, TotalsStats, dt } from "../../_components/cards"
import { HBars, Panel, WorkBars } from "../../_components/viz"

export default function WagonPage() {
  const { key } = useParams<{ key: string }>()
  const [days, setDays] = useState(30)
  const [card, setCard] = useState<WagonCard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const params = useMemo(() => parseWagonKey(key), [key])

  useEffect(() => {
    let cancelled = false
    api.scales.wagonCard({ ...params, days }).then((value) => { if (!cancelled) { setCard(value); setError(null) } }).catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить вагон") })
    return () => { cancelled = true }
  }, [params, days])

  if (error) return <div className="space-y-3 p-6"><Back /><p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p></div>
  if (!card) return <div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Загружаю вагон…</div>

  const title = card.asset?.inv_number ?? card.gtk?.inventory_number ?? card.gtk?.name ?? `GTK ${card.gtk?.carriage_gtk_id}`

  return (
    <div className="mx-auto min-h-screen max-w-[1500px] space-y-4 bg-gray-50 p-5 sm:p-7 dark:bg-gray-950" data-testid="wagon-card">
      <div className="flex flex-wrap items-center justify-between gap-2"><Back /><PeriodPicker days={days} onChange={setDays} /></div>

      <header className="rounded-3xl bg-gradient-to-br from-emerald-900 via-teal-900 to-slate-900 p-5 text-white shadow-lg sm:p-6">
        <div className="flex flex-wrap items-center gap-2 text-sm text-emerald-100/80">
          <span>{card.asset?.asset_type_name ?? "Вагон"}</span>
          {card.asset ? <Badge tone="green">связан с ОС</Badge> : <Badge tone="amber">не связан с ОС</Badge>}
          {card.asset?.status_name && <Badge tone="blue">{card.asset.status_name}</Badge>}
          {card.gtk?.is_loaded !== null && card.gtk?.is_loaded !== undefined && <Badge tone={card.gtk.is_loaded ? "amber" : "gray"}>{card.gtk.is_loaded ? "сейчас гружёный (GTK)" : "сейчас порожний (GTK)"}</Badge>}
        </div>
        <h1 className="mt-1 text-3xl font-bold" data-testid="wagon-title">{title}</h1>
        <p className="mt-1 text-sm text-emerald-100/80">{[card.asset?.model_name ?? card.gtk?.model_name, card.asset?.section_name].filter(Boolean).join(" · ") || "Данные карточки не заполнены"}</p>
      </header>

      {!card.asset && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Этот вагон известен только по GTK. Свяжите его с основным средством (<Link className="underline" href="/dashboard/os/gtk">Данные GTK → привязки</Link>), и здесь появятся ОС, ТО, наряды и наработка с последнего ТО; прошлые рейсы подтянутся сами.
        </p>
      )}

      <TotalsStats period={card.period} allTime={card.all_time} days={days} />

      <Panel title={`Тонн по дням, ${days} дн.`} hint="каждый столбец — день; наведите для подробностей"><WorkBars points={card.daily} color="#10b981" /></Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Откуда везёт" hint="груз / карьер"><HBars items={card.by_cargo.map((s) => ({ key: s.key, label: s.label, value: s.tonnes, hint: `${s.trips} рейсов` }))} color="#0ea5e9" /></Panel>
        <Panel title="Какими локомотивами" hint="с кем ходит этот вагон"><HBars items={card.by_loco.map((s) => ({ key: s.key, label: s.label, value: s.tonnes, hint: `${s.trips} рейсов` }))} color="#2563eb" /></Panel>
        <Panel title="Под какими экскаваторами" hint="кто его грузил"><HBars items={card.by_excavator.map((s) => ({ key: s.key, label: s.label, value: s.tonnes, hint: `${s.trips} рейсов` }))} color="#a855f7" /></Panel>
      </div>

      {card.asset && <div className="grid gap-4 xl:grid-cols-2"><AssetFacts asset={card.asset} />{card.maintenance && <MaintenancePanel m={card.maintenance} />}</div>}

      {card.gtk && (
        <Panel title="Вагон в GTK" hint="как его видит система слежения">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <Fact label="Название">{card.gtk.name}</Fact><Fact label="Рег. номер">{card.gtk.reg_number}</Fact><Fact label="Инв. номер GTK">{card.gtk.inventory_number}</Fact><Fact label="Модель">{card.gtk.model_name}</Fact>
            <Fact label="Активен">{card.gtk.is_active === null ? "—" : card.gtk.is_active ? "да" : "нет"}</Fact>
            <Fact label="Координаты">{card.gtk.lat !== null && card.gtk.lon !== null ? <a className="text-blue-600 hover:underline dark:text-blue-400" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${card.gtk.lat}&mlon=${card.gtk.lon}#map=14/${card.gtk.lat}/${card.gtk.lon}`}>{fmt(card.gtk.lat, 4)}, {fmt(card.gtk.lon, 4)}</a> : "нет"}</Fact>
          </dl>
        </Panel>
      )}

      <Panel title="Последние рейсы" hint="какой вагон, когда, сколько тонн, за каким локомотивом; нажмите на время, чтобы открыть весь состав">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs text-gray-500"><tr>{["Когда", "Тонн", "Основание", "Позиция", "Локомотив", "Груз", "Весы"].map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {card.recent.map((r) => (
                <tr key={`${r.train_id}-${r.position}`} data-testid="wagon-recent" className="border-t border-gray-100 dark:border-gray-800">
                  <td className="px-2 py-1.5 whitespace-nowrap"><Link className="text-blue-600 hover:underline dark:text-blue-400" href={trainHref(r.train_id)}>{dt(r.started_at)}</Link></td>
                  <td className="px-2 py-1.5 whitespace-nowrap font-semibold">{tripTonnes({ tonnes: r.tonnes, basis: r.basis })}</td>
                  <td className="px-2 py-1.5 text-xs text-gray-600 dark:text-gray-400">{BASIS_LABEL[r.basis]}</td>
                  <td className="px-2 py-1.5">{r.position ?? "—"}</td><td className="px-2 py-1.5">{r.loco_number ?? "—"}</td><td className="px-2 py-1.5">{r.cargo_name ?? "—"}</td><td className="px-2 py-1.5">{r.post_code}</td>
                </tr>
              ))}
              {card.recent.length === 0 && <tr><td colSpan={7} className="px-2 py-6 text-center text-gray-500">Рейсов нет.</td></tr>}
            </tbody>
          </table>
        </div>
        <Link href={`/dashboard/scales`} className="mt-2 inline-block text-xs text-blue-600 hover:underline dark:text-blue-400">Все рейсы и выгрузка в Excel: «Весовая → Вагоны» →</Link>
      </Panel>
    </div>
  )
}
