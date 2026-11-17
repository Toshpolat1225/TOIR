"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { durationMinutes, fmt, locoHref, n, tonnesCompact, trainHref, wagonHref, type TrainCard } from "@/lib/scales-insights"
import { STATUS_LABEL, flagLabel, type MatchStatus } from "@/lib/scales-view"
import { Loader2 } from "@/components/ui/icons"
import { Back, Badge, Fact, dt } from "../../_components/cards"
import { Panel, Stat, TrainStrip } from "../../_components/viz"

const STATUS_TONE: Record<string, "green" | "amber" | "red" | "gray"> = { ok: "green", no_gtk_train: "amber", no_loco: "red", pending: "gray", excluded: "gray" }
const FLAG_HELP: Record<string, string> = {
  count_mismatch: "Число вагонов на весах не совпало с числом вагонов состава в GTK: возможно, вагон отцепили или добавили. Тонны делятся поровну.",
  default_tare: "Тара вагонов не взвешивалась, программа подставила 49 т: масса нетто приблизительная.",
  overload: "Хотя бы один вагон загружен выше грузоподъёмности 105 т.",
  negative_net: "У вагона отрицательная масса нетто: вероятно, сбой датчика или ошибка тары.",
  no_wagon_rows: "Весы не передали строки по вагонам; масса состава оценена по общему весу.",
  partial_wagon_rows: "Строк по вагонам меньше, чем заявлено в составе: масса оценена.",
  estimated_net: "Масса груза оценена по весу состава (вес весов минус типовая поправка), а не по взвешиванию вагонов.",
  traction_inferred: "Сколько единиц составляют тяговый агрегат, определено по числу вагонов в GTK.",
}

export default function TrainPage() {
  const { id } = useParams<{ id: string }>()
  const [card, setCard] = useState<TrainCard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setCard(null)
    api.scales.trainCard(id).then((value) => { if (!cancelled) { setCard(value); setError(null) } }).catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить состав") })
    return () => { cancelled = true }
  }, [id])

  if (error) return <div className="space-y-3 p-6"><Back /><p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p></div>
  if (!card) return <div className="p-6 text-sm text-gray-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Загружаю состав…</div>

  const minutes = durationMinutes(card.started_at, card.finished_at)
  const dumps = card.units.filter((u) => u.kind === "dump")
  const over = dumps.filter((u) => n(u.net_t) > n(u.capacity_t || 105))
  const maxNet = dumps.reduce((m, u) => Math.max(m, n(u.net_t)), 0)
  const speeds = card.units.map((u) => n(u.speed_kmh)).filter(Boolean)
  const tractionTare = card.units.filter((u) => u.kind === "traction").reduce((s, u) => s + n(u.tare_t), 0)

  return (
    <div className="mx-auto min-h-screen max-w-[1500px] space-y-4 bg-gray-50 p-5 sm:p-7 dark:bg-gray-950" data-testid="train-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Back />
        <div className="flex gap-2 text-sm">
          {card.prev_id ? <Link className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900" href={trainHref(card.prev_id)}>← Предыдущий состав</Link> : null}
          {card.next_id ? <Link className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900" href={trainHref(card.next_id)}>Следующий состав →</Link> : null}
        </div>
      </div>

      <header className="rounded-3xl bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-900 p-5 text-white shadow-lg sm:p-6">
        <div className="flex flex-wrap items-center gap-2 text-sm text-sky-100/80">
          <span>{card.post_name}</span><span>·</span><span>запись № {card.src_id}</span>
          <Badge tone={STATUS_TONE[card.match_status] ?? "gray"}>{STATUS_LABEL[card.match_status as MatchStatus] ?? card.match_status}</Badge>
        </div>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Состав {card.loco_number ? `локомотива ${card.loco_number}` : "(локомотив не указан)"}</h1>
        <p className="mt-1 text-sm text-sky-100/80">{dt(card.started_at)}{card.finished_at ? ` — ${dt(card.finished_at)}` : ""}{minutes !== null ? ` · взвешивали ${minutes} мин` : ""}</p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Груз в составе", tonnesCompact(card.net_total_t) + (card.net_source === "estimated" ? " (≈ оценка)" : "")],
            ["Вагонов с грузом", `${card.dump_count || card.carriages.length}`],
            ["В среднем на вагон", card.avg_car_t ? `${fmt(card.avg_car_t, 1)} т` : "—"],
            ["Вес по весам", tonnesCompact(card.reported_weight_t)],
          ].map(([l, v]) => <div key={l} className="rounded-2xl bg-white/10 p-3 ring-1 ring-white/10"><div className="text-[11px] uppercase tracking-wide text-sky-100/70">{l}</div><div className="mt-0.5 text-xl font-bold tabular-nums">{v}</div></div>)}
        </div>
      </header>

      <Panel title="Состав на весах" hint="слева направо, как проезжал: тяговый агрегат и вагоны; высота заливки = груз к грузоподъёмности 105 т: зелёный — в норме, жёлтый — выше 105 т, красный — выше 115 т. Клик по вагону откроет его карточку">
        <TrainStrip units={card.units} />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Откуда берутся тонны" hint="почему «вес по весам» больше фактического груза" className="lg:col-span-2">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Вес по весам" value={tonnesCompact(card.reported_weight_t)} hint="сумма брутто минус тара по умолчанию" />
            <Stat label="Тяговый агрегат" value={tractionTare ? `${fmt(tractionTare)} т` : "—"} hint={`${card.traction_count} ед., их тара входит в вес весов`} />
            <Stat label="Груз по вагонам" value={tonnesCompact(card.net_total_t)} hint="сумма нетто вагонов" tone="good" />
            <Stat label="Разница" value={card.offset_t ? `${fmt(card.offset_t)} т` : "—"} hint="вес весов − груз" />
          </div>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">Весы вычитают из брутто стандартную тару 49 т у <b>каждой</b> единицы, включая тяжёлый тяговый агрегат. Поэтому в отчётах весов состав «тяжелее» на ~190 т; для учёта работы вагонов TOIR берёт только нетто вагонов.{card.doc_weight_t ? ` По документам заявлено: ${fmt(card.doc_weight_t)} т.` : ""}</p>
        </Panel>
        <Panel title="Цифры состава">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Макс. вагон" value={`${fmt(maxNet, 1)} т`} tone={maxNet > 105 ? "warn" : "plain"} />
            <Stat label="Перегруженных" value={over.length} tone={over.length ? "warn" : "plain"} />
            <Stat label="Скорость, км/ч" value={speeds.length ? fmt(speeds.reduce((a, b) => a + b, 0) / speeds.length, 1) : "—"} hint="средняя при взвешивании" />
            <Stat label="Строк по вагонам" value={`${card.wagon_rows}/${card.declared_wagons ?? "—"}`} hint="получено / заявлено" tone={card.declared_wagons && card.wagon_rows < card.declared_wagons ? "warn" : "plain"} />
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Кто тянул" hint="локомотив и его связи">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Fact label="Номер, набранный оператором">{card.loco_number ?? "не указан"}</Fact>
            <Fact label="Определён как">{card.loco ? <Link className="text-blue-600 hover:underline dark:text-blue-400" href={locoHref(card.loco.asset_id)}>{card.loco.inv_number} · {card.loco.model_name ?? card.loco.asset_type_name}</Link> : "не определён"}</Fact>
            <Fact label="Участок">{card.loco?.section_name ?? "—"}</Fact>
            <Fact label="Статус ОС">{card.loco?.status_name ?? "—"}</Fact>
            <Fact label="Локомотив в GTK">{card.gtk_loco ? `${card.gtk_loco.name ?? ""} (гар. ${card.gtk_loco.garage_number ?? "—"})` : "—"}</Fact>
            <Fact label="Способ определения">{{ gtk_garage: "по гаражному номеру GTK", alias: "исправлено оператором (псевдоним)", forced: "состав выбран оператором" }[card.match_method ?? ""] ?? "—"}</Fact>
          </dl>
        </Panel>
        <Panel title="Состав в GTK" hint="какие вагоны GTK видел за этим локомотивом в момент взвешивания">
          {card.gtk_train ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              <Fact label="Состав GTK">{card.gtk_train.title ?? `№ ${card.gtk_train.number}`}</Fact>
              <Fact label="Начат в GTK">{dt(card.gtk_train.begin_time)}</Fact>
              <Fact label="Вагонов в GTK">{card.carriages.length}</Fact>
              <Fact label="Связано с ОС">{card.carriages.filter((c) => c.asset_id).length} из {card.carriages.length}</Fact>
              <Fact label="Груз">{card.cargo_name ?? "—"}</Fact>
              <Fact label="Экскаватор / оператор">{card.excavator ?? "—"} / {card.operator_code ?? "—"}</Fact>
            </dl>
          ) : <p className="text-sm text-gray-500">GTK не показал состав за этим локомотивом в это время (история GTK ведётся с 04.11.2026, либо локомотив не числится головным в составе). Исправить можно в разделе «Не распознано».</p>}
        </Panel>
      </div>

      {card.flags.length > 0 && (
        <Panel title="Замечания по составу">
          <ul className="space-y-1.5 text-sm">{card.flags.map((f) => <li key={f}><Badge tone="amber">{flagLabel(f)}</Badge> <span className="text-gray-600 dark:text-gray-400">{FLAG_HELP[f] ?? ""}</span></li>)}</ul>
        </Panel>
      )}
      {card.corrections.length > 0 && (
        <Panel title="Исправления оператора, применённые к этому составу">
          <ul className="space-y-1 text-sm">{card.corrections.map((c) => <li key={c.id}>{c.kind === "loco_alias" ? `Номер «${c.loco_number}» = этот локомотив` : c.kind === "train_gtk" ? "Состав привязан к составу GTK вручную" : "Состав исключён"}{c.note ? ` · ${c.note}` : ""} <span className="text-xs text-gray-500">{dt(c.created_at)}</span></li>)}</ul>
        </Panel>
      )}

      <Panel title="Взвешивание по единицам" hint="что именно записали весы для каждой единицы состава">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="text-xs text-gray-500"><tr>{["Поз.", "Вид", "Вагон (по порядку GTK)", "Брутто, т", "Тара, т", "Нетто, т", "К норме, т", "Скорость", "Осей", "Время"].map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {card.units.map((u, i) => (
                <tr key={`${u.position}-${i}`} data-testid="unit-row" className="border-t border-gray-100 dark:border-gray-800">
                  <td className="px-2 py-1.5">{u.position}</td>
                  <td className="px-2 py-1.5">{u.kind === "traction" ? <Badge tone="blue">тяга</Badge> : "вагон"}</td>
                  <td className="px-2 py-1.5">{u.carriage_gtk_id !== null ? <Link className="text-blue-600 hover:underline dark:text-blue-400" href={wagonHref({ asset_id: u.asset_id, carriage_gtk_id: u.carriage_gtk_id })}>{u.inv_number ?? u.carriage_name ?? `GTK ${u.carriage_gtk_id}`}</Link> : <span className="text-gray-400">—</span>}</td>
                  <td className="px-2 py-1.5 tabular-nums">{fmt(u.gross_t, 1)}</td><td className="px-2 py-1.5 tabular-nums">{fmt(u.tare_t, 1)}</td>
                  <td className={`px-2 py-1.5 font-semibold tabular-nums ${n(u.net_t) > n(u.capacity_t || 105) && u.kind === "dump" ? "text-rose-600" : ""}`}>{u.kind === "traction" ? "—" : fmt(u.net_t, 1)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{u.kind === "traction" ? "—" : fmt(u.overload_t, 1)}</td><td className="px-2 py-1.5 tabular-nums">{fmt(u.speed_kmh, 1)}</td>
                  <td className="px-2 py-1.5">{u.axles ?? "—"}</td><td className="px-2 py-1.5 whitespace-nowrap">{dt(u.weighed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
