"use client"

// Result cards of the command centre: one renderer for every card kind of the backend contract (asset, wagon, train, list, metric, text, table, confirm, help, error).
import Link from "next/link"
import type { AssistantCard, AssistantCardItem, AssistantEntityRef, AssistantTone } from "@/lib/assistant"

const TONE_TEXT: Record<AssistantTone, string> = {
  ok: "text-emerald-700 dark:text-emerald-400",
  warn: "text-amber-700 dark:text-amber-400",
  bad: "text-rose-700 dark:text-rose-400",
  info: "text-sky-700 dark:text-sky-400",
  muted: "text-gray-500 dark:text-gray-400",
}
const TONE_DOT: Record<AssistantTone, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-rose-500",
  info: "bg-sky-500",
  muted: "bg-gray-400",
}
const KIND_FRAME: Record<string, string> = {
  error: "border-rose-200 bg-rose-50/60 dark:border-rose-900 dark:bg-rose-950/30",
  confirm: "border-amber-300 bg-amber-50/70 dark:border-amber-800 dark:bg-amber-950/30",
  help: "border-indigo-200 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/30",
}
const KIND_LABEL: Record<string, string> = {
  asset: "Техника",
  wagon: "Вагон",
  train: "Состав",
  metric: "Показатель",
  table: "Таблица",
  confirm: "Подтверждение",
  help: "Команды",
}

export function toneText(tone: AssistantTone | null | undefined): string {
  return tone ? TONE_TEXT[tone] : "text-gray-900 dark:text-gray-100"
}

function Item({ item, onEntity, onNavigate }: { item: AssistantCardItem; onEntity: (entity: AssistantEntityRef) => void; onNavigate: () => void }) {
  const body = (
    <>
      {item.tone ? <span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${TONE_DOT[item.tone]}`} /> : null}
      <span className="min-w-0 flex-1">
        <span className={`block break-words text-sm font-medium ${item.href ? "text-blue-700 dark:text-blue-400" : "text-gray-900 dark:text-gray-100"}`}>{item.label}</span>
        {item.sub ? <span className="block break-words text-xs text-gray-500 dark:text-gray-400">{item.sub}</span> : null}
      </span>
      {item.value ? <span className={`shrink-0 text-right text-sm font-semibold tabular-nums ${toneText(item.tone)}`}>{item.value}</span> : null}
    </>
  )
  const frame = "flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left"
  if (item.href) {
    return (
      <Link
        href={item.href}
        onClick={() => {
          if (item.entity) onEntity(item.entity)
          onNavigate()
        }}
        className={`${frame} hover:bg-white/70 dark:hover:bg-gray-800`}
      >
        {body}
      </Link>
    )
  }
  if (item.entity) {
    const entity = item.entity
    return (
      <button type="button" onClick={() => onEntity(entity)} title="Сделать контекстом разговора («это»)" className={`${frame} hover:bg-white/70 dark:hover:bg-gray-800`}>
        {body}
      </button>
    )
  }
  return <div className={frame}>{body}</div>
}

export function AssistantCardView({ card, onEntity, onNavigate }: { card: AssistantCard; onEntity: (entity: AssistantEntityRef) => void; onNavigate: () => void }) {
  const frame = KIND_FRAME[card.kind] ?? "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
  const accent = card.tone ? TONE_TEXT[card.tone] : "text-gray-500 dark:text-gray-400"
  return (
    <article data-testid="assistant-card" data-kind={card.kind} className={`min-w-0 max-w-full rounded-2xl border p-3 shadow-sm ${frame}`}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {KIND_LABEL[card.kind] ? <p className={`text-[10px] font-semibold uppercase tracking-wide ${accent}`}>{KIND_LABEL[card.kind]}</p> : null}
          <h3 className="break-words text-sm font-semibold text-gray-900 dark:text-white">{card.title}</h3>
          {card.subtitle ? <p className="break-words text-xs text-gray-500 dark:text-gray-400">{card.subtitle}</p> : null}
        </div>
        {card.badge ? (
          <span className={`shrink-0 rounded-full bg-white px-2 py-0.5 text-xs font-medium ring-1 ring-gray-200 dark:bg-gray-800 dark:ring-gray-700 ${card.tone ? TONE_TEXT[card.tone] : "text-gray-700 dark:text-gray-200"}`}>{card.badge}</span>
        ) : null}
      </header>

      {card.rows.length > 0 ? (
        <dl className="mt-2 divide-y divide-gray-100 text-sm dark:divide-gray-800">
          {card.rows.map((row, i) => (
            <div key={`${row.label}-${i}`} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-1">
              <dt className="text-gray-500 dark:text-gray-400">{row.label}</dt>
              <dd className={`min-w-0 break-words text-right font-medium ${toneText(row.tone)}`}>{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {card.items.length > 0 ? (
        <ul className="mt-2 space-y-0.5">
          {card.items.map((item, i) => (
            <li key={`${item.label}-${i}`} className="min-w-0">
              <Item item={item} onEntity={onEntity} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      ) : null}

      {card.columns.length > 0 && card.table.length > 0 ? (
        <div className="mt-2 max-w-full overflow-x-auto rounded-lg ring-1 ring-gray-100 dark:ring-gray-800">
          <table className="w-full min-w-max text-left text-xs">
            <thead className="bg-gray-50 text-gray-500 dark:bg-gray-800/60 dark:text-gray-400">
              <tr>
                {card.columns.map((column, i) => (
                  <th key={`${column}-${i}`} className="px-2 py-1.5 font-medium">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {card.table.map((line, r) => (
                <tr key={r}>
                  {line.map((cell, c) => (
                    <td key={c} className="px-2 py-1.5 tabular-nums text-gray-800 dark:text-gray-200">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {card.href ? (
        <Link href={card.href} onClick={onNavigate} className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-blue-700 hover:underline dark:text-blue-400">
          Открыть →
        </Link>
      ) : null}
    </article>
  )
}
