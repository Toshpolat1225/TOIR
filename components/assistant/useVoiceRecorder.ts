"use client"

// Push-to-talk recording: MediaRecorder + a level meter. Nothing is uploaded here; the caller gets the Blob when the recording stops.
import { useCallback, useEffect, useRef, useState } from "react"
import { MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS, microphoneErrorMessage, microphoneProblem, pickRecorderMime, rmsLevel } from "@/lib/assistant"

const MIN_SECONDS = 0.4

type Options = {
  onRecorded: (blob: Blob, mime: string, seconds: number) => void
  onProblem: (message: string) => void
}

type AudioContextCtor = typeof AudioContext

export function useVoiceRecorder({ onRecorded, onProblem }: Options) {
  const [recording, setRecording] = useState(false)
  const [level, setLevel] = useState(0)
  const [seconds, setSeconds] = useState(0)

  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const chunks = useRef<Blob[]>([])
  const audioContext = useRef<AudioContext | null>(null)
  const frame = useRef<number | null>(null)
  const timer = useRef<number | null>(null)
  const autoStop = useRef<number | null>(null)
  const startedAt = useRef(0)
  const session = useRef(0) // a press that is released before the microphone is ready must not start a recording
  const starting = useRef(false)
  const cancelled = useRef(false)
  const callbacks = useRef({ onRecorded, onProblem })
  callbacks.current = { onRecorded, onProblem }

  const release = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    if (timer.current !== null) window.clearInterval(timer.current)
    if (autoStop.current !== null) window.clearTimeout(autoStop.current)
    frame.current = timer.current = autoStop.current = null
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
    void audioContext.current?.close().catch(() => undefined)
    audioContext.current = null
    recorder.current = null
    setRecording(false)
    setLevel(0)
    setSeconds(0)
  }, [])

  const stop = useCallback(() => {
    session.current += 1 // invalidates a start that is still waiting for the microphone permission
    const active = recorder.current
    if (active && active.state !== "inactive") active.stop()
  }, [])

  const cancel = useCallback(() => {
    cancelled.current = true
    stop()
  }, [stop])

  const start = useCallback(async () => {
    if (recorder.current || starting.current) return
    const problem = microphoneProblem({
      secure: typeof window !== "undefined" && window.isSecureContext,
      hasMediaDevices: typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia,
      hasRecorder: typeof MediaRecorder !== "undefined",
    })
    if (problem) {
      callbacks.current.onProblem(problem)
      return
    }
    const mySession = ++session.current
    starting.current = true
    cancelled.current = false
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      if (mySession !== session.current) {
        media.getTracks().forEach((track) => track.stop()) // released before the permission came back
        return
      }
      stream.current = media
      const mime = pickRecorderMime((m) => MediaRecorder.isTypeSupported(m))
      const rec = new MediaRecorder(media, mime ? { mimeType: mime } : undefined)
      chunks.current = []
      rec.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunks.current.push(event.data)
      }
      rec.onstop = () => {
        const elapsed = (Date.now() - startedAt.current) / 1000
        const type = rec.mimeType || mime || "audio/webm"
        const blob = new Blob(chunks.current, { type })
        chunks.current = []
        const wasCancelled = cancelled.current
        release()
        if (wasCancelled) return
        if (elapsed < MIN_SECONDS || blob.size === 0) return callbacks.current.onProblem("Запись слишком короткая. Удерживайте кнопку, пока говорите.")
        if (blob.size > MAX_AUDIO_BYTES) return callbacks.current.onProblem("Запись слишком большая. Скажите короче (до 30 секунд).")
        callbacks.current.onRecorded(blob, type, elapsed)
      }
      rec.onerror = () => {
        release()
        callbacks.current.onProblem("Ошибка записи. Пользуйтесь текстовым вводом.")
      }
      recorder.current = rec
      startedAt.current = Date.now()
      rec.start()
      setRecording(true)
      timer.current = window.setInterval(() => setSeconds(Math.floor((Date.now() - startedAt.current) / 1000)), 250)
      autoStop.current = window.setTimeout(() => stop(), MAX_AUDIO_SECONDS * 1000)

      const Ctor: AudioContextCtor | undefined = window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextCtor }).webkitAudioContext
      if (Ctor) {
        const ctx = new Ctor()
        audioContext.current = ctx
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 512
        ctx.createMediaStreamSource(media).connect(analyser)
        const data = new Uint8Array(analyser.fftSize)
        const tick = () => {
          analyser.getByteTimeDomainData(data)
          setLevel(rmsLevel(data))
          frame.current = requestAnimationFrame(tick)
        }
        tick()
      }
    } catch (error) {
      release()
      callbacks.current.onProblem(microphoneErrorMessage(error))
    } finally {
      starting.current = false
    }
  }, [release, stop])

  useEffect(
    () => () => {
      cancelled.current = true
      session.current += 1
      const active = recorder.current
      if (active && active.state !== "inactive") active.stop()
      else release()
    },
    [release],
  )

  return { recording, level, seconds, start, stop, cancel }
}
