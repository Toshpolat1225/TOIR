"use client"

import { useEffect, useRef, useState, type ReactNode } from "react"
import type { MaintenanceBaselineUpsert, MaintenanceBlockReason, MaintenanceDisruptionCreate, Section } from "@/lib/api"
import {
  BLOCK_REASON_LABEL, equipmentSubtitle, equipmentTitle, formatDate, intervalTitle, parseKmInput, shiftDate,
  validateBaselineDate, type ScheduleItem,
} from "@/lib/maintenance-view"

const FIELD = "mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white"

/** A small modal: Escape cancels (unless busy), Tab stays inside, focus returns to the opener. */
function Shell({ title, subtitle, busy, error, confirmLabel, confirmTone = "blue", canConfirm, onConfirm, onCancel, children }: {
  title: string
  subtitle?: string
  busy: boolean
  error: string | null
  confirmLabel: string
  confirmTone?: "blue" | "red" | "amber"
  canConfirm: boolean
  onConfirm: () => void
  onCancel: () => void
  children: ReactNode
}) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    cancelRef.current?.focus()
    return () => opener?.focus?.()
  }, [])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) { event.stopPropagation(); onCancel(); return }
      if (event.key !== "Tab" || !dialogRef.current) return
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])",
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener("keydown", onKey, true)
    return () => window.removeEventListener("keydown", onKey, true)
  }, [busy, onCancel])
  const tone = confirmTone === "red" ? "bg-red-600 hover:bg-red-700" : confirmTone === "amber" ? "bg-amber-600 hover:bg-amber-700" : "bg-blue-600 hover:bg-blue-700"
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" onClick={() => { if (!busy) onCancel() }} />
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="plan-dialog-title"
        className="relative flex max-h-[92vh] w-full max-w-md flex-col overflow-y-auto rounded-2xl bg-white shadow-2xl dark:bg-gray-900">
        <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
          <h2 id="plan-dialog-title" className="text-lg font-bold text-gray-900 dark:text-white">{title}</h2>
          {subtitle && <p className="mt-1 text-xs text-gray-500">{subtitle}</p>}
        </div>
        <div className="space-y-4 px-6 py-5">
          {children}
          {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-gray-200 px-6 py-4 dark:border-gray-800">
          <button ref={cancelRef} type="button" onClick={onCancel} disabled={busy}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
            {"Отмена"}
          </button>
          <button type="button" onClick={onConfirm} disabled={!canConfirm || busy}
            className={`rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 ${tone}`}>
            {busy ? "Сохранение…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function Who({ item }: { item: ScheduleItem }) {
  return (
    <p className="text-sm font-semibold text-gray-900 dark:text-white">
      {equipmentTitle(item)} <span className="font-normal text-gray-500">{`· ${equipmentSubtitle(item)} · ${intervalTitle(item.type)}`}</span>
    </p>
  )
}

const PLAN_BLOCK_REASONS = (Object.keys(BLOCK_REASON_LABEL) as MaintenanceBlockReason[]).filter((code) => code !== "sensor_failure")

export function BlockDialog({ item, todayIso, busy, error, onConfirm, onCancel }: {
  item: ScheduleItem
  todayIso: string
  busy: boolean
  error: string | null
  onConfirm: (data: { reason_code: MaintenanceBlockReason; until: string | null; note: string | null }) => void
  onCancel: () => void
}) {
  const [reason, setReason] = useState<MaintenanceBlockReason>("parts")
  const [until, setUntil] = useState("")
  const [note, setNote] = useState("")
  const untilError = until && until < todayIso ? "Срок не может быть в прошлом" : null
  return (
    <Shell title={"Заблокировать план?"} subtitle={"Работа не отменяется: обязательство остаётся, а наработка и приоритет продолжают расти."}
      busy={busy} error={error ?? untilError} confirmLabel={"Заблокировать"} confirmTone="amber" canConfirm={!untilError}
      onConfirm={() => onConfirm({ reason_code: reason, until: until || null, note: note.trim() || null })} onCancel={onCancel}>
      <Who item={item} />
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Причина"}
        <select value={reason} onChange={(event) => setReason(event.target.value as MaintenanceBlockReason)} disabled={busy} className={FIELD}>
          {PLAN_BLOCK_REASONS.map((code) => <option key={code} value={code}>{BLOCK_REASON_LABEL[code]}</option>)}
        </select>
      </label>
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Ожидаемая дата снятия (по желанию)"}
        <input type="date" min={todayIso} value={until} onChange={(event) => setUntil(event.target.value)} disabled={busy} className={FIELD} />
      </label>
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Комментарий (по желанию)"}
        <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={2} disabled={busy} className={FIELD} />
      </label>
    </Shell>
  )
}

export function WaiveDialog({ item, busy, error, onConfirm, onCancel }: {
  item: ScheduleItem
  busy: boolean
  error: string | null
  onConfirm: (reason: string) => void
  onCancel: () => void
}) {
  const [reason, setReason] = useState("")
  const trimmed = reason.trim()
  return (
    <Shell title={"Пропустить этот цикл ТО?"} subtitle={"Решение администратора. Цикл не нужен (например, заменён старшим ТО); следующий отсчёт пойдёт от порога этого цикла."}
      busy={busy} error={error} confirmLabel={"Пропустить цикл"} confirmTone="red" canConfirm={trimmed.length >= 3}
      onConfirm={() => onConfirm(trimmed)} onCancel={onCancel}>
      <Who item={item} />
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Основание (обязательно)"}
        <textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} rows={3} disabled={busy}
          placeholder={"Например: выполнено ТО-3, цикл ТО-2 перекрыт"} className={FIELD} />
      </label>
    </Shell>
  )
}

export function BaselineDialog({ item, todayIso, busy, error, onConfirm, onCancel }: {
  item: ScheduleItem
  todayIso: string
  busy: boolean
  error: string | null
  onConfirm: (payload: Omit<MaintenanceBaselineUpsert, "asset_id" | "interval_id">) => void
  onCancel: () => void
}) {
  const [doneAt, setDoneAt] = useState(shiftDate(todayIso, -30))
  const [mode, setMode] = useState<"odometer" | "toir">("odometer")
  const [km, setKm] = useState("")
  const [hours, setHours] = useState("")
  const [note, setNote] = useState("")
  const kmValue = parseKmInput(km)
  const hoursValue = parseKmInput(hours)
  const dateError = validateBaselineDate(doneAt, todayIso)
  const kmError = km.trim() !== "" && kmValue === null ? "Введите число" : mode === "odometer" && kmValue !== null && kmValue < 0 ? "Одометр не бывает отрицательным" : null
  const needsKm = item.interval_id !== null && toNumOrNull(item.intervalKm) !== null
  const canConfirm = !dateError && !kmError && (!needsKm || kmValue !== null)
  return (
    <Shell title={"Когда было последнее ТО?"} subtitle={"Следующий срок считается от этой точки, а не от сетки порогов. После сохранения прогноз станет надёжным."}
      busy={busy} error={error} confirmLabel={"Сохранить"} canConfirm={canConfirm}
      onConfirm={() => onConfirm({
        done_at: doneAt,
        ...(kmValue !== null ? (mode === "odometer" ? { odometer_km: kmValue } : { km: kmValue }) : {}),
        hours: hoursValue,
        note: note.trim() || null,
      })} onCancel={onCancel}>
      <Who item={item} />
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Дата последнего ТО"}
        <input type="date" max={todayIso} value={doneAt} onChange={(event) => setDoneAt(event.target.value)} disabled={busy} className={FIELD} />
        {dateError && <span className="mt-1 block text-red-600">{dateError}</span>}
      </label>
      <fieldset className="space-y-2">
        <legend className="text-xs font-semibold text-gray-600 dark:text-gray-300">{"Пробег на тот момент"}</legend>
        <label className="flex items-start gap-2 text-xs text-gray-700 dark:text-gray-300">
          <input type="radio" name="baseline-mode" checked={mode === "odometer"} onChange={() => setMode("odometer")} className="mt-0.5" />
          <span>{"Показание одометра (как в паспорте или Wialon). Система сама пересчитает его в шкалу ТОИР."}</span>
        </label>
        <label className="flex items-start gap-2 text-xs text-gray-700 dark:text-gray-300">
          <input type="radio" name="baseline-mode" checked={mode === "toir"} onChange={() => setMode("toir")} className="mt-0.5" />
          <span>{"Пробег в шкале ТОИР (км с момента подключения слежения; до подключения — отрицательный)."}</span>
        </label>
        <input inputMode="decimal" value={km} onChange={(event) => setKm(event.target.value)} disabled={busy}
          placeholder={mode === "odometer" ? "Например: 121 500" : "Например: 1 500"} aria-label={"Пробег, км"} className={FIELD} />
        {kmError && <span className="block text-xs text-red-600">{kmError}</span>}
      </fieldset>
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Моточасы на тот момент (по желанию, для дизелей)"}
        <input inputMode="decimal" value={hours} onChange={(event) => setHours(event.target.value)} disabled={busy} className={FIELD} />
      </label>
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Источник / комментарий (по желанию)"}
        <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} disabled={busy}
          placeholder={"Например: паспорт локомотива, запись от " + formatDate(doneAt)} className={FIELD} />
      </label>
    </Shell>
  )
}

function toNumOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function DisruptionDialog({ todayIso, sections, assets, busy, error, onConfirm, onCancel }: {
  todayIso: string
  sections: Section[]
  assets: { id: string; label: string }[]
  busy: boolean
  error: string | null
  onConfirm: (data: MaintenanceDisruptionCreate) => void
  onCancel: () => void
}) {
  const [kind, setKind] = useState<MaintenanceBlockReason>("no_bay")
  const [scope, setScope] = useState<"asset" | "section" | "all">("section")
  const [assetId, setAssetId] = useState("")
  const [sectionId, setSectionId] = useState("")
  const [startsOn, setStartsOn] = useState(todayIso)
  const [endsOn, setEndsOn] = useState("")
  const [note, setNote] = useState("")
  const targetOk = scope === "all" || (scope === "asset" ? assetId !== "" : sectionId !== "")
  const datesOk = !endsOn || endsOn >= startsOn
  const blocks = kind !== "sensor_failure"
  return (
    <Shell title={"Зафиксировать сбой или ограничение"}
      subtitle={blocks ? "Все запланированные ТО в этот период будут заблокированы (не отменены) и вернутся в план, когда сбой закроют." : "Неисправный датчик не останавливает работы: прогноз по этой технике просто помечается как устаревший."}
      busy={busy} error={error ?? (datesOk ? null : "Окончание раньше начала")} confirmLabel={"Зафиксировать"} confirmTone="amber"
      canConfirm={targetOk && datesOk}
      onConfirm={() => onConfirm({
        kind, scope,
        asset_id: scope === "asset" ? assetId : null,
        section_id: scope === "section" ? sectionId : null,
        starts_on: startsOn || null, ends_on: endsOn || null, note: note.trim() || null,
      })} onCancel={onCancel}>
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Что случилось"}
        <select value={kind} onChange={(event) => setKind(event.target.value as MaintenanceBlockReason)} disabled={busy} className={FIELD}>
          {(Object.keys(BLOCK_REASON_LABEL) as MaintenanceBlockReason[]).map((code) => <option key={code} value={code}>{BLOCK_REASON_LABEL[code]}</option>)}
        </select>
      </label>
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"На что влияет"}
        <select value={scope} onChange={(event) => setScope(event.target.value as "asset" | "section" | "all")} disabled={busy} className={FIELD}>
          <option value="section">{"Участок / депо"}</option>
          <option value="asset">{"Одна единица техники"}</option>
          <option value="all">{"Всё предприятие"}</option>
        </select>
      </label>
      {scope === "section" && (
        <select value={sectionId} onChange={(event) => setSectionId(event.target.value)} disabled={busy} aria-label={"Участок"} className={FIELD}>
          <option value="">{"Выберите участок…"}</option>
          {sections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
        </select>
      )}
      {scope === "asset" && (
        <select value={assetId} onChange={(event) => setAssetId(event.target.value)} disabled={busy} aria-label={"Техника"} className={FIELD}>
          <option value="">{"Выберите технику…"}</option>
          {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.label}</option>)}
        </select>
      )}
      <div className="grid grid-cols-2 gap-3">
        <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
          {"С"}
          <input type="date" value={startsOn} onChange={(event) => setStartsOn(event.target.value)} disabled={busy} className={FIELD} />
        </label>
        <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
          {"По (пусто — пока не закроют)"}
          <input type="date" min={startsOn} value={endsOn} onChange={(event) => setEndsOn(event.target.value)} disabled={busy} className={FIELD} />
        </label>
      </div>
      <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300">
        {"Комментарий (по желанию)"}
        <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={2} disabled={busy} className={FIELD} />
      </label>
    </Shell>
  )
}
