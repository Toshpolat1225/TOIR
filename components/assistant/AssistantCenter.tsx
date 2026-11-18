"use client"

// The command centre: header buttons (microphone, «Команды»), Ctrl+K, and a panel with the conversation of result cards, push-to-talk voice,
// a confirmation flow for writes, help and text-to-speech. Everything goes through api.assistant.*.
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react"
import { createPortal } from "react-dom"
import { HelpCircle, Loader2, Mic, MicFill, Send, StopFill, Volume2, X } from "@/components/ui/icons"
import { api, type AssistantCommandOut, type AssistantEntityRef, type AssistantHelpOut, type AssistantStatusOut } from "@/lib/api"
import {
  HISTORY_KEY,
  LANG_KEY,
  LANG_OPTIONS,
  MAX_AUDIO_SECONDS,
  NAVIGATE_DELAY_MS,
  ONBOARDING_EXAMPLES,
  TTS_KEY,
  appendHistory,
  audioFileName,
  buildContext,
  type AssistantDialog,
  detectConfirmReply,
  formatCountdown,
  mapAssistantError,
  needsReview,
  newEntryId,
  nextLastEntity,
  normalizeLang,
  openConfirmation,
  parseHistory,
  patchHistory,
  pickVoice,
  secondsLeft,
  shouldSpeak,
  speechText,
  transcribeLanguage,
  type AssistantLang,
  type AssistantResolved,
  type HistoryEntry,
} from "@/lib/assistant"
import { AssistantCardView } from "./AssistantCards"
import { useVoiceRecorder } from "./useVoiceRecorder"

type Pending = { query: string; source: "text" | "voice"; label: string }
type Review = { text: string; confidence: number | null }

const FIELD = "rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"

function safeNavigate(path: string | null | undefined): string | null {
  if (!path || !path.startsWith("/") || path.startsWith("//")) return null
  return path
}

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // storage may be blocked (private window): the assistant still works, it just forgets
  }
}

const RESOLVED_TEXT: Record<AssistantResolved, string> = {
  approved: "Подтверждено",
  cancelled: "Отменено",
  expired: "Срок подтверждения истёк",
}

export function AssistantCenter() {
  const router = useRouter()
  const pathname = usePathname()

  const [mounted, setMounted] = useState(false)
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState<Pending | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [lastEntity, setLastEntity] = useState<AssistantEntityRef | null>(null)
  const [lang, setLang] = useState<AssistantLang>("auto")
  const [tts, setTts] = useState(false)
  const [status, setStatus] = useState<AssistantStatusOut | null>(null)
  const [statusFailed, setStatusFailed] = useState(false)
  const [help, setHelp] = useState<AssistantHelpOut | null>(null)
  const [helpFailed, setHelpFailed] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [review, setReview] = useState<Review | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [navPending, setNavPending] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const counter = useRef(0)
  const busyRef = useRef(false)
  const historyRef = useRef<HistoryEntry[]>([])
  const lastEntityRef = useRef<AssistantEntityRef | null>(null)
  const dialogRef = useRef<AssistantDialog | null>(null)
  const langRef = useRef<AssistantLang>("auto")
  const ttsRef = useRef(false)
  const pathRef = useRef<string | null>(null)
  const requestRef = useRef<AbortController | null>(null)
  historyRef.current = history
  lastEntityRef.current = lastEntity
  langRef.current = lang
  ttsRef.current = tts
  pathRef.current = pathname

  // ---- persisted preferences and the last answers ----
  useEffect(() => {
    setMounted(true)
    setHistory(parseHistory(readStorage(HISTORY_KEY)))
    setLang(normalizeLang(readStorage(LANG_KEY)))
    setTts(readStorage(TTS_KEY) === "1")
  }, [])
  useEffect(() => {
    if (mounted) writeStorage(HISTORY_KEY, JSON.stringify(history))
  }, [history, mounted])
  useEffect(() => {
    if (mounted) writeStorage(LANG_KEY, lang)
  }, [lang, mounted])
  useEffect(() => {
    if (mounted) writeStorage(TTS_KEY, tts ? "1" : "0")
  }, [tts, mounted])

  const confirmEntry = useMemo(() => openConfirmation(history, now), [history, now])

  // a one-second ticker only while a confirmation is counting down
  useEffect(() => {
    if (!confirmEntry || !open) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [confirmEntry, open])

  // ---- voice service availability (asked when the panel is first opened) ----
  useEffect(() => {
    if (!open || status || statusFailed) return
    let alive = true
    api.assistant
      .status()
      .then((value) => alive && setStatus(value))
      .catch(() => alive && setStatusFailed(true))
    return () => {
      alive = false
    }
  }, [open, status, statusFailed])

  useEffect(() => {
    if (!open || !showHelp || help || helpFailed) return
    let alive = true
    api.assistant
      .help()
      .then((value) => alive && setHelp(value))
      .catch(() => alive && setHelpFailed(true))
    return () => {
      alive = false
    }
  }, [open, showHelp, help, helpFailed])

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 30)
  }, [open])

  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [history, busy, review, navPending, showHelp])

  useEffect(() => {
    if (!notice) return
    const id = window.setTimeout(() => setNotice(null), 3500)
    return () => window.clearTimeout(id)
  }, [notice])

  // ---- text to speech ----
  const stopSpeaking = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel()
  }, [])

  const speak = useCallback((out: AssistantCommandOut) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return
    const voice = pickVoice(window.speechSynthesis.getVoices(), out.speak_lang)
    if (!shouldSpeak(ttsRef.current, out, voice !== null) || !voice) return // never speaks unless the toggle is on and a voice of that language exists
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(speechText(out.speak))
    utterance.voice = voice
    utterance.lang = voice.lang
    window.speechSynthesis.speak(utterance)
  }, [])

  const close = useCallback(() => {
    setOpen(false)
    stopSpeaking()
  }, [stopSpeaking])

  // ---- sending a sentence ----
  const addEntry = useCallback((entry: HistoryEntry) => setHistory((list) => appendHistory(list, entry)), [])

  const handleResult = useCallback(
    (out: AssistantCommandOut) => {
      setLastEntity((previous) => nextLastEntity(previous, out))
      dialogRef.current = out.dialog ?? null // an unfinished command: the next answer completes it
      speak(out)
      const target = safeNavigate(out.navigate)
      if (target) setNavPending(target)
    },
    [speak],
  )

  const answerConfirm = useCallback(
    async (entry: HistoryEntry, approve: boolean, spoken?: string) => {
      const confirm = entry.out?.confirm
      if (!confirm || busyRef.current) return
      if (secondsLeft(confirm.expires_at, Date.now()) <= 0) {
        setHistory((list) => patchHistory(list, entry.id, { resolved: "expired" }))
        return
      }
      busyRef.current = true
      setBusy({ query: spoken ?? (approve ? "Подтвердить" : "Отмена"), source: "text", label: approve ? "Выполняю…" : "Отменяю…" })
      try {
        const out = await api.assistant.confirm({ token: confirm.token, approve, context: buildContext(pathRef.current, lastEntityRef.current) })
        setHistory((list) => patchHistory(list, entry.id, { resolved: approve ? "approved" : "cancelled" }))
        addEntry({ id: newEntryId(Date.now(), counter.current++), at: new Date().toISOString(), query: spoken ?? (approve ? "Подтвердить" : "Отмена"), source: "text", out })
        handleResult(out)
      } catch (error) {
        const status = error && typeof error === "object" && "status" in error ? Number((error as { status: unknown }).status) : 0
        setHistory((list) => patchHistory(list, entry.id, { resolved: status === 410 || status === 400 ? "expired" : null }))
        addEntry({ id: newEntryId(Date.now(), counter.current++), at: new Date().toISOString(), query: spoken ?? "Подтверждение", source: "text", error: mapAssistantError(error) })
      } finally {
        busyRef.current = false
        setBusy(null)
      }
    },
    [addEntry, handleResult],
  )

  const submit = useCallback(
    async (raw: string, source: "text" | "voice" = "text", confidence: number | null = null) => {
      const text = raw.trim()
      if (!text || busyRef.current) return
      setProblem(null)
      setReview(null)
      setShowHelp(false)
      setNavPending(null)
      const waiting = openConfirmation(historyRef.current, Date.now())
      if (waiting) {
        const reply = detectConfirmReply(text)
        if (reply) {
          setInput("")
          await answerConfirm(waiting, reply === "yes", text)
          return
        }
      }
      busyRef.current = true
      setBusy({ query: text, source, label: "Думаю…" })
      setInput("")
      const controller = new AbortController()
      requestRef.current = controller
      try {
        const out = await api.assistant.command(
          { text, locale: langRef.current, source, stt_confidence: source === "voice" ? confidence : null, context: buildContext(pathRef.current, lastEntityRef.current, dialogRef.current) },
          controller.signal,
        )
        addEntry({ id: newEntryId(Date.now(), counter.current++), at: new Date().toISOString(), query: text, source, out })
        handleResult(out)
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return
        addEntry({ id: newEntryId(Date.now(), counter.current++), at: new Date().toISOString(), query: text, source, error: mapAssistantError(error) })
      } finally {
        busyRef.current = false
        setBusy(null)
      }
    },
    [addEntry, answerConfirm, handleResult],
  )

  // ---- voice ----
  const onRecorded = useCallback(
    async (blob: Blob, mime: string) => {
      if (busyRef.current) return
      busyRef.current = true
      setBusy({ query: "", source: "voice", label: "Распознаю речь…" })
      let recognised: { text: string; confidence: number | null } | null = null
      try {
        const result = await api.assistant.transcribe(blob, audioFileName(mime), transcribeLanguage(langRef.current))
        recognised = { text: (result.text ?? "").trim(), confidence: typeof result.confidence === "number" ? result.confidence : null }
      } catch (error) {
        setProblem(mapAssistantError(error))
      } finally {
        busyRef.current = false
        setBusy(null)
      }
      if (!recognised) return
      if (!recognised.text) {
        setProblem("Речь не распознана. Повторите громче и ближе к микрофону или напишите текстом.")
        return
      }
      const waiting = openConfirmation(historyRef.current, Date.now())
      if (needsReview(recognised.text, recognised.confidence, !!waiting)) setReview(recognised)
      else await submit(recognised.text, "voice", recognised.confidence)
    },
    [submit],
  )

  const recorder = useVoiceRecorder({ onRecorded: (blob, mime) => void onRecorded(blob, mime), onProblem: setProblem })
  const voiceAvailable = status?.voice_available === true

  // ---- keyboard: Ctrl+K toggles, Esc closes ----
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setOpen((value) => !value)
      } else if (event.key === "Escape" && open) {
        recorder.cancel()
        close()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, close, recorder])

  // hold Space (focus not in a text field or on a button) = push-to-talk
  const onPanelKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.code !== "Space" || event.repeat || !voiceAvailable) return
    const tag = (event.target as HTMLElement).tagName
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON") return
    event.preventDefault()
    void recorder.start()
  }
  const onPanelKeyUp = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.code === "Space" && recorder.recording) {
      event.preventDefault()
      recorder.stop()
    }
  }

  // ---- navigation requested by an answer: shown first, cancellable for 1.5 s ----
  useEffect(() => {
    if (!navPending) return
    const id = window.setTimeout(() => {
      router.push(navPending)
      setNavPending(null)
      setOpen(false)
    }, NAVIGATE_DELAY_MS)
    return () => window.clearTimeout(id)
  }, [navPending, router])

  useEffect(
    () => () => {
      requestRef.current?.abort()
      if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel()
    },
    [],
  )

  const onEntity = useCallback((entity: AssistantEntityRef) => {
    setLastEntity(entity)
    setNotice(`Контекст: ${entity.label}. Скажите «bu» / «этот».`)
  }, [])

  const toggleTts = (value: boolean) => {
    setTts(value)
    if (!value) stopSpeaking()
    else if (typeof window !== "undefined" && "speechSynthesis" in window && !pickVoice(window.speechSynthesis.getVoices(), "ru")) {
      setNotice("Русский голос в браузере не найден: ответы останутся текстом.")
    }
  }

  const lastEntry = history[history.length - 1]
  const suggestions = lastEntry?.out?.suggestions ?? []
  const empty = history.length === 0 && !busy

  const header = (
    <>
      <button
        type="button"
        data-testid="assistant-open"
        aria-label="Голосовая команда (Ctrl+K)"
        title="Голосовая команда (Ctrl+K)"
        onClick={() => setOpen(true)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 dark:text-gray-300 dark:hover:bg-gray-800"
      >
        <Mic className="text-lg" />
      </button>
      <button
        type="button"
        data-testid="assistant-help-open"
        onClick={() => {
          setOpen(true)
          setShowHelp(true)
        }}
        className="inline-flex h-9 items-center gap-1.5 rounded-lg px-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-gray-300 dark:hover:bg-gray-800"
      >
        <HelpCircle />
        <span className="hidden sm:inline">Команды</span>
      </button>
    </>
  )

  const panel = (
    <div className="fixed inset-0 z-[70]">
      <button type="button" aria-label="Закрыть помощника" className="absolute inset-0 bg-slate-950/40 backdrop-blur-[1px]" onClick={() => { recorder.cancel(); close() }} />
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Голосовой помощник"
        data-testid="assistant-panel"
        tabIndex={-1}
        onKeyDown={onPanelKeyDown}
        onKeyUp={onPanelKeyUp}
        className="absolute inset-y-0 right-0 flex w-full max-w-[460px] min-w-0 flex-col bg-slate-50 shadow-2xl outline-none dark:bg-gray-950"
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 dark:border-gray-800 dark:bg-gray-900">
          <h2 className="mr-auto text-sm font-semibold text-slate-900 dark:text-white">Помощник · Yordamchi</h2>
          <select data-testid="assistant-lang" aria-label="Язык распознавания" value={lang} onChange={(e) => setLang(normalizeLang(e.target.value))} className={FIELD}>
            {LANG_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-slate-600 dark:text-gray-300">
            <input type="checkbox" data-testid="assistant-tts" checked={tts} onChange={(e) => toggleTts(e.target.checked)} />
            <Volume2 /> Озвучивать ответы
          </label>
          <button type="button" onClick={() => setShowHelp((v) => !v)} aria-pressed={showHelp} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-gray-800">
            <HelpCircle /> Команды
          </button>
          <button type="button" aria-label="Закрыть" onClick={() => { recorder.cancel(); close() }} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:text-gray-400 dark:hover:bg-gray-800">
            <X />
          </button>
        </div>

        <div ref={listRef} aria-live="polite" className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden px-3 py-3">
          {showHelp ? (
            <div data-testid="assistant-help" className="rounded-2xl border border-indigo-200 bg-white p-3 dark:border-indigo-900 dark:bg-gray-900">
              <p className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">Что можно сказать или написать</p>
              {helpFailed ? <p className="text-sm text-rose-700 dark:text-rose-400">Не удалось загрузить список команд.</p> : null}
              {!help && !helpFailed ? <p className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="animate-spin" /> Загрузка…</p> : null}
              {help?.groups.map((group) => (
                <div key={group.module} className="mb-2 last:mb-0">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">{group.title}</p>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {group.examples.map((example) => (
                      <button key={example} type="button" data-testid="assistant-help-example" onClick={() => void submit(example)} className="max-w-full break-words rounded-full bg-indigo-50 px-2.5 py-1 text-left text-xs text-indigo-900 ring-1 ring-indigo-200 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:text-indigo-100 dark:ring-indigo-800">
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {empty && !showHelp ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
              <p className="font-medium text-slate-900 dark:text-white">Скажите или напишите команду</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-gray-400">
                Например: {ONBOARDING_EXAMPLES.map((e) => `«${e}»`).join(" · ")}. Нажмите Ctrl+K, чтобы открыть помощника в любой момент.
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {ONBOARDING_EXAMPLES.map((example) => (
                  <button key={example} type="button" data-testid="assistant-suggestion" onClick={() => void submit(example)} className="rounded-full bg-blue-50 px-2.5 py-1 text-xs text-blue-900 ring-1 ring-blue-200 hover:bg-blue-100 dark:bg-blue-950/40 dark:text-blue-100 dark:ring-blue-800">
                    {example}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {history.map((entry) => {
            const out = entry.out
            const confirm = out?.confirm
            const remaining = confirm ? secondsLeft(confirm.expires_at, now) : 0
            const state: AssistantResolved | null = entry.resolved ?? (confirm && out?.status === "needs_confirm" && remaining <= 0 ? "expired" : null)
            const isOpenConfirm = confirmEntry?.id === entry.id && !state
            return (
              <div key={entry.id} className="space-y-2">
                <div className="flex justify-end">
                  <p className="max-w-[85%] break-words rounded-2xl rounded-br-md bg-blue-600 px-3 py-1.5 text-sm text-white">
                    {entry.source === "voice" ? <Mic className="mr-1 text-xs opacity-80" /> : null}
                    {entry.query}
                  </p>
                </div>
                {entry.error ? (
                  <p data-testid="assistant-error" role="alert" className="break-words rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200">
                    {entry.error}
                  </p>
                ) : null}
                {out ? (
                  <div className="space-y-2">
                    <p data-testid="assistant-heard" className="break-words text-[11px] text-slate-500 dark:text-gray-400">
                      Вы сказали: «{out.heard}»
                      {entry.source === "voice" && out.status !== "needs_confirm" ? (
                        <button type="button" data-testid="assistant-fix" onClick={() => { setInput(entry.query); inputRef.current?.focus() }} className="ml-2 font-medium text-blue-600 underline hover:text-blue-700 dark:text-blue-400">
                          Исправить
                        </button>
                      ) : null}
                    </p>
                    {out.cards.map((card, i) => (
                      <AssistantCardView key={i} card={card} onEntity={onEntity} onNavigate={close} />
                    ))}
                    {out.cards.length === 0 && out.status !== "needs_confirm" ? (
                      <p className="break-words rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200">
                        {out.status === "denied" ? "Нет прав на эту команду." : out.status === "unmatched" ? "Не понял команду. Попробуйте переформулировать или откройте «Команды»." : out.status === "needs_clarification" ? "Уточните, пожалуйста." : out.status === "error" ? "Не удалось выполнить команду." : "Готово."}
                      </p>
                    ) : null}
                    {confirm ? (
                      <div data-testid="assistant-confirm" data-state={state ?? "open"} className="rounded-2xl border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30">
                        <p className="break-words font-medium text-amber-950 dark:text-amber-100">{confirm.summary}</p>
                        {state ? (
                          <p className="mt-1 text-xs text-amber-900/80 dark:text-amber-200/80">{RESOLVED_TEXT[state]}</p>
                        ) : (
                          <>
                            <p className="mt-1 text-xs text-amber-900/80 dark:text-amber-200/80">
                              Осталось {formatCountdown(remaining)}{confirm.risk === "medium" ? " · внимание: изменит данные" : ""}. Скажите «ha» / «да» или «yo&apos;q» / «нет».
                            </p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <button type="button" data-testid="assistant-confirm-yes" disabled={!!busy || !isOpenConfirm} onClick={() => void answerConfirm(entry, true)} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                                Подтвердить
                              </button>
                              <button type="button" data-testid="assistant-confirm-no" disabled={!!busy || !isOpenConfirm} onClick={() => void answerConfirm(entry, false)} className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:opacity-50 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-700">
                                Отмена
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )
          })}

          {busy ? (
            <div className="space-y-2">
              {busy.query ? (
                <div className="flex justify-end">
                  <p className="max-w-[85%] break-words rounded-2xl rounded-br-md bg-blue-600/70 px-3 py-1.5 text-sm text-white">{busy.query}</p>
                </div>
              ) : null}
              <p className="flex items-center gap-2 text-sm text-slate-500 dark:text-gray-400"><Loader2 className="animate-spin" /> {busy.label}</p>
            </div>
          ) : null}

          {navPending ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-sky-50 px-3 py-2 text-sm text-sky-900 ring-1 ring-sky-200 dark:bg-sky-950/30 dark:text-sky-100 dark:ring-sky-900">
              <span className="min-w-0 break-words">Открываю {navPending}…</span>
              <button type="button" onClick={() => setNavPending(null)} className="rounded-lg bg-white px-2.5 py-1 text-xs font-medium ring-1 ring-sky-300 hover:bg-sky-100 dark:bg-gray-900 dark:ring-sky-800">Отмена</button>
            </div>
          ) : null}

          {suggestions.length > 0 && !busy ? (
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((s, i) => (
                <button key={`${s.text}-${i}`} type="button" data-testid="assistant-suggestion" onClick={() => void submit(s.text)} className="max-w-full break-words rounded-full bg-white px-2.5 py-1 text-left text-xs text-blue-900 ring-1 ring-blue-200 hover:bg-blue-50 dark:bg-gray-900 dark:text-blue-100 dark:ring-blue-900">
                  {s.text}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="border-t border-slate-200 bg-white px-3 py-2 dark:border-gray-800 dark:bg-gray-900">
          {problem ? (
            <p data-testid="assistant-error" role="alert" className="mb-2 flex items-start justify-between gap-2 rounded-lg bg-rose-50 px-2.5 py-1.5 text-xs text-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
              <span className="min-w-0 break-words">
                {problem}
                {typeof window !== "undefined" && window.location.protocol === "http:" && /HTTPS/.test(problem) ? (
                  <>
                    {" "}
                    <a data-testid="assistant-https-link" className="font-semibold underline" href={`https://${window.location.host}${window.location.pathname}`}>
                      Открыть по HTTPS
                    </a>
                    <span className="block pt-1 text-rose-700/80 dark:text-rose-300/80">
                      Если браузер предупредит о сертификате: установите toir-local-root.crt один раз (Доверенные корневые центры) или нажмите «Дополнительно → Перейти».
                    </span>
                  </>
                ) : null}
              </span>
              <button type="button" aria-label="Скрыть" onClick={() => setProblem(null)}><X /></button>
            </p>
          ) : null}
          {notice ? <p className="mb-2 break-words rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-700 dark:bg-gray-800 dark:text-gray-200">{notice}</p> : null}
          {review ? (
            <div className="mb-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-sm dark:border-amber-800 dark:bg-amber-950/30">
              <p className="break-words text-amber-950 dark:text-amber-100">Siz aytdingiz: «{review.text}»{review.confidence !== null ? <span className="text-xs opacity-70"> ({Math.round(review.confidence * 100)}%)</span> : null}</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                <button type="button" onClick={() => void submit(review.text, "voice", review.confidence)} className="rounded-lg bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700">Отправить</button>
                <button type="button" onClick={() => { setInput(review.text); setReview(null); inputRef.current?.focus() }} className="rounded-lg bg-white px-3 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-700">Править</button>
                <button type="button" onClick={() => setReview(null)} className="rounded-lg px-3 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:text-gray-300 dark:hover:bg-gray-800">Отмена</button>
              </div>
            </div>
          ) : null}
          {recorder.recording ? (
            <div className="mb-2 flex items-center gap-2 text-xs text-rose-700 dark:text-rose-300">
              <MicFill className="animate-pulse" />
              <span className="tabular-nums">{recorder.seconds} / {MAX_AUDIO_SECONDS} с</span>
              <span className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-rose-100 dark:bg-rose-950"><span className="block h-full rounded-full bg-rose-500 transition-[width] duration-75" style={{ width: `${Math.round(recorder.level * 100)}%` }} /></span>
              <span>отпустите, чтобы отправить</span>
            </div>
          ) : null}
          {!voiceAvailable && (status || statusFailed) ? <p className="mb-2 text-xs text-slate-500 dark:text-gray-400">Голос выключен — пользуйтесь текстом.</p> : null}
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              void submit(input)
            }}
          >
            <input
              ref={inputRef}
              data-testid="assistant-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={400}
              autoComplete="off"
              placeholder={confirmEntry ? "ha / да — подтвердить, yo'q / нет — отменить" : "37919 qayerda · открой карту · …"}
              aria-label="Команда"
              className="h-11 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
            />
            {voiceAvailable ? (
              <button
                type="button"
                data-testid="assistant-mic"
                aria-label="Удерживайте и говорите"
                aria-pressed={recorder.recording}
                title="Удерживайте и говорите (или удерживайте пробел)"
                onPointerDown={(e) => { e.preventDefault(); void recorder.start() }}
                onPointerUp={() => recorder.stop()}
                onPointerLeave={() => recorder.stop()}
                onPointerCancel={() => recorder.stop()}
                onContextMenu={(e) => e.preventDefault()}
                className={`inline-flex h-12 w-12 shrink-0 touch-none select-none items-center justify-center rounded-full text-xl text-white shadow ${recorder.recording ? "animate-pulse bg-rose-600" : "bg-slate-800 hover:bg-slate-700 dark:bg-gray-700"}`}
              >
                {recorder.recording ? <StopFill /> : <Mic />}
              </button>
            ) : null}
            <button type="submit" data-testid="assistant-send" disabled={!!busy || !input.trim()} aria-label="Отправить" className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
              <Send />
            </button>
          </form>
          <p className="mt-1.5 text-[10px] text-slate-400 dark:text-gray-500">
            {voiceAvailable ? "Удерживайте микрофон или пробел и говорите. " : ""}
            <Link href="/dashboard" onClick={close} className="hover:underline">На главную</Link>
          </p>
        </div>
      </section>
    </div>
  )

  return (
    <>
      {header}
      {mounted && open ? createPortal(panel, document.body) : null}
    </>
  )
}
