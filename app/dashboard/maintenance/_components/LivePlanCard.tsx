"use client"

import {
  BASELINE_SOURCE_LABEL, BLOCK_REASON_LABEL, CONFIDENCE_LABEL, PRIORITY_CLS, STATE_LABEL, canBlock, canSetBaseline,
  canUnblock, canWaive, diffDaysIso, fmtNum, formatDate, limitingLabel, limitingUnit, markerTimeline, paceText,
  priorityTone, toNum, type ScheduleItem,
} from "@/lib/maintenance-view"
import type { MaintenanceDecision } from "@/lib/api"

const MARKER_STYLE: Record<string, { dot: string; text: string }> = {
  window: { dot: "#3b82f6", text: "text-blue-600 dark:text-blue-300" },
  early: { dot: "#ef4444", text: "text-red-600 dark:text-red-300" },
  typical: { dot: "#f59e0b", text: "text-amber-600 dark:text-amber-300" },
  late: { dot: "#10b981", text: "text-emerald-600 dark:text-emerald-300" },
}

const MARKER_HINT: Record<string, string> = {
  window: "С этой даты планирование открыто: пора резервировать место и запчасти",
  early: "Осторожная дата: так будет, если техника поедет быстрее обычного. К этому дню ТО должно быть сделано",
  typical: "Обычная дата при типичном темпе работы",
  late: "Если техника будет ездить медленнее обычного",
}

const DECISION_LABEL: Record<string, string> = {
  reschedule: "Перенос срока",
  block: "Блокировка",
  unblock: "Снятие блокировки",
  waive: "Пропуск цикла",
  cover: "Перекрыто старшим ТО",
  release: "Возврат в план",
}

function daysFromToday(iso: string, todayIso: string): string {
  const days = diffDaysIso(todayIso, iso)
  if (days === 0) return "сегодня"
  return days > 0 ? `через ${days} дн.` : `${Math.abs(days)} дн. назад`
}

/** The living-plan facts of one obligation: where the limit is, how sure the forecast is, why it is urgent. */
export function LivePlanCard({
  item, todayIso, canUpdate, isAdmin, busy, decisions, decisionsError, onBlock, onUnblock, onWaive, onBaseline,
}: {
  item: ScheduleItem
  todayIso: string
  canUpdate: boolean
  isAdmin: boolean
  busy: boolean
  decisions: MaintenanceDecision[] | null
  decisionsError: boolean
  onBlock: () => void
  onUnblock: () => void
  onWaive: () => void
  onBaseline: () => void
}) {
  if (item.entity_type === "work_order") return null
  const timeline = markerTimeline(item, todayIso)
  const confidence = item.confidence ? CONFIDENCE_LABEL[item.confidence] : null
  const used = toNum(item.limitingUsed)
  const limit = toNum(item.limitingLimit)
  const tolerance = toNum(item.tolerance)
  const unit = limitingUnit(item)
  const usedPct = used !== null && limit !== null && limit > 0 ? Math.max(0, (used / limit) * 100) : null
  const pace = paceText(item)
  const provisional = item.baselineSource === "provisional"
  const hasModel = !!item.state || !!item.confidence || timeline !== null
  const showBaseline = canSetBaseline(item, canUpdate)
  const rangeLeft = timeline ? Math.min(...timeline.points.filter((p) => p.key !== "window").map((p) => p.pct)) : 0
  const rangeRight = timeline ? Math.max(...timeline.points.filter((p) => p.key !== "window").map((p) => p.pct)) : 0

  return (
    <section aria-labelledby="live-plan-title" className="space-y-4 rounded-xl border border-blue-100 bg-blue-50/40 p-4 dark:border-blue-900/60 dark:bg-blue-950/10">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="live-plan-title" className="text-xs font-bold uppercase tracking-wider text-blue-700 dark:text-blue-300">{"Живой план"}</h3>
        {item.state && (
          <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-gray-700 ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:ring-gray-700">
            {STATE_LABEL[item.state] ?? item.state}
          </span>
        )}
        {item.priority !== null && item.priority !== undefined && (
          <span title={"Приоритет 0–100: чем выше, тем раньше нужно браться"}
            className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-bold ${PRIORITY_CLS[priorityTone(item.priority)]}`}>
            {`Приоритет ${item.priority}`}
          </span>
        )}
      </div>

      {!hasModel && (
        <p className="text-xs text-gray-500">{"Для этой записи нет данных живого плана (сервер ещё не рассчитал даты)."}</p>
      )}

      {confidence && (
        <p title={confidence.hint} className={`inline-block rounded-lg px-2.5 py-1 text-xs font-semibold ${confidence.cls}`}>
          {confidence.label}
        </p>
      )}

      {usedPct !== null && limit !== null && used !== null && (
        <div>
          <div className="mb-1 flex flex-wrap justify-between gap-x-3 text-xs text-gray-600 dark:text-gray-300">
            <span>{`Наработка ${limitingLabel(item)} с последнего ТО`}</span>
            <span className="font-semibold">{`${fmtNum(used)} из ${fmtNum(limit)} ${unit}`}</span>
          </div>
          <div className="relative h-2.5 overflow-hidden rounded-full bg-white dark:bg-gray-800">
            <div className={`h-full rounded-full ${usedPct >= 100 ? "bg-red-500" : usedPct >= 90 ? "bg-amber-500" : "bg-blue-500"}`}
              style={{ width: `${Math.min(100, usedPct)}%` }} />
          </div>
          {tolerance !== null && tolerance > 0 && (
            <p className="mt-1 text-[11px] text-gray-500">{`Допуск сверх лимита: +${fmtNum(tolerance)} ${unit}. За ним перенос только с согласованием администратора.`}</p>
          )}
        </div>
      )}

      {timeline && (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500">{"Когда это произойдёт"}</p>
          <div className="relative mx-2 h-6" role="img"
            aria-label={`Окно плана и даты: ${timeline.points.map((p) => `${p.label} ${formatDate(p.iso)}`).join(", ")}`}>
            <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-gray-200 dark:bg-gray-700" />
            {timeline.points.some((p) => p.key !== "window") && (
              <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-amber-300/70"
                style={{ left: `${rangeLeft}%`, width: `${Math.max(1, rangeRight - rangeLeft)}%` }} />
            )}
            <div className="absolute top-0 h-6 w-px bg-gray-500" style={{ left: `${timeline.todayPct}%` }} title={"Сегодня"} />
            {timeline.points.map((point) => (
              <span key={point.key} title={`${point.label}: ${formatDate(point.iso)}${point.clamped ? " (дальше края шкалы)" : ""}`}
                className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow dark:border-gray-900"
                style={{ left: `${point.pct}%`, backgroundColor: MARKER_STYLE[point.key].dot }} />
            ))}
          </div>
          <ul className="mt-3 space-y-1">
            {timeline.points.map((point) => (
              <li key={point.key} title={MARKER_HINT[point.key]} className="flex items-center gap-2 text-xs">
                <span aria-hidden="true" className="h-2.5 w-2.5 flex-shrink-0 rounded-full" style={{ backgroundColor: MARKER_STYLE[point.key].dot }} />
                <span className={`font-semibold ${MARKER_STYLE[point.key].text}`}>{point.label}</span>
                <span className="ml-auto font-semibold text-gray-800 dark:text-gray-100">{formatDate(point.iso)}</span>
                <span className="w-24 text-right text-gray-500">{point.clamped ? "очень нескоро" : daysFromToday(point.iso, todayIso)}</span>
              </li>
            ))}
          </ul>
          {item.opportunistic && (
            <p className="mt-2 rounded-lg bg-emerald-50 px-2.5 py-1.5 text-xs text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
              {"Техника уже стоит в ремонте: удобно выполнить это ТО заодно."}
            </p>
          )}
          {item.mergedInto && (
            <p className="mt-2 rounded-lg bg-blue-50 px-2.5 py-1.5 text-xs text-blue-800 dark:bg-blue-950/30 dark:text-blue-200">
              {"Срок близок к более крупному ТО: оба вида работ планируются одним заходом."}
            </p>
          )}
        </div>
      )}

      {(pace || item.baselineSource) && (
        <dl className="grid grid-cols-1 gap-1 text-xs text-gray-600 dark:text-gray-300">
          {pace && (
            <div className="flex justify-between gap-3"><dt className="text-gray-500">{"Темп работы"}</dt><dd className="text-right font-medium">{pace}</dd></div>
          )}
          {item.baselineSource && (
            <div className="flex justify-between gap-3"><dt className="text-gray-500">{"Точка отсчёта"}</dt><dd className="text-right font-medium">{BASELINE_SOURCE_LABEL[item.baselineSource] ?? item.baselineSource}</dd></div>
          )}
          {(item.deferralCount ?? 0) > 0 && (
            <div className="flex justify-between gap-3"><dt className="text-gray-500">{"Переносов срока"}</dt><dd className="text-right font-medium">{item.deferralCount}</dd></div>
          )}
        </dl>
      )}

      {item.priorityWhy && item.priorityWhy.length > 0 && (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-500">{"Почему такой приоритет"}</p>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-gray-700 dark:text-gray-300">
            {item.priorityWhy.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </div>
      )}

      {item.status === "blocked" && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          <p className="font-bold">{`Заблокировано: ${BLOCK_REASON_LABEL[item.blockedReason ?? "other"] ?? "причина не указана"}`}</p>
          {item.blockedUntil && <p>{`До ${formatDate(item.blockedUntil)}`}</p>}
          {item.blockedNote && <p>{item.blockedNote}</p>}
          <p className="mt-1 opacity-80">{"Обязательство не потеряно: наработка продолжает расти, приоритет тоже."}</p>
        </div>
      )}

      {provisional && showBaseline && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          {"Дата и пробег последнего ТО не внесены, поэтому срок — приблизительный. Внесите их, и прогноз станет надёжным."}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {showBaseline && (
          <button type="button" onClick={onBaseline} disabled={busy}
            className="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-800 dark:bg-gray-800 dark:text-blue-300">
            {provisional ? "Внести последнее ТО…" : "Изменить последнее ТО…"}
          </button>
        )}
        {canBlock(item, canUpdate) && (
          <button type="button" onClick={onBlock} disabled={busy}
            className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-50 disabled:opacity-50 dark:border-amber-800 dark:bg-gray-800 dark:text-amber-300">
            {"Заблокировать…"}
          </button>
        )}
        {canUnblock(item, canUpdate) && (
          <button type="button" onClick={onUnblock} disabled={busy}
            className="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-600 disabled:opacity-50">
            {"Снять блокировку"}
          </button>
        )}
        {canWaive(item, isAdmin) && (
          <button type="button" onClick={onWaive} disabled={busy}
            className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:bg-gray-800 dark:text-red-300">
            {"Пропустить цикл…"}
          </button>
        )}
      </div>

      {item.plan_id && (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-500">{"Журнал решений"}</p>
          {decisions === null && !decisionsError && <p className="text-xs text-gray-400">{"Загрузка…"}</p>}
          {decisionsError && <p className="text-xs text-amber-600 dark:text-amber-400">{"Журнал недоступен"}</p>}
          {decisions !== null && decisions.length === 0 && <p className="text-xs text-gray-400">{"Решений по этому плану пока нет"}</p>}
          {decisions !== null && decisions.length > 0 && (
            <ul className="space-y-1.5">
              {decisions.slice(0, 8).map((decision) => (
                <li key={decision.id} className="rounded-lg bg-white px-2.5 py-1.5 text-xs ring-1 ring-gray-100 dark:bg-gray-800 dark:ring-gray-700">
                  <div className="flex justify-between gap-2">
                    <span className="font-semibold text-gray-800 dark:text-gray-100">{DECISION_LABEL[decision.kind] ?? decision.kind}</span>
                    <span className="text-gray-400">{new Date(decision.created_at).toLocaleDateString("ru-RU")}</span>
                  </div>
                  {(decision.from_date || decision.to_date) && (
                    <p className="text-gray-500">
                      {decision.from_date ? formatDate(decision.from_date) : "—"} {"→"} {decision.to_date ? formatDate(decision.to_date) : "—"}
                    </p>
                  )}
                  {decision.reason_code && <p className="text-gray-500">{BLOCK_REASON_LABEL[decision.reason_code] ?? decision.reason_code}</p>}
                  {decision.note && <p className="text-gray-600 dark:text-gray-300">{decision.note}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
