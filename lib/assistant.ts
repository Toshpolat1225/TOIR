// The command centre (voice/text assistant): the API contract (mirrors backend/app/schemas/assistant.py) and the pure helpers around it.
// No imports from the app: this file is unit-tested with `node --test`.

export type AssistantTone = "ok" | "warn" | "bad" | "info" | "muted"
export type AssistantCardKind = "asset" | "wagon" | "train" | "list" | "metric" | "text" | "table" | "confirm" | "help" | "error"
export type AssistantStatusKind = "ok" | "unmatched" | "denied" | "needs_confirm" | "needs_clarification" | "error"
export type AssistantLang = "auto" | "uz" | "ru"

export type AssistantEntityRef = { kind: "asset" | "train" | "work_order" | "section"; id: string; label: string; asset_type?: string | null }
export type AssistantDialog = { intent: string; base: string }
export type AssistantContext = { page?: string | null; asset_id?: string | null; train_gtk_id?: number | null; last_entity?: AssistantEntityRef | null; dialog?: AssistantDialog | null }
export type AssistantCommandIn = {
  text: string
  locale: AssistantLang
  source: "text" | "voice"
  stt_confidence?: number | null
  context?: AssistantContext | null
}
export type AssistantCardRow = { label: string; value: string; tone?: AssistantTone | null }
export type AssistantCardItem = {
  label: string
  sub?: string | null
  value?: string | null
  href?: string | null
  tone?: AssistantTone | null
  entity?: AssistantEntityRef | null
}
export type AssistantCard = {
  kind: AssistantCardKind
  title: string
  subtitle?: string | null
  tone?: AssistantTone | null
  rows: AssistantCardRow[]
  items: AssistantCardItem[]
  columns: string[]
  table: string[][]
  href?: string | null
  badge?: string | null
}
export type AssistantSuggestion = { text: string; intent?: string | null }
export type AssistantConfirmOut = { token: string; expires_at: string; summary: string; risk: "low" | "medium" }
export type AssistantCommandOut = {
  ok: boolean
  status: AssistantStatusKind
  intent?: string | null
  heard: string
  speak?: string | null
  speak_lang: "uz" | "ru"
  cards: AssistantCard[]
  navigate?: string | null
  confirm?: AssistantConfirmOut | null
  suggestions: AssistantSuggestion[]
  entities: AssistantEntityRef[]
  ms: number
  query_id?: number | null
  dialog?: AssistantDialog | null
}
export type AssistantConfirmIn = { token: string; approve: boolean; context?: AssistantContext | null }
export type AssistantTranscribeOut = { text: string; language?: string | null; confidence?: number | null; duration_s?: number | null; ms: number }
export type AssistantStatusOut = { voice_available: boolean; voice_model?: string | null; max_audio_s: number; write_actions: boolean }
export type AssistantHelpGroup = { module: string; title: string; examples: string[] }
export type AssistantHelpOut = { groups: AssistantHelpGroup[] }
export type AssistantUnmatchedItem = { text: string; count: number; last_at: string; best_intent?: string | null }
export type AssistantUnmatchedPage = { items: AssistantUnmatchedItem[]; total: number }

// ---- constants ---------------------------------------------------------------------------------------------
export const MAX_AUDIO_SECONDS = 30
export const MAX_AUDIO_BYTES = 2 * 1024 * 1024
export const LOW_CONFIDENCE = 0.6
export const HISTORY_KEY = "toir.assistant.history.v1"
export const LANG_KEY = "toir.assistant.lang.v1"
export const TTS_KEY = "toir.assistant.tts.v1"
export const HISTORY_LIMIT = 20
export const NAVIGATE_DELAY_MS = 1500
export const ONBOARDING_EXAMPLES = ["37919 qayerda", "открой карту", "muddati o'tgan ТО"]
export const LANG_OPTIONS: { value: AssistantLang; label: string }[] = [
  { value: "auto", label: "Авто" },
  { value: "uz", label: "O'zbekcha" },
  { value: "ru", label: "Русский" },
]

export function normalizeLang(value: unknown): AssistantLang {
  return value === "uz" || value === "ru" || value === "auto" ? value : "auto"
}

/** The `language` hint of the transcription request: nothing for «auto» (the recogniser detects it). */
export function transcribeLanguage(lang: AssistantLang): "uz" | "ru" | undefined {
  return lang === "auto" ? undefined : lang
}

// ---- yes / no by voice or keyboard ---------------------------------------------------------------------------
export function normalizeUtterance(text: string): string {
  return text
    .toLowerCase()
    .replace(/[ʻʼ’‘`´]/g, "'")
    .replace(/[.,!?;:«»"()]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

const YES_WORDS = new Set(["ha", "xa", "tasdiqlayman", "tasdiqla", "tasdiqlash", "mayli", "ok", "okay", "да", "подтверждаю", "подтвердить", "давай", "yes"])
const NO_WORDS = new Set(["yo'q", "yoq", "bekor", "отмена", "нет", "no", "cancel"])
const FILLER = new Set(["iltimos", "пожалуйста", "please", "qil", "qilish", "etaman", "o'zim"])

/** Is the whole utterance a «yes» or a «no»? Anything else (a real command, a mix) is null. */
export function detectConfirmReply(text: string): "yes" | "no" | null {
  const tokens = normalizeUtterance(text)
    .split(" ")
    .filter((t) => t && !FILLER.has(t))
  if (tokens.length === 0 || tokens.length > 4) return null
  if (tokens.every((t) => YES_WORDS.has(t))) return "yes"
  if (tokens.every((t) => NO_WORDS.has(t))) return "no"
  return null
}

/** A recognised phrase is sent straight away (no extra confirmation: the answer shows what was heard, with an «Исправить» button). Only an empty or one/two-letter result is held back, except a yes/no to an open confirmation. */
export function needsReview(text: string, _confidence: number | null | undefined, confirmOpen = false): boolean {
  if (confirmOpen && detectConfirmReply(text) !== null) return false
  return text.trim().length < 3
}

// ---- context -------------------------------------------------------------------------------------------------
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
const ASSET_PATH = new RegExp(`^/dashboard/gps/(?:wagons/)?(${UUID})/?$`, "i")

/** The asset whose page is open (/dashboard/gps/<uuid> and /dashboard/gps/wagons/<uuid>); a GTK-only wagon key («gtk-123») is not an asset. */
export function assetIdFromPath(pathname: string | null | undefined): string | null {
  if (!pathname) return null
  const match = ASSET_PATH.exec(pathname.split("?")[0])
  return match ? match[1].toLowerCase() : null
}

export function buildContext(pathname: string | null | undefined, lastEntity: AssistantEntityRef | null | undefined, dialog?: AssistantDialog | null): AssistantContext {
  return {
    page: pathname ? pathname.slice(0, 200) : null,
    asset_id: assetIdFromPath(pathname),
    last_entity: lastEntity ?? null,
    dialog: dialog ?? null,
  }
}

/** The entity that the next sentence refers to as «bu»: the first one of the newest answer, else the previous one. */
export function nextLastEntity(previous: AssistantEntityRef | null, out: Pick<AssistantCommandOut, "entities">): AssistantEntityRef | null {
  return out.entities && out.entities.length > 0 ? out.entities[0] : previous
}

// ---- text to speech ------------------------------------------------------------------------------------------
export type VoiceLike = { lang: string; localService?: boolean; name?: string }

/** A voice of the wanted language (local ones first); null when the browser has none: then the answer stays text. */
export function pickVoice<T extends VoiceLike>(voices: readonly T[], lang: "uz" | "ru"): T | null {
  const wanted = voices.filter((v) => (v.lang || "").toLowerCase().replace("_", "-").startsWith(lang))
  if (wanted.length === 0) return null
  return wanted.find((v) => v.localService) ?? wanted[0]
}

/** What is read aloud: plain text, no markup characters, at most ~300 characters (cut at a sentence end when possible). */
export function speechText(text: string | null | undefined, max = 300): string {
  const plain = (text ?? "").replace(/[*_`#>|]/g, " ").replace(/\s+/g, " ").trim()
  if (plain.length <= max) return plain
  const cut = plain.slice(0, max)
  const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "))
  return (end > max / 3 ? cut.slice(0, end + 1) : cut).trim()
}

export function shouldSpeak(enabled: boolean, out: Pick<AssistantCommandOut, "speak"> | null | undefined, voiceFound: boolean): boolean {
  return enabled && voiceFound && !!out?.speak && speechText(out.speak).length > 0
}

// ---- audio ---------------------------------------------------------------------------------------------------
const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg", "audio/mp4"]

export function pickRecorderMime(isSupported: (mime: string) => boolean): string | undefined {
  return MIME_CANDIDATES.find((mime) => {
    try {
      return isSupported(mime)
    } catch {
      return false
    }
  })
}

export function audioFileName(mime: string | undefined): string {
  const m = (mime ?? "").toLowerCase()
  if (m.includes("ogg")) return "voice.ogg"
  if (m.includes("mp4") || m.includes("aac")) return "voice.m4a"
  if (m.includes("wav")) return "voice.wav"
  return "voice.webm"
}

/** Loudness 0..1 of a time-domain frame (bytes centred on 128), scaled so that normal speech reaches about the middle of the meter. */
export function rmsLevel(data: ArrayLike<number>): number {
  if (!data.length) return 0
  let sum = 0
  for (let i = 0; i < data.length; i++) {
    const v = (data[i] - 128) / 128
    sum += v * v
  }
  return Math.max(0, Math.min(1, Math.sqrt(sum / data.length) * 3))
}

export function microphoneProblem(opts: { secure: boolean; hasMediaDevices: boolean; hasRecorder: boolean }): string | null {
  if (!opts.secure) return "Микрофон работает только по HTTPS. Откройте систему по защищённому адресу или пользуйтесь текстом."
  if (!opts.hasMediaDevices || !opts.hasRecorder) return "Этот браузер не поддерживает запись голоса. Пользуйтесь текстовым вводом."
  return null
}

export function microphoneErrorMessage(error: unknown): string {
  const name = error && typeof error === "object" && "name" in error ? String((error as { name: unknown }).name) : ""
  if (name === "NotAllowedError" || name === "SecurityError") return "Доступ к микрофону запрещён. Разрешите микрофон в настройках браузера или пользуйтесь текстом."
  if (name === "NotFoundError" || name === "OverconstrainedError") return "Микрофон не найден. Подключите микрофон или пользуйтесь текстом."
  if (name === "NotReadableError") return "Микрофон занят другим приложением."
  return "Не удалось начать запись. Пользуйтесь текстовым вводом."
}

// ---- errors --------------------------------------------------------------------------------------------------
export function mapAssistantError(error: unknown): string {
  const status = error && typeof error === "object" && "status" in error ? Number((error as { status: unknown }).status) : NaN
  const name = error && typeof error === "object" && "name" in error ? String((error as { name: unknown }).name) : ""
  const message = error instanceof Error ? error.message : ""
  if (status === 403) return "Недостаточно прав для этой команды."
  if (status === 404) return "Не найдено или нет доступа."
  if (status === 410) return "Срок подтверждения истёк. Повторите команду."
  if (status === 413) return "Запись слишком длинная или большая. Скажите короче (до 30 секунд)."
  if (status === 422) return "Команда не принята сервером. Переформулируйте."
  if (status === 429) return "Слишком много запросов. Подождите немного."
  if (status === 502 || status === 503 || status === 504) return "Сервис временно недоступен (возможно, голосовой модуль выключен). Пользуйтесь текстом."
  if (name === "TypeError" || /failed to fetch|network/i.test(message)) return "Нет связи с сервером."
  return message || "Не удалось выполнить команду."
}

// ---- confirmation countdown ------------------------------------------------------------------------------------
export function secondsLeft(expiresAt: string, nowMs: number): number {
  const at = Date.parse(expiresAt)
  if (Number.isNaN(at)) return 0
  return Math.max(0, Math.ceil((at - nowMs) / 1000))
}

export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

// ---- history (the last answers, kept in localStorage) -------------------------------------------------------------
export type AssistantResolved = "approved" | "cancelled" | "expired"
export type HistoryEntry = {
  id: string
  at: string
  query: string
  source: "text" | "voice"
  out?: AssistantCommandOut | null
  error?: string | null
  resolved?: AssistantResolved | null
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

export function parseHistory(raw: string | null | undefined): HistoryEntry[] {
  if (!raw) return []
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(data)) return []
  const entries: HistoryEntry[] = []
  for (const item of data) {
    if (!isObject(item) || typeof item.id !== "string" || typeof item.at !== "string" || typeof item.query !== "string") continue
    const out = isObject(item.out) && Array.isArray(item.out.cards) && typeof item.out.heard === "string" ? (item.out as unknown as AssistantCommandOut) : null
    entries.push({
      id: item.id,
      at: item.at,
      query: item.query,
      source: item.source === "voice" ? "voice" : "text",
      out,
      error: typeof item.error === "string" ? item.error : null,
      resolved: item.resolved === "approved" || item.resolved === "cancelled" || item.resolved === "expired" ? item.resolved : null,
    })
  }
  return entries.slice(-HISTORY_LIMIT)
}

export function appendHistory(list: readonly HistoryEntry[], entry: HistoryEntry, limit = HISTORY_LIMIT): HistoryEntry[] {
  return [...list, entry].slice(-limit)
}

export function patchHistory(list: readonly HistoryEntry[], id: string, patch: Partial<HistoryEntry>): HistoryEntry[] {
  return list.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry))
}

/** The confirmation that is still waiting for an answer: the newest entry that asks for one and has not been resolved. */
export function openConfirmation(list: readonly HistoryEntry[], nowMs: number): HistoryEntry | null {
  for (let i = list.length - 1; i >= 0; i--) {
    const entry = list[i]
    const confirm = entry.out?.confirm
    if (!confirm || entry.out?.status !== "needs_confirm") continue
    if (entry.resolved) return null // the newest confirmation is already answered
    return secondsLeft(confirm.expires_at, nowMs) > 0 ? entry : null
  }
  return null
}

export function newEntryId(nowMs: number, counter: number): string {
  return `${nowMs.toString(36)}-${counter.toString(36)}`
}
