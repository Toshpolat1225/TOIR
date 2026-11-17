"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import {
  HEALTH_TONE, STATUS_LABEL, STATUS_TONE, candidateText, collectorText, correctionText, dateTimeText, flagLabel, healthText,
  netText, percentText, tonnesText, wagonsText,
  type Correction, type MatchStatus, type Page, type ScaleTrain, type ScalesStatus, type UnmatchedTrain,
} from "@/lib/scales-view"
import { Loader2, RefreshCw } from "@/components/ui/icons"
import Overview from "./_components/Overview"
import WagonLedger from "./_components/WagonLedger"
import { locoHref, trainHref } from "@/lib/scales-insights"

type Tab = "wagons" | "trains" | "unmatched" | "corrections"
const PAGE_SIZE = 50
const TAB_LABEL: Record<Tab, string> = { wagons: "Вагоны", trains: "Составы", unmatched: "Не распознано", corrections: "Корректировки" }
const FLAGS = ["count_mismatch", "default_tare", "overload", "negative_net", "no_wagon_rows", "partial_wagon_rows", "estimated_net"]
const field = "rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
const button = "rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"

export default function ScalesPage() {
  const [tab, setTab] = useState<Tab>("wagons")
  const [status, setStatus] = useState<ScalesStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)

  const [trains, setTrains] = useState<Page<ScaleTrain> | null>(null)
  const [post, setPost] = useState("")
  const [matchStatus, setMatchStatus] = useState("")
  const [flag, setFlag] = useState("")
  const [q, setQ] = useState("")
  const [debouncedQ, setDebouncedQ] = useState("")
  const [offset, setOffset] = useState(0)
  const [unmatched, setUnmatched] = useState<Page<UnmatchedTrain> | null>(null)
  const [corrections, setCorrections] = useState<Correction[] | null>(null)

  const fail = (cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось выполнить запрос")

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQ(q.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [q])
  useEffect(() => setOffset(0), [post, matchStatus, flag, debouncedQ])

  useEffect(() => {
    let cancelled = false
    api.scales.status().then((value) => !cancelled && setStatus(value)).catch(fail)
    return () => { cancelled = true }
  }, [version])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        if (tab === "wagons") {
          // the ledger loads its own data
        } else if (tab === "trains") {
          const page = await api.scales.trains({ post, match_status: matchStatus, flag, q: debouncedQ, limit: PAGE_SIZE, offset })
          if (!cancelled) setTrains(page)
        } else if (tab === "unmatched") {
          const page = await api.scales.unmatched({ limit: PAGE_SIZE, offset: 0 })
          if (!cancelled) setUnmatched(page)
        } else {
          const list = await api.scales.corrections()
          if (!cancelled) setCorrections(list)
        }
        if (!cancelled) setError(null)
      } catch (cause) {
        if (!cancelled) fail(cause)
      }
    }
    void run()
    return () => { cancelled = true }
  }, [tab, post, matchStatus, flag, debouncedQ, offset, version])

  const act = async (message: string, work: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await work()
      setNotice(message)
      setError(null)
      setVersion((v) => v + 1)
    } catch (cause) {
      fail(cause)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto min-h-screen max-w-[1680px] space-y-5 bg-gray-50 p-5 sm:p-7 xl:p-9 dark:bg-gray-950">
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Весовая</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Взвешивание составов на двух путях: сколько тонн перевезено, каким локомотивом и какими вагонами (по данным GTK)
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" className={button} disabled={busy} onClick={() => act("Пересчёт выполнен", () => api.scales.rematch())}>
            Пересчитать всё
          </button>
          <button type="button" className={`${button} inline-flex items-center gap-2`} onClick={() => setVersion((v) => v + 1)}>
            <RefreshCw className="h-4 w-4" /> Обновить
          </button>
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}
      {notice && <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">{notice}</p>}

      <Overview />

      <div className="grid gap-4 md:grid-cols-2" aria-label="Весы">
        {(status?.posts ?? []).map((p) => (
          <section key={p.code} data-testid="scale-post" className={`rounded-xl p-4 ring-1 ${HEALTH_TONE[p.health]}`}>
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-semibold">{p.name}</h2>
              <span className="text-xs">{collectorText(p.collector)}</span>
            </div>
            <p className="mt-1 text-sm font-medium">{healthText(p)}</p>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
              <div><dt className="text-xs opacity-70">Составов за 24 ч</dt><dd className="font-semibold">{p.trains_24h}</dd></div>
              <div><dt className="text-xs opacity-70">Тонн за 24 ч</dt><dd className="font-semibold">{tonnesText(p.tonnes_24h)}</dd></div>
              <div><dt className="text-xs opacity-70">Распознано за 7 сут</dt><dd className="font-semibold">{percentText(p.match_rate_7d)}</dd></div>
              <div><dt className="text-xs opacity-70">Не распознано</dt><dd className="font-semibold">{p.unmatched}</dd></div>
            </dl>
            <p className="mt-2 text-xs opacity-70">Последнее взвешивание: {dateTimeText(p.last_weighing_at)}</p>
          </section>
        ))}
        {status && status.posts.length === 0 && (
          <p className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-600 md:col-span-2 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
            Данных ещё нет: сборщик (scripts/scales_collector) не передавал взвешивания.
          </p>
        )}
      </div>
      {status && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Всего составов: <b>{status.trains_total}</b> · требуют внимания: <b>{status.unmatched_total}</b> · с {dateTimeText(status.first_train_at)} по {dateTimeText(status.last_train_at)}
          {status.before_gtk_history > 0 && (
            <span> · до начала истории GTK ({dateTimeText(status.gtk_history_from)}) вагоны не определяются: <b>{status.before_gtk_history}</b> составов, учтены по локомотиву</span>
          )}
        </p>
      )}

      <div className="flex flex-wrap gap-2" role="tablist">
        {(Object.keys(TAB_LABEL) as Tab[]).map((key) => (
          <button
            key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
            className={`rounded-full px-4 py-1.5 text-sm ring-1 ${tab === key ? "bg-blue-600 text-white ring-blue-600" : "bg-white text-gray-800 ring-gray-200 dark:bg-gray-900 dark:text-gray-100 dark:ring-gray-800"}`}
          >
            {TAB_LABEL[key]}{key === "unmatched" && status ? ` (${status.unmatched_total})` : ""}
          </button>
        ))}
      </div>

      {tab === "wagons" && <WagonLedger posts={(status?.posts ?? []).map((p) => ({ code: p.code, name: p.name }))} />}

      {tab === "trains" && (
        <section className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <select aria-label="Весы" className={field} value={post} onChange={(e) => setPost(e.target.value)}>
              <option value="">Все весы</option>
              {(status?.posts ?? []).map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
            </select>
            <select aria-label="Статус" className={field} value={matchStatus} onChange={(e) => setMatchStatus(e.target.value)}>
              <option value="">Любой статус</option>
              {(Object.keys(STATUS_LABEL) as MatchStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
            <select aria-label="Замечание" className={field} value={flag} onChange={(e) => setFlag(e.target.value)}>
              <option value="">Любое замечание</option>
              {FLAGS.map((f) => <option key={f} value={f}>{flagLabel(f)}</option>)}
            </select>
            <input aria-label="Поиск" type="search" placeholder="№ локомотива" className={field} value={q} onChange={(e) => setQ(e.target.value)} />
            <span className="self-center text-sm text-gray-500">{trains ? `Показано ${trains.total ? offset + 1 : 0}–${Math.min(offset + trains.items.length, trains.total)} из ${trains.total}` : <Loader2 className="h-4 w-4 animate-spin" />}</span>
          </div>
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                <tr>{["Начало", "Весы", "Локомотив", "Вагоны", "Масса груза", "Груз", "Статус", "Замечания"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {(trains?.items ?? []).map((t) => (
                  <tr key={t.id} data-testid="scale-train" className="border-t border-gray-100 align-top dark:border-gray-800">
                    <td className="px-3 py-2 whitespace-nowrap"><Link className="text-blue-600 hover:underline dark:text-blue-400" href={trainHref(t.id)} title="Открыть состав: вагоны, тонны, связи">{dateTimeText(t.started_at)}</Link></td>
                    <td className="px-3 py-2">{t.post_code}</td>
                    <td className="px-3 py-2">{t.loco_asset_id ? <Link className="text-blue-600 hover:underline dark:text-blue-400" href={locoHref(t.loco_asset_id)}>{t.loco_number}</Link> : (t.loco_number ?? "—")}{t.loco_inv_number ? <span className="block text-xs text-gray-500">ОС {t.loco_inv_number}</span> : null}</td>
                    <td className="px-3 py-2 text-xs">{wagonsText(t)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{netText(t)}</td>
                    <td className="px-3 py-2">{t.cargo_name ?? "—"}</td>
                    <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_TONE[t.match_status]}`}>{STATUS_LABEL[t.match_status]}</span></td>
                    <td className="px-3 py-2 text-xs text-gray-600 dark:text-gray-400">{t.flags.map(flagLabel).join("; ") || "—"}</td>
                  </tr>
                ))}
                {trains && trains.items.length === 0 && <tr><td colSpan={8} className="px-3 py-6 text-center text-gray-500">Нет составов по выбранным условиям.</td></tr>}
              </tbody>
            </table>
          </div>
          {trains && trains.total > PAGE_SIZE && (
            <div className="flex gap-2">
              <button className={button} type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Назад</button>
              <button className={button} type="button" disabled={offset + PAGE_SIZE >= trains.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Дальше</button>
            </div>
          )}
        </section>
      )}

      {tab === "unmatched" && (
        <section className="space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Номер состава на весах набирает оператор вручную. Если он не найден в GTK, система предлагает локомотивы, которые в это время работали. Подтвердите верный вариант: исправление применится и к прошлым составам с этим номером.
          </p>
          {(unmatched?.items ?? []).map((t) => (
            <article key={t.id} data-testid="scale-unmatched" className="space-y-2 rounded-xl border border-gray-200 bg-white p-4 text-sm dark:border-gray-800 dark:bg-gray-900">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <b>{dateTimeText(t.started_at)}</b><span>Весы {t.post_code}</span><span>Номер на весах: <b>{t.loco_number ?? "не указан"}</b></span>
                <span>{netText(t)}</span><span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_TONE[t.match_status]}`}>{STATUS_LABEL[t.match_status]}</span>
              </div>
              {t.candidates.length === 0 && <p className="text-gray-500">GTK в это время не показывал работающих локомотивов (история GTK ведётся с 04.11.2026).</p>}
              {t.candidates.map((c) => (
                <div key={c.loco_gtk_id} className="flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50 p-2 dark:bg-emerald-950/40">
                  <span>{candidateText(c)}</span>
                  {c.asset_id && t.loco_number && (
                    <button type="button" className={button} disabled={busy}
                      onClick={() => act(`Номер «${t.loco_number}» привязан к локомотиву`, () => api.scales.createCorrection({ kind: "loco_alias", loco_number: t.loco_number!, asset_id: c.asset_id!, note: "подтверждено оператором" }))}>
                      Это он
                    </button>
                  )}
                  {!c.asset_id && <span className="text-xs text-amber-700 dark:text-amber-300">Сначала свяжите этот локомотив GTK с ОС в карточке</span>}
                </div>
              ))}
              <button type="button" className={button} disabled={busy} onClick={() => act("Состав исключён из учёта", () => api.scales.createCorrection({ kind: "train_exclude", train_id: t.id, note: "исключено оператором" }))}>
                Исключить (проба, дубль, ошибка)
              </button>
            </article>
          ))}
          {unmatched && unmatched.items.length === 0 && <p className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-gray-800 dark:bg-gray-900">Все составы распознаны.</p>}
        </section>
      )}

      {tab === "corrections" && (
        <section className="space-y-2">
          {(corrections ?? []).map((c) => (
            <div key={c.id} data-testid="scale-correction" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-200 bg-white p-3 text-sm dark:border-gray-800 dark:bg-gray-900">
              <span>{correctionText(c)}{c.note ? <span className="text-gray-500"> · {c.note}</span> : null}</span>
              <button type="button" className={button} disabled={busy} onClick={() => act("Корректировка отменена, данные пересчитаны", () => api.scales.endCorrection(c.id))}>Отменить</button>
            </div>
          ))}
          {corrections && corrections.length === 0 && <p className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-gray-800 dark:bg-gray-900">Корректировок нет.</p>}
        </section>
      )}
    </div>
  )
}
