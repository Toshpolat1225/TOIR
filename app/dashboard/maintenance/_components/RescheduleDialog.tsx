"use client"

import { useEffect, useRef, useState } from "react"
import {
  equipmentSubtitle, equipmentTitle, fmtNum, formatDate, intervalTitle, rescheduleImpact,
  validateRescheduleDate, type ScheduleItem,
} from "@/lib/maintenance-view"
import { EquipmentAvatar, IntervalChip } from "./EquipmentBadge"

const MIN_REASON_WHEN_RISKY = 5

function DateBox({ label, value, strong = false, tone }: { label: string; value: string; strong?: boolean; tone?: string }) {
  return (
    <div className={`rounded-xl border px-3 py-2 text-center ${tone ?? "border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/40"}`}>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`mt-0.5 ${strong ? "text-lg font-black" : "text-sm font-semibold"} text-gray-900 dark:text-white`}>{formatDate(value)}</p>
    </div>
  )
}

/**
 * Asks for an explicit confirmation before a maintenance date is moved by hand. The planner sees what the
 * system recommended, what changes, and what the move means in kilometres; a move that would run the unit
 * past its threshold needs a reason and an explicit acknowledgement.
 */
export function RescheduleDialog({ item, toIso, todayIso, dailyKm, color, busy, error, onConfirm, onCancel }: {
  item: ScheduleItem
  toIso: string
  todayIso: string
  dailyKm: number | null
  color: string
  busy: boolean
  error: string | null
  onConfirm: (reason: string) => void
  onCancel: () => void
}) {
  const impact = rescheduleImpact(item, toIso, todayIso, dailyKm)
  const dateError = validateRescheduleDate(toIso, todayIso)
  const risky = impact.level === "danger"
  const [reason, setReason] = useState("")
  const [acknowledged, setAcknowledged] = useState(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)

  // Focus lands on the SAFE button; focus returns to whatever opened the dialog.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    cancelRef.current?.focus()
    return () => opener?.focus?.()
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) { onCancel(); return }
      if (event.key !== "Tab" || !dialogRef.current) return
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), a[href]',
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [busy, onCancel])

  const trimmed = reason.trim()
  const reasonOk = !risky || trimmed.length >= MIN_REASON_WHEN_RISKY
  const canConfirm = !busy && !dateError && impact.shiftDays !== 0 && reasonOk && (!risky || acknowledged)
  const shiftLabel = `${impact.shiftDays > 0 ? "+" : "−"}${Math.abs(impact.shiftDays)} дн.`
  const vsLabel =
    impact.vsRecommendedDays === 0
      ? "совпадает с рекомендацией"
      : impact.vsRecommendedDays > 0
        ? `на ${impact.vsRecommendedDays} дн. позже рекомендации`
        : `на ${Math.abs(impact.vsRecommendedDays)} дн. раньше рекомендации`

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" onClick={() => { if (!busy) onCancel() }} />
      <div ref={dialogRef} role="alertdialog" aria-modal="true" aria-labelledby="reschedule-title" aria-describedby="reschedule-desc"
        className="relative flex max-h-[92vh] w-full max-w-lg flex-col overflow-y-auto rounded-2xl bg-white shadow-2xl dark:bg-gray-900">
        <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
          <h2 id="reschedule-title" className="text-lg font-bold text-gray-900 dark:text-white">{"✋ Перенести срок ТО?"}</h2>
          <p id="reschedule-desc" className="mt-1 text-xs text-gray-500">
            {"Переносите дату, только если в рекомендованный день физически нельзя поставить технику на ТО или осмотр."}
          </p>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div className="flex items-center gap-3">
            <EquipmentAvatar item={item} size="md" />
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-gray-900 dark:text-white">{equipmentTitle(item)}</p>
              <p className="truncate text-xs text-gray-500">{equipmentSubtitle(item)}</p>
            </div>
            <span className="ml-auto" title={intervalTitle(item.type)}><IntervalChip type={item.type} color={color} large /></span>
          </div>

          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <DateBox label="Сейчас в плане" value={impact.fromIso} />
            <span aria-hidden="true" className="text-xl text-gray-400">→</span>
            <DateBox label="Новая дата" value={impact.toIso} strong
              tone={risky ? "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/30" : "border-blue-300 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30"} />
          </div>
          <p className="text-center text-xs text-gray-500">
            {`Сдвиг ${shiftLabel} · ${vsLabel}`}
            {impact.recommendedIso !== impact.fromIso && ` (рекомендация системы: ${formatDate(impact.recommendedIso)})`}
          </p>

          {impact.level === "danger" && (
            <div role="alert" className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
              <p className="font-bold">{"Порог ТО будет превышен"}</p>
              <p className="mt-1">
                {`К ${formatDate(impact.toIso)} при пробеге этой техники ${fmtNum(impact.paceKm ?? 0)} км/сут пробег превысит порог (${intervalTitle(item.type)}) примерно на ${fmtNum(impact.overrunKm)} км. Эксплуатация сверх порога повышает риск отказа.`}
              </p>
            </div>
          )}
          {impact.needsApproval && (
            <div role="note" className="rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-900 dark:border-violet-900 dark:bg-violet-950/30 dark:text-violet-200">
              <p className="font-bold">{"Потребуется согласование администратора"}</p>
              <p className="mt-1">{"Новая дата выходит за допуск сверх лимита или это уже третий перенос подряд. Оператору сервер откажет; администратор может подтвердить перенос."}</p>
            </div>
          )}
          {impact.level === "info" && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200">
              {`Работы пройдут раньше рекомендации.${impact.remainingAtNewKm !== null ? ` К этой дате до порога останется ≈ ${fmtNum(impact.remainingAtNewKm)} км запаса: он не будет использован.` : ""}`}
            </div>
          )}
          {impact.level === "ok" && impact.remainingAtNewKm !== null && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">
              {`Порог не будет превышен: к этой дате до него останется ≈ ${fmtNum(Math.max(0, impact.remainingAtNewKm))} км.`}
            </div>
          )}
          {impact.remainingAtNewKm === null && (
            <p className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-300">
              {"Прогноз по километрам недоступен (интервал по сроку или не задан средний суточный пробег): проверьте последствия вручную."}
            </p>
          )}

          {item.entity_type === "forecast" && (
            <p className="text-xs text-gray-500">{"Для этой записи будет создан план ТО на выбранную дату, дальше система её не изменит."}</p>
          )}

          <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
            {risky ? `Причина переноса (обязательно, не короче ${MIN_REASON_WHEN_RISKY} символов)` : "Причина переноса (по желанию)"}
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} rows={2} disabled={busy}
              placeholder={"Например: нет свободной позиции в депо / техника на маршруте"}
              className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white" />
          </label>

          {risky && (
            <label className="flex items-start gap-2 text-sm text-red-800 dark:text-red-200">
              <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} disabled={busy} className="mt-1" />
              {"Я понимаю риск превышения порога и подтверждаю перенос"}
            </label>
          )}

          {(error || dateError) && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              {error ?? dateError}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-gray-200 px-6 py-4 dark:border-gray-800">
          <button ref={cancelRef} type="button" onClick={onCancel} disabled={busy}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
            {"Отмена, оставить как есть"}
          </button>
          <button type="button" onClick={() => onConfirm(trimmed)} disabled={!canConfirm}
            className={`rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 ${risky ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"}`}>
            {busy ? "Сохранение…" : `Подтвердить перенос на ${formatDate(impact.toIso)}`}
          </button>
        </div>
      </div>
    </div>
  )
}
