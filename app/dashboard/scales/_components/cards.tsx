"use client"

import Link from "next/link"
import {
  SERVICE_STATUS_LABEL, fmt, percent, sinceServiceText, tonnesCompact, type AssetIdentity, type Maintenance, type Totals,
} from "@/lib/scales-insights"
import { ArrowLeft } from "@/components/ui/icons"
import { Empty, Panel, Stat } from "./viz"

export const dt = (iso: string | null | undefined, withTime = true): string => {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString("ru-RU", withTime ? { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "2-digit", year: "numeric" })
}

export function Back({ href = "/dashboard/scales", label = "Весовая" }: { href?: string; label?: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline dark:text-blue-400">
      <ArrowLeft className="h-4 w-4" /> {label}
    </Link>
  )
}

export function Badge({ children, tone = "gray" }: { children: React.ReactNode; tone?: "gray" | "green" | "amber" | "red" | "blue" }) {
  const cls = {
    gray: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300", green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300", red: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
    blue: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  }[tone]
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>
}

export function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="mt-0.5 truncate text-sm font-medium text-gray-900 dark:text-gray-100">{children ?? "—"}</dd>
    </div>
  )
}

export function PeriodPicker({ days, onChange, options = [30, 90, 365] }: { days: number; onChange: (d: number) => void; options?: number[] }) {
  return (
    <div className="inline-flex overflow-hidden rounded-full ring-1 ring-gray-300 dark:ring-gray-700" role="group" aria-label="Период">
      {options.map((d) => (
        <button key={d} type="button" aria-pressed={days === d} onClick={() => onChange(d)} className={`px-3 py-1 text-sm ${days === d ? "bg-blue-600 text-white" : "bg-white text-gray-800 dark:bg-gray-900 dark:text-gray-100"}`}>
          {d === 365 ? "год" : `${d} дн.`}
        </button>
      ))}
    </div>
  )
}

/** The asset as TOIR knows it: type, status, section, model, mileage, service dates, with a way into the asset card. */
export function AssetFacts({ asset, title = "Основное средство" }: { asset: AssetIdentity; title?: string }) {
  return (
    <Panel title={title} hint="данные карточки ОС">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        <Fact label="Инв. №">{asset.inv_number}</Fact>
        <Fact label="Тип">{asset.asset_type_name ?? asset.asset_type}</Fact>
        <Fact label="Статус">{asset.status_name ?? asset.status}</Fact>
        <Fact label="Участок">{asset.section_name ?? "—"}</Fact>
        <Fact label="Модель">{asset.model_name ?? "—"}</Fact>
        <Fact label="Владелец">{asset.owner ?? "—"}</Fact>
        <Fact label="Пробег по ОС">{asset.mileage !== null ? `${fmt(asset.mileage)} км` : "—"}</Fact>
        <Fact label="Последнее ТО (в карточке)">{dt(asset.last_maint_date, false)}</Fact>
        <Fact label="Следующее ТО (в карточке)">{dt(asset.next_maint_date, false)}</Fact>
      </dl>
      <Link href={`/dashboard/directories/assets?q=${encodeURIComponent(asset.inv_number)}`} className="mt-3 inline-block text-sm text-blue-600 hover:underline dark:text-blue-400">Открыть карточку ОС (привязки, паспорт) →</Link>
    </Panel>
  )
}

/** How hard the asset worked, set against its maintenance: the scales know the work, maintenance knows the service. */
export function MaintenancePanel({ m }: { m: Maintenance }) {
  return (
    <Panel title="Наработка и обслуживание" hint="связь весов с ТО и ремонтами">
      <div className={`rounded-xl p-3 text-sm ${m.last_service_at ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200" : "bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"}`}>
        {sinceServiceText(m)}
        {m.last_service_source && <span className="ml-1 text-xs opacity-70">(источник: {m.last_service_source})</span>}
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">План ТО</h3>
          {m.plans.length === 0 ? <p className="text-sm text-gray-500">Открытых пунктов плана нет.</p> : (
            <ul className="space-y-1.5">
              {m.plans.map((p) => (
                <li key={p.plan_id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate"><b>{p.interval_code}</b> · {p.interval_name}</span>
                  <span className="shrink-0 text-xs text-gray-500">{SERVICE_STATUS_LABEL[p.status] ?? p.status}{p.scheduled_date ? ` · ${dt(p.scheduled_date, false)}` : ""}</span>
                </li>
              ))}
            </ul>
          )}
          <Link href="/dashboard/maintenance" className="mt-2 inline-block text-xs text-blue-600 hover:underline dark:text-blue-400">Открыть «ИИ-ТО и ремонты» →</Link>
        </div>
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Наряды (всего {m.work_orders_total})</h3>
          {m.work_orders.length === 0 ? <p className="text-sm text-gray-500">Нарядов по этому ОС нет.</p> : (
            <ul className="space-y-1.5">
              {m.work_orders.map((o) => (
                <li key={o.id} className="text-sm">
                  <span className="font-medium">{o.number}</span> <Badge tone={o.status === "completed" ? "green" : o.status === "cancelled" ? "gray" : "blue"}>{SERVICE_STATUS_LABEL[o.status] ?? o.status}</Badge>
                  <div className="truncate text-xs text-gray-500">{dt(o.date_start ?? null, false)} · {o.description}</div>
                </li>
              ))}
            </ul>
          )}
          <Link href="/dashboard/work-orders" className="mt-2 inline-block text-xs text-blue-600 hover:underline dark:text-blue-400">Открыть наряды →</Link>
        </div>
      </div>
    </Panel>
  )
}

export function TotalsStats({ period, allTime, days, unit = "рейсов" }: { period: Totals; allTime: Totals; days: number; unit?: string }) {
  const ownShare = period.trips ? period.own_trips / period.trips : null
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
      <Stat label={`${unit[0].toUpperCase()}${unit.slice(1)} за ${days} дн.`} value={fmt(period.trips)} hint={`всего за всё время: ${fmt(allTime.trips)}`} />
      <Stat label="Перевезено" value={tonnesCompact(period.tonnes)} hint={`за всё время: ${tonnesCompact(allTime.tonnes)}`} />
      <Stat label="В среднем за рейс" value={period.avg_tonnes ? `${fmt(period.avg_tonnes, 1)} т` : "—"} />
      <Stat label="Точность" value={percent(ownShare)} hint="рейсов по собственному взвешиванию вагона" tone={ownShare !== null && ownShare < 0.5 ? "warn" : "plain"} />
      <Stat label="Перегруз" value={fmt(period.overload_trips)} hint="рейсов выше 105 т" tone={period.overload_trips ? "warn" : "plain"} />
      <Stat label="Последний рейс" value={<span className="text-base">{dt(period.last_at)}</span>} />
    </div>
  )
}

export const NoData = ({ text }: { text: string }) => <Empty text={text} />
