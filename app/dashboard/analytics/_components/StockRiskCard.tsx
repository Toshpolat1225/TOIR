"use client"

import { useMemo, useState } from "react"
import { AlertTriangle, CheckCircle, Clock, Info, Package, XCircle } from "@/components/ui/icons"
import type { StockRisk, StockRiskItem, StockStatus } from "@/lib/api"
import { fmtInt, fmtMoney, fmtNumber } from "@/lib/format"
import { coverageText, daysText, orderArrivalText, STOCK_STATUS, stockConclusion } from "@/lib/parts-analytics"
import { StatCard } from "./AnalyticsElements"
import { Body, Conclusion, Panel, Segmented, type Remote } from "./parts-ui"

type SortKey = "default" | "name" | "runs_out_in_days" | "need_by_days" | "shortfall_cost_year"
const SORTS: { value: SortKey; label: string }[] = [
  { value: "default", label: "По срочности" },
  { value: "runs_out_in_days", label: "По дням запаса" },
  { value: "need_by_days", label: "По сроку заказа" },
  { value: "shortfall_cost_year", label: "По сумме дефицита" },
  { value: "name", label: "По названию" },
]
const PAGE = 20

function sortItems(items: StockRiskItem[], key: SortKey): StockRiskItem[] {
  if (key === "default") return items
  const list = [...items]
  if (key === "name") return list.sort((a, b) => a.name.localeCompare(b.name, "ru"))
  if (key === "shortfall_cost_year") return list.sort((a, b) => b.shortfall_cost_year - a.shortfall_cost_year)
  const big = Number.POSITIVE_INFINITY
  return list.sort((a, b) => (a[key] ?? big) - (b[key] ?? big))
}

function Row({ item }: { item: StockRiskItem }) {
  const st = STOCK_STATUS[item.status]
  const stockText = item.stock === null ? "нет данных" : `${fmtNumber(item.stock)} ${item.unit ?? ""}`
  return (
    <li className="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">{item.name}</p>
          <p className="text-[10px] text-gray-500">{[item.code, item.department, item.supplier].filter(Boolean).join(" · ")}</p>
        </div>
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${st.badge}`}>{st.label}</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] sm:grid-cols-5">
        <p className="text-gray-500">Остаток <b className="block text-xs text-gray-900 dark:text-white">{stockText}</b></p>
        <p className="text-gray-500">Хватит на <b className="block text-xs text-gray-900 dark:text-white">{daysText(item.runs_out_in_days)}</b></p>
        <p className="text-gray-500">Срок поставки <b className="block text-xs text-gray-900 dark:text-white">{fmtInt(item.lead_time_days)} дн.{item.lead_time_unknown ? " (оценка)" : ""}</b></p>
        <p className="text-gray-500">Заказ придёт <b className="block text-xs text-gray-900 dark:text-white">{orderArrivalText(item)}</b></p>
        <p className="text-gray-500">Заказать через <b className={`block text-xs ${item.need_by_days !== null && item.need_by_days <= 0 ? "text-red-600 dark:text-red-400" : "text-gray-900 dark:text-white"}`}>{daysText(item.need_by_days)}</b></p>
      </div>
      {item.status !== "no_data" && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(["quarter", "half", "year"] as const).map((h) => {
            const c = item.coverage[h]
            const ok = c?.covers === true
            return (
              <span key={h} className={`rounded-md px-1.5 py-0.5 text-[10px] ${ok
                ? "bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300"
                : "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300"}`}>
                {h === "quarter" ? "Квартал" : h === "half" ? "Полгода" : "Год"}: <b>{coverageText(c, item.unit)}</b>
              </span>
            )
          })}
        </div>
      )}
      <p className="mt-2 text-[11px] leading-snug text-gray-600 dark:text-gray-300">{item.message}</p>
    </li>
  )
}

export function StockRiskCard({ remote }: { remote: Remote<StockRisk> }) {
  const [status, setStatus] = useState<StockStatus | "all">("all")
  const [sort, setSort] = useState<SortKey>("default")
  const [showAll, setShowAll] = useState(false)

  const items = remote.data?.items
  const rows = useMemo(() => {
    const filtered = (items ?? []).filter((i) => status === "all" || i.status === status)
    return sortItems(filtered, sort)
  }, [items, status, sort])

  const hasStock = (remote.data?.summary.no_data ?? 0) < (remote.data?.total ?? 0)

  return (
    <Panel title="Склад и риск дефицита" hint="Хватит ли остатка до прихода заказа: остаток, срок поставки, открытые заказы" icon={Package}>
      <Body remote={remote} empty={(d) => d.total === 0}>
        {(d) => {
          const s = d.summary
          return (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatCard title="Критично" value={fmtInt(s.critical)} subtitle="запас кончится раньше поставки" icon={XCircle} color="red" colorValue />
                <StatCard title="Заказать сейчас" value={fmtInt(s.order_now)} subtitle="срок заказа настал" icon={Clock} color="amber" />
                <StatCard title="В норме" value={fmtInt(s.ok)} subtitle="запаса достаточно" icon={CheckCircle} color="green" />
                <StatCard title="Нет остатков" value={fmtInt(s.no_data)} subtitle="нет данных из 1С" icon={Info} color="blue" />
              </div>
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <StatCard title="Дефицит, квартал" value={fmtMoney(s.shortfall_cost_quarter)} unit="сум" icon={AlertTriangle} color="red" />
                <StatCard title="Дефицит, полгода" value={fmtMoney(s.shortfall_cost_half)} unit="сум" icon={AlertTriangle} color="amber" />
                <StatCard title="Дефицит, год" value={fmtMoney(s.shortfall_cost_year)} unit="сум" icon={AlertTriangle} color="purple" />
              </div>

              {!hasStock && (
                <div role="status" className="mt-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200">
                  Остатки склада ещё не загружены, поэтому вердикты недоступны. Загрузите выгрузку из 1С (инструкция ниже).
                </div>
              )}

              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <Segmented
                  label="Фильтр по статусу"
                  value={status}
                  onChange={(v) => { setStatus(v); setShowAll(false) }}
                  options={[
                    { value: "all", label: `Все ${fmtInt(d.total)}` },
                    { value: "critical", label: `Критично ${fmtInt(s.critical)}` },
                    { value: "order_now", label: `Заказать ${fmtInt(s.order_now)}` },
                    { value: "ok", label: `В норме ${fmtInt(s.ok)}` },
                    { value: "no_data", label: `Нет данных ${fmtInt(s.no_data)}` },
                  ]}
                />
                <select
                  aria-label="Сортировка"
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortKey)}
                  className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-xs text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                >
                  {SORTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>

              {rows.length === 0 ? (
                <p className="py-6 text-center text-xs text-gray-400">В этом статусе позиций нет</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {(showAll ? rows : rows.slice(0, PAGE)).map((i) => <Row key={i.nomenclature_id} item={i} />)}
                </ul>
              )}
              {rows.length > PAGE && (
                <button type="button" onClick={() => setShowAll((v) => !v)} className="mt-3 w-full rounded-lg border border-violet-200 py-1.5 text-xs font-semibold text-violet-700 hover:bg-violet-50 dark:border-violet-800 dark:text-violet-300 dark:hover:bg-violet-950">
                  {showAll ? "Свернуть до 20" : `Показать все (${fmtInt(rows.length)})`}
                </button>
              )}
              {d.total > d.items.length && <p className="mt-2 text-[11px] text-gray-500">Загружено {fmtInt(d.items.length)} из {fmtInt(d.total)} позиций, самые срочные.</p>}

              <Conclusion>{stockConclusion(s)}</Conclusion>

              <details className="mt-3 rounded-lg border border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
                <summary className="cursor-pointer font-semibold text-gray-700 dark:text-gray-200">Как загрузить остатки из 1С</summary>
                <ol className="mt-2 list-decimal space-y-1 pl-4 text-gray-600 dark:text-gray-300">
                  <li>Выгрузите из 1С остатки (а также открытые заказы и сроки поставки) в .xlsx или .csv по шаблону.</li>
                  <li>Администратор загружает файл через командную строку сервера: проверка без записи, затем с параметром применения.</li>
                  <li>Шаблоны и подробная инструкция: docs/templates/README_1C.md.</li>
                </ol>
              </details>
            </>
          )
        }}
      </Body>
    </Panel>
  )
}
