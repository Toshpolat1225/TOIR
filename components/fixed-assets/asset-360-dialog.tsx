"use client"

// «Паспорт 360°»: one window with everything the other pages know about ONE asset
// (GPS Wialon ↔ GTK, Карта, Данные GTK, Данные Wialon, Состав, Весовая, Ремонты). It reads the very same endpoints as those pages.
import Link from "next/link"
import { useEffect, useState } from "react"
import { api, type AssetOverview, type GtkFixedAssetDetail, type WorkOrder } from "@/lib/api"
import type { GpsAssetDetail } from "@/lib/gps-view"
import { POSITION_HINT, POSITION_LABEL, positionColor, type PositionVerdict } from "@/lib/gps-view"
import type { LocoCard, WagonCard } from "@/lib/scales-insights"
import { X } from "@/components/ui/icons"

export type Asset360Subject = {
  id: string; name: string; invNumber: string; assetType: string; sectionName: string
  mileage: string; wialonMileage: string; engineHours: string; speed: string
  lastMessageAt: string | null; wialonOnline: boolean | null; unitId: string | null; statusLabel: string
}
export type Asset360Tab = "summary" | "gps" | "wialon" | "gtk" | "scales" | "repairs"

const TABS: { id: Asset360Tab; label: string; icon: string }[] = [
  { id: "summary", label: "Сводка", icon: "◎" },
  { id: "gps", label: "GPS и карта", icon: "📍" },
  { id: "wialon", label: "Wialon", icon: "📡" },
  { id: "gtk", label: "GTK и состав", icon: "🚆" },
  { id: "scales", label: "Весовая", icon: "⚖" },
  { id: "repairs", label: "Ремонты", icon: "🔧" },
]
const LOCO = new Set(["locomotive", "diesel", "special_self_propelled"])

export const fmtDate = (iso: string | null | undefined): string => {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })
}
export const fmtDay = (iso: string | null | undefined): string => {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" })
}
const ago = (iso: string | null | undefined): string => {
  if (!iso) return "нет данных"
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (m < 60) return `${m} мин назад`
  if (m < 60 * 48) return `${Math.round(m / 60)} ч назад`
  return `${Math.round(m / 1440)} дн назад`
}
const num = (v: string | number | null | undefined, d = 0): string => {
  const x = Number(v)
  return v === null || v === undefined || v === "" || !Number.isFinite(x) ? "—" : x.toLocaleString("ru-RU", { maximumFractionDigits: d })
}

function Tile({ title, value, sub, color, onClick }: { title: string; value: string; sub?: string; color: string; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} disabled={!onClick}
      className="group relative overflow-hidden rounded-2xl border border-gray-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md disabled:cursor-default disabled:hover:translate-y-0 dark:border-gray-700 dark:bg-gray-900">
      <span className="absolute inset-y-0 left-0 w-1.5" style={{ background: color }} />
      <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">{title}</p>
      <p className="mt-1 text-lg font-bold text-gray-900 dark:text-white">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{sub}</p>}
    </button>
  )
}
function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-gray-100 py-2 text-sm last:border-0 dark:border-gray-800">
      <span className="text-gray-500 dark:text-gray-400">{k}</span><span className="text-right font-medium text-gray-900 dark:text-gray-100">{v}</span>
    </div>
  )
}
function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900"><p className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-400">{title}</p>{children}</div>
}
const Note = ({ children }: { children: React.ReactNode }) => <p className="rounded-xl bg-gray-50 px-4 py-6 text-center text-sm text-gray-500 dark:bg-gray-800/50 dark:text-gray-400">{children}</p>

function useLoad<T>(enabled: boolean, load: () => Promise<T>, key: string) {
  const [state, set] = useState<{ status: "idle" | "loading" | "ok" | "denied" | "error"; data: T | null }>({ status: "idle", data: null })
  useEffect(() => {
    if (!enabled) return
    let live = true
    set({ status: "loading", data: null })
    load().then((data) => live && set({ status: "ok", data }))
      .catch((e: unknown) => live && set({ status: (e as { status?: number })?.status === 403 ? "denied" : "error", data: null }))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, key])
  return state
}
function Async<T>({ s, children }: { s: { status: string; data: T | null }; children: (d: T) => React.ReactNode }) {
  if (s.status === "loading" || s.status === "idle") return <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800" />)}</div>
  if (s.status === "denied") return <Note>Раздел недоступен для вашей роли.</Note>
  if (s.status === "error" || s.data === null) return <Note>Не удалось загрузить данные.</Note>
  return <>{children(s.data)}</>
}

export function Asset360Dialog({ subject, overview, initialTab, onClose, onEdit }: {
  subject: Asset360Subject; overview: AssetOverview | undefined; initialTab: Asset360Tab; onClose: () => void; onEdit?: () => void
}) {
  const [tab, setTab] = useState<Asset360Tab>(initialTab)
  const isLoco = LOCO.has(subject.assetType)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const gps = overview?.gps ?? null
  const verdict = (gps?.verdict ?? null) as PositionVerdict | null
  const vColor = verdict ? positionColor(verdict) : "#94a3b8"
  const gpsDetail = useLoad<GpsAssetDetail>(tab === "gps" && isLoco, () => api.gps.asset(subject.id, { days: 1, track_days: 1 }), subject.id)
  const gtkDetail = useLoad<GtkFixedAssetDetail>(tab === "gtk", () => api.gtk.fixedAssetDetail(subject.id), subject.id)
  const locoCard = useLoad<LocoCard>(tab === "scales" && isLoco, () => api.scales.locoCard(subject.id, 30), subject.id)
  const wagonCard = useLoad<WagonCard>(tab === "scales" && !isLoco, () => api.scales.wagonCard({ asset_id: subject.id, days: 30 }), subject.id)
  const orders = useLoad<{ items: WorkOrder[]; total: number }>(tab === "repairs", () => api.workOrders.list({ fixed_asset_id: subject.id, limit: 8 }), subject.id)

  const m = overview?.maintenance
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/60 p-3 backdrop-blur-sm sm:p-8" onClick={onClose} role="dialog" aria-modal="true" aria-label={`Паспорт 360° ${subject.name}`}>
      <div className="w-full max-w-4xl overflow-hidden rounded-3xl bg-gray-50 shadow-2xl ring-1 ring-black/10 dark:bg-gray-950" onClick={(e) => e.stopPropagation()}>
        <div className="relative overflow-hidden bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-800 px-6 pb-5 pt-6 text-white">
          <div className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-white/10 blur-2xl" />
          <button type="button" onClick={onClose} aria-label="Закрыть" className="absolute right-4 top-4 rounded-full bg-white/10 p-2 hover:bg-white/20"><X className="h-4 w-4" /></button>
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-200">Паспорт 360° · {isLoco ? "локомотив" : "вагон"}</p>
          <h2 className="mt-1 text-2xl font-extrabold">{subject.name}</h2>
          <p className="mt-1 text-sm text-blue-100">Инв. № {subject.invNumber || "—"} · {subject.sectionName || "участок не назначен"} · {subject.statusLabel}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold"><span className="h-2 w-2 rounded-full" style={{ background: vColor, boxShadow: `0 0 8px ${vColor}` }} />{verdict ? POSITION_LABEL[verdict] ?? verdict : gps ? (gps.source === "train" ? "Позиция по составу" : "Есть позиция") : "GPS: нет данных"}</span>
            {overview?.gtk && <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold">Состав № {overview.gtk.train_number ?? overview.gtk.train_gtk_id}</span>}
            {onEdit && <button type="button" onClick={onEdit} className="rounded-full bg-white px-3 py-1 text-xs font-bold text-blue-900 hover:bg-blue-50">Паспорт и редактирование →</button>}
          </div>
        </div>
        <div className="flex gap-1 overflow-x-auto border-b border-gray-200 bg-white px-3 pt-2 dark:border-gray-800 dark:bg-gray-900">
          {TABS.map((t) => (
            <button key={t.id} type="button" onClick={() => setTab(t.id)}
              className={`whitespace-nowrap rounded-t-xl px-3.5 py-2 text-sm font-semibold transition ${tab === t.id ? "bg-gray-50 text-blue-700 shadow-[inset_0_-3px_0_#2563eb] dark:bg-gray-950 dark:text-blue-300" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}>
              <span className="mr-1.5">{t.icon}</span>{t.label}
            </button>
          ))}
        </div>

        <div className="max-h-[68vh] space-y-3 overflow-y-auto p-5">
          {tab === "summary" && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Tile title="GPS Wialon ↔ GTK" color={vColor} value={verdict ? POSITION_LABEL[verdict] ?? verdict : gps ? (gps.source === "train" ? "По составу" : "Есть позиция") : "Нет данных"} sub={gps ? `${ago(gps.position_at)}${gps.diff_m != null ? ` · расхождение ${Math.round(gps.diff_m)} м` : ""}` : "ни один трекер не отдаёт позицию"} onClick={() => setTab("gps")} />
                <Tile title="Wialon" color="#0ea5e9" value={subject.unitId ? `${num(subject.wialonMileage)} км` : "Нет трекера"} sub={subject.unitId ? `${subject.wialonOnline ? "онлайн" : "на связи: " + ago(subject.lastMessageAt)} · ${num(subject.speed)} км/ч` : undefined} onClick={() => setTab("wialon")} />
                <Tile title="Состав (GTK)" color="#8b5cf6" value={overview?.gtk ? `№ ${overview.gtk.train_number ?? overview.gtk.train_gtk_id}` : "Не в составе"} sub={overview?.gtk ? (isLoco ? `${overview.gtk.carriages} вагонов в составе` : `позиция ${overview.gtk.order}, с ${fmtDay(overview.gtk.since)}`) : "нет открытого состава"} onClick={() => setTab("gtk")} />
                <Tile title="Весовая" color="#f59e0b" value={overview?.scales?.last_at ? fmtDay(overview.scales.last_at) : "Нет взвешиваний"} sub={overview?.scales ? `${overview.scales.net_t != null ? num(overview.scales.net_t, 1) + " т · " : ""}${overview.scales.trains_30d} рейсов за 30 дн` : undefined} onClick={() => setTab("scales")} />
                <Tile title="Последний ремонт" color="#10b981" value={m?.last_maint_date ? fmtDay(m.last_maint_date) : m?.last_order_at ? fmtDay(m.last_order_at) : "Нет данных"} sub={`${m?.open_orders ?? 0} открытых нарядов · след. ТО: ${fmtDay(m?.next_maint_date)}`} onClick={() => setTab("repairs")} />
                <Tile title="Пробег НейроТОиР" color="#ef4444" value={`${num(subject.mileage)} км`} sub={subject.unitId ? `Wialon: ${num(subject.wialonMileage)} км` : "трекера нет"} />
              </div>
            </>
          )}

          {tab === "gps" && (
            <>
              <Box title="Позиция: сверка двух трекеров">
                {gps ? (
                  <>
                    <p className="mb-2 flex items-center gap-2 text-base font-bold" style={{ color: vColor }}><span className="h-3 w-3 animate-pulse rounded-full" style={{ background: vColor }} />{verdict ? POSITION_LABEL[verdict] ?? verdict : "—"}</p>
                    {verdict && <p className="mb-3 text-sm text-gray-600 dark:text-gray-300">{POSITION_HINT[verdict]}</p>}
                    <Row k="Источник точки" v={gps.source === "train" ? `по составу № ${gps.train_number ?? ""}` : gps.source} />
                    <Row k="Координаты" v={`${gps.lat.toFixed(5)}, ${gps.lon.toFixed(5)}`} />
                    <Row k="Обновлено" v={`${fmtDate(gps.position_at)} (${ago(gps.position_at)})`} />
                    <Row k="Скорость" v={gps.speed != null ? `${num(gps.speed)} км/ч` : "—"} />
                  </>
                ) : <Note>У этого актива нет координат ни из Wialon, ни из GTK.</Note>}
              </Box>
              {isLoco && (
                <Box title="Треки за сутки">
                  <Async s={gpsDetail}>{(d) => (<><Row k="Точек Wialon" v={d.wialon_track.length} /><Row k="Точек GTK" v={d.gtk_track.length} /><Row k="Пробег за неделю Wialon / GTK" v={`${num(d.row.week_wialon_m / 1000, 1)} / ${num(d.row.week_gtk_m / 1000, 1)} км`} /></>)}</Async>
                </Box>
              )}
              <div className="flex flex-wrap gap-2">
                <Link href="/dashboard/map" className="rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Открыть Карту</Link>
                {isLoco && <Link href={`/dashboard/gps/${subject.id}`} className="rounded-full border border-gray-300 px-4 py-2 text-sm font-semibold hover:bg-white dark:border-gray-600">Страница GPS</Link>}
              </div>
            </>
          )}

          {tab === "wialon" && (
            subject.unitId ? (
              <Box title="Данные Wialon (счётчики трекера)">
                <Row k="Единица Wialon" v={subject.unitId} />
                <Row k="Связь" v={subject.wialonOnline ? "онлайн" : `нет связи · ${ago(subject.lastMessageAt)}`} />
                <Row k="Последнее сообщение" v={fmtDate(subject.lastMessageAt)} />
                <Row k="Пробег Wialon" v={`${num(subject.wialonMileage)} км`} />
                <Row k="Моточасы" v={subject.engineHours ? num(subject.engineHours, 1) : "—"} />
                <Row k="Скорость" v={`${num(subject.speed)} км/ч`} />
                <Row k="Пробег НейроТОиР (для сравнения)" v={`${num(subject.mileage)} км`} />
              </Box>
            ) : <Note>Wialon-трекер к этому активу не привязан.</Note>
          )}

          {tab === "gtk" && (
            <Async s={gtkDetail}>{(d) => (
              <>
                <Box title={d.kind === "locomotive" ? "Локомотив в GTK" : "Вагон в GTK"}>
                  <Row k="GTK ID" v={d.gtk_id} />
                  <Row k="Название" v={d.gtk_object.name ?? "—"} />
                  <Row k="Инв. номер GTK" v={d.gtk_object.inventory_number ?? "—"} />
                  <Row k="Модель" v={d.gtk_object.model_name ?? "—"} />
                  <Row k="Активен в GTK" v={d.gtk_object.is_active ? "да" : "нет"} />
                </Box>
                <Box title="Текущий состав">
                  {d.current_trains.length === 0 ? <p className="text-sm text-gray-500">Сейчас не входит ни в один открытый состав.</p> : d.current_trains.map((t) => (
                    <div key={t.gtk_id} className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 py-2 text-sm last:border-0 dark:border-gray-800">
                      <span className="font-semibold">Состав № {t.number ?? t.gtk_id}</span>
                      <span className="text-gray-500">{t.title ?? ""} · с {fmtDay(t.begin_time)} · {t.carriages.length} ваг.</span>
                    </div>
                  ))}
                </Box>
                <Link href="/dashboard/os/gtk" className="inline-block rounded-full border border-gray-300 px-4 py-2 text-sm font-semibold hover:bg-white dark:border-gray-600">Данные GTK</Link>
              </>
            )}</Async>
          )}

          {tab === "scales" && (isLoco ? (
            <Async s={locoCard}>{(c) => (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <Tile title="Составов (30 дн)" color="#f59e0b" value={String(c.period.trips)} />
                  <Tile title="Тонн (30 дн)" color="#f59e0b" value={num(c.period.tonnes, 0)} />
                  <Tile title="Всего составов" color="#94a3b8" value={String(c.all_time.trips)} />
                </div>
                <Box title="Последние взвешивания">
                  {c.recent.length === 0 ? <p className="text-sm text-gray-500">Нет взвешиваний.</p> : c.recent.slice(0, 8).map((t) => (
                    <Row key={t.id} k={`${fmtDate(t.started_at)} · пост ${t.post_code}`} v={`${t.tonnes != null ? num(t.tonnes, 1) + " т" : "—"} · ${t.cars} ваг.`} />
                  ))}
                </Box>
                <Link href={`/dashboard/scales/loco/${subject.id}`} className="inline-block rounded-full bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600">Полная карточка в Весовой</Link>
              </>
            )}</Async>
          ) : (
            <Async s={wagonCard}>{(c) => (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <Tile title="Рейсов (30 дн)" color="#f59e0b" value={String(c.period.trips)} />
                  <Tile title="Тонн (30 дн)" color="#f59e0b" value={num(c.period.tonnes, 0)} />
                  <Tile title="Всего рейсов" color="#94a3b8" value={String(c.all_time.trips)} />
                </div>
                <Box title="Последние рейсы">
                  {c.recent.length === 0 ? <p className="text-sm text-gray-500">Нет взвешиваний.</p> : c.recent.slice(0, 8).map((t) => (
                    <Row key={`${t.train_id}-${t.position}`} k={`${fmtDate(t.started_at)} · ${t.cargo_name ?? "груз"}`} v={`${t.tonnes != null ? num(t.tonnes, 1) + " т" : "—"} · лок. ${t.loco_number ?? "—"}`} />
                  ))}
                </Box>
                <Link href={`/dashboard/scales/wagon/${subject.id}`} className="inline-block rounded-full bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600">Полная карточка в Весовой</Link>
              </>
            )}</Async>
          ))}

          {tab === "repairs" && (
            <>
              <Box title="Обслуживание">
                <Row k="Последнее ТО / ремонт" v={fmtDay(m?.last_maint_date ?? m?.last_order_at)} />
                <Row k="Следующее ТО (план)" v={fmtDay(m?.next_maint_date)} />
                <Row k="Открытых нарядов" v={m?.open_orders ?? 0} />
              </Box>
              <Box title="Наряды">
                <Async s={orders}>{(o) => o.items.length === 0 ? <p className="text-sm text-gray-500">Нарядов по этому активу ещё нет.</p> : (
                  <>{o.items.map((w) => <Row key={w.id} k={`${w.number} · ${w.description.slice(0, 60)}`} v={`${w.status} · ${fmtDay(w.closed_at ?? w.date_start)}`} />)}</>
                )}</Async>
              </Box>
              <Link href="/dashboard/maintenance" className="inline-block rounded-full border border-gray-300 px-4 py-2 text-sm font-semibold hover:bg-white dark:border-gray-600">ИИ-ТО и ремонты</Link>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
