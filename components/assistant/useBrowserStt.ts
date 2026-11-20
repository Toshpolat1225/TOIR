"use client"

// The browser's own speech recogniser (Web Speech API), run in PARALLEL with the recording: when it hears the sentence the audio is never uploaded,
// when it cannot (no internet, a service error, silence) the recording goes to the local Whisper. Needs the user's own internet; the server needs none.
import { useCallback, useRef, useState } from "react"
import { isHardBrowserError, joinResults, type Heard } from "@/lib/browser-stt"

type RecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript?: string; confidence?: number }> & { isFinal?: boolean }> }) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}
type RecognitionCtor = new () => RecognitionLike

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

const WAIT_AFTER_STOP_MS = 1500 // the final result arrives a moment after the button is released

export function useBrowserStt() {
  const [supported] = useState(() => recognitionCtor() !== null)
  const [broken, setBroken] = useState(false) // a hard error happened: no more attempts until the page is reloaded
  const rec = useRef<RecognitionLike | null>(null)
  const result = useRef<Heard | null>(null)
  const done = useRef<Promise<void> | null>(null)
  const resolveDone = useRef<(() => void) | null>(null)
  const active = useRef(false)

  const start = useCallback((lang: string) => {
    const Ctor = recognitionCtor()
    if (!Ctor || active.current) return
    try {
      const r = new Ctor()
      r.lang = lang
      r.continuous = true // keep listening while the button is held
      r.interimResults = false
      r.maxAlternatives = 1
      result.current = null
      done.current = new Promise<void>((resolve) => { resolveDone.current = resolve })
      r.onresult = (event) => { result.current = joinResults(event.results) ?? result.current }
      r.onerror = (event) => { if (isHardBrowserError(event.error)) setBroken(true) }
      r.onend = () => { active.current = false; resolveDone.current?.() }
      rec.current = r
      active.current = true
      r.start()
    } catch {
      active.current = false
      resolveDone.current?.()
    }
  }, [])

  const stop = useCallback(() => {
    try { rec.current?.stop() } catch { /* already stopped */ }
  }, [])

  const cancel = useCallback(() => {
    try { rec.current?.abort() } catch { /* already stopped */ }
    result.current = null
  }, [])

  /** The sentence the browser heard (null: nothing, an error, or too slow). Resolves a moment after `stop()`. */
  const take = useCallback(async (): Promise<Heard | null> => {
    const pending = done.current
    if (!pending) return null
    await Promise.race([pending, new Promise<void>((resolve) => window.setTimeout(resolve, WAIT_AFTER_STOP_MS))])
    try { rec.current?.abort() } catch { /* already stopped */ }
    const heard = result.current
    result.current = null
    done.current = null
    rec.current = null
    return heard
  }, [])

  return { supported, broken, start, stop, cancel, take }
}
