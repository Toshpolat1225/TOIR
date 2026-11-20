// Hybrid speech recognition of the assistant: the BROWSER recogniser (Web Speech API, needs the user's own internet) is tried first, the local
// Whisper service answers when the browser cannot (no support, no internet, a network/service error, silence). Pure helpers: no imports, easy to test.
export type SttPref = "auto" | "whisper" | "browser"
export const STT_KEY = "toir.assistant.stt.v1"

export const STT_OPTIONS: { value: SttPref; label: string }[] = [
  { value: "auto", label: "Авто: браузер, затем Whisper" },
  { value: "whisper", label: "Только Whisper (локально)" },
  { value: "browser", label: "Только браузер" },
]

export function normalizeSttPref(value: unknown): SttPref {
  return value === "whisper" || value === "browser" ? value : "auto"
}

/** The language of the browser recogniser; «auto» follows the interface (Russian). */
export function browserLang(lang: "auto" | "uz" | "ru"): "ru-RU" | "uz-UZ" {
  return lang === "uz" ? "uz-UZ" : "ru-RU"
}

export type SttEnvironment = { supported: boolean; online: boolean; allowed: boolean }

/** Should the browser recogniser run for this press of the microphone? (`allowed` = the server did not forbid it, e.g. a closed-circuit policy) */
export function shouldTryBrowser(pref: SttPref, env: SttEnvironment): boolean {
  return pref !== "whisper" && env.allowed && env.supported && env.online
}

export type Heard = { text: string; confidence: number | null }

type Alt = { transcript?: string; confidence?: number }

/** The recognised sentence of a finished recogniser: the final results joined, the lowest confidence of the parts (0..1, or null when the browser gives none). */
export function joinResults(results: ArrayLike<ArrayLike<Alt> & { isFinal?: boolean }>): Heard | null {
  const parts: string[] = []
  let confidence: number | null = null
  for (let i = 0; i < results.length; i += 1) {
    const result = results[i]
    if (result.isFinal === false) continue
    const best = result[0]
    const text = (best?.transcript ?? "").trim()
    if (!text) continue
    parts.push(text)
    if (typeof best.confidence === "number" && best.confidence > 0) confidence = confidence === null ? best.confidence : Math.min(confidence, best.confidence)
  }
  const text = parts.join(" ").replace(/\s+/g, " ").trim()
  return text ? { text, confidence } : null
}

/** What to tell the user when the browser recogniser alone (pref «browser») could not hear anything. */
export const BROWSER_ONLY_FAILED = "Браузер не распознал речь (нет интернета или службы). Выберите «Авто» или «Whisper», либо напишите текстом."

/** Errors after which the browser recogniser will not work again in this session without a change (no internet, blocked service): the next press goes straight to Whisper. */
export function isHardBrowserError(error: string | null | undefined): boolean {
  return error === "network" || error === "service-not-allowed" || error === "language-not-supported"
}
