import assert from "node:assert/strict"
import { test } from "node:test"

import {
  appendHistory,
  assetIdFromPath,
  audioFileName,
  buildContext,
  detectConfirmReply,
  formatCountdown,
  HISTORY_LIMIT,
  mapAssistantError,
  microphoneErrorMessage,
  microphoneProblem,
  needsReview,
  nextLastEntity,
  normalizeLang,
  normalizeUtterance,
  openConfirmation,
  parseHistory,
  patchHistory,
  pickRecorderMime,
  pickVoice,
  rmsLevel,
  secondsLeft,
  shouldSpeak,
  speechText,
  transcribeLanguage,
  type AssistantCommandOut,
  type HistoryEntry,
} from "./assistant.ts"

const UUID = "3f2b8c1e-4d5a-4b6c-9e7f-0a1b2c3d4e5f"

const out = (over: Partial<AssistantCommandOut> = {}): AssistantCommandOut => ({
  ok: true, status: "ok", heard: "x", speak_lang: "ru", cards: [], suggestions: [], entities: [], ms: 5, ...over,
})
const entry = (id: string, over: Partial<HistoryEntry> = {}): HistoryEntry => ({ id, at: "2026-11-18T10:00:00Z", query: "q", source: "text", ...over })

test("normalizeUtterance folds apostrophes, punctuation and case", () => {
  assert.equal(normalizeUtterance("  Yo‘q!  "), "yo'q")
  assert.equal(normalizeUtterance("«Да», подтверждаю."), "да подтверждаю")
})

test("detectConfirmReply: yes and no in Uzbek and Russian, real commands are not answers", () => {
  for (const t of ["ha", "Xa", "tasdiqlayman", "mayli", "ok", "да", "Подтверждаю", "давай", "yes", "ha, tasdiqlayman", "да пожалуйста"]) assert.equal(detectConfirmReply(t), "yes", t)
  for (const t of ["yo'q", "yoq", "bekor", "bekor qil", "Отмена", "нет", "no", "cancel", "yo‘q"]) assert.equal(detectConfirmReply(t), "no", t)
  for (const t of ["37919 qayerda", "ha yo'q", "naryad och", "", "да нет", "открой карту"]) assert.equal(detectConfirmReply(t), null, t)
})

test("needsReview: a low-confidence phrase is sent anyway; only an empty / 1-2 letter result is held back, except a yes/no to an open confirmation", () => {
  assert.equal(needsReview("37919 qayerda", 0.9), false)
  assert.equal(needsReview("37919 qayerda", 0.4), false)
  assert.equal(needsReview("37919 qayerda", null), false)
  assert.equal(needsReview("xarita", 0.3), false)
  assert.equal(needsReview("ha", 0.9), true)
  assert.equal(needsReview("ha", 0.3, true), false)
  assert.equal(needsReview("открой", 0.9, true), false)
  assert.equal(needsReview("  ", 0.9), true)
})

test("assetIdFromPath reads the asset of the open GPS pages only", () => {
  assert.equal(assetIdFromPath(`/dashboard/gps/${UUID}`), UUID)
  assert.equal(assetIdFromPath(`/dashboard/gps/wagons/${UUID}/`), UUID)
  assert.equal(assetIdFromPath(`/dashboard/gps/${UUID.toUpperCase()}`), UUID)
  assert.equal(assetIdFromPath("/dashboard/gps/wagons/gtk-1186"), null)
  assert.equal(assetIdFromPath("/dashboard/gps/wagons"), null)
  assert.equal(assetIdFromPath("/dashboard/gps"), null)
  assert.equal(assetIdFromPath("/dashboard/map"), null)
  assert.equal(assetIdFromPath(null), null)
})

test("buildContext carries the page, the page asset and the last entity", () => {
  const last = { kind: "asset" as const, id: UUID, label: "37919", asset_type: "locomotive" }
  assert.deepEqual(buildContext(`/dashboard/gps/${UUID}`, last), { page: `/dashboard/gps/${UUID}`, asset_id: UUID, last_entity: last, dialog: null })
  assert.deepEqual(buildContext("/dashboard/map", null), { page: "/dashboard/map", asset_id: null, last_entity: null, dialog: null })
  assert.deepEqual(buildContext("/dashboard/map", null, { intent: "wo.create", base: "naryad och" }).dialog, { intent: "wo.create", base: "naryad och" })
  assert.equal(buildContext("/x".repeat(300), null).page?.length, 200)
})

test("nextLastEntity: the newest answer wins, an answer without entities keeps the previous one", () => {
  const a = { kind: "asset" as const, id: "1", label: "A" }
  const b = { kind: "train" as const, id: "2", label: "B" }
  assert.equal(nextLastEntity(a, { entities: [b] }), b)
  assert.equal(nextLastEntity(a, { entities: [] }), a)
  assert.equal(nextLastEntity(null, { entities: [] }), null)
})

test("pickVoice prefers a local voice of the wanted language and returns null without one", () => {
  const voices = [
    { lang: "en-US", name: "en", localService: true },
    { lang: "ru-RU", name: "ru-net", localService: false },
    { lang: "ru_RU", name: "ru-local", localService: true },
  ]
  assert.equal(pickVoice(voices, "ru")?.name, "ru-local")
  assert.equal(pickVoice(voices, "uz"), null)
  assert.equal(pickVoice([{ lang: "uz-UZ", name: "uz" }], "uz")?.name, "uz")
  assert.equal(pickVoice([], "ru"), null)
})

test("speechText strips markup and cuts long text at a sentence end; shouldSpeak needs the toggle, a voice and a text", () => {
  assert.equal(speechText("**Лок 37919** — на станции `A`"), "Лок 37919 — на станции A")
  const long = "Первое предложение. ".repeat(40)
  const cut = speechText(long, 100)
  assert.ok(cut.length <= 100 && cut.endsWith("."), cut)
  assert.equal(speechText(null), "")
  assert.equal(shouldSpeak(true, { speak: "Привет" }, true), true)
  assert.equal(shouldSpeak(false, { speak: "Привет" }, true), false)
  assert.equal(shouldSpeak(true, { speak: "Привет" }, false), false)
  assert.equal(shouldSpeak(true, { speak: "  " }, true), false)
  assert.equal(shouldSpeak(true, null, true), false)
})

test("pickRecorderMime takes the first supported type, survives a throwing check; audioFileName follows the type", () => {
  assert.equal(pickRecorderMime((m) => m === "audio/ogg;codecs=opus"), "audio/ogg;codecs=opus")
  assert.equal(pickRecorderMime(() => true), "audio/webm;codecs=opus")
  assert.equal(pickRecorderMime(() => false), undefined)
  assert.equal(pickRecorderMime(() => { throw new Error("x") }), undefined)
  assert.equal(audioFileName("audio/webm;codecs=opus"), "voice.webm")
  assert.equal(audioFileName("audio/ogg"), "voice.ogg")
  assert.equal(audioFileName("audio/mp4"), "voice.m4a")
  assert.equal(audioFileName(undefined), "voice.webm")
})

test("rmsLevel: silence is 0, loud speech is large, always within 0..1", () => {
  assert.equal(rmsLevel(new Uint8Array(0)), 0)
  assert.equal(rmsLevel(new Uint8Array(64).fill(128)), 0)
  const loud = Uint8Array.from({ length: 64 }, (_, i) => (i % 2 ? 250 : 6))
  assert.equal(rmsLevel(loud), 1)
  const quiet = Uint8Array.from({ length: 64 }, (_, i) => (i % 2 ? 136 : 120))
  assert.ok(rmsLevel(quiet) > 0 && rmsLevel(quiet) < 0.5)
})

test("microphone problems are explained in Russian and point to the text fallback", () => {
  assert.match(microphoneProblem({ secure: false, hasMediaDevices: true, hasRecorder: true }) ?? "", /HTTPS/)
  assert.match(microphoneProblem({ secure: true, hasMediaDevices: false, hasRecorder: true }) ?? "", /не поддерживает/)
  assert.equal(microphoneProblem({ secure: true, hasMediaDevices: true, hasRecorder: true }), null)
  assert.match(microphoneErrorMessage({ name: "NotAllowedError" }), /запрещён/)
  assert.match(microphoneErrorMessage({ name: "NotFoundError" }), /не найден/)
  assert.match(microphoneErrorMessage(new Error("x")), /текстов/)
})

test("mapAssistantError turns statuses and network failures into short Russian messages", () => {
  assert.match(mapAssistantError({ status: 403 }), /прав/)
  assert.match(mapAssistantError({ status: 410 }), /Срок/)
  assert.match(mapAssistantError({ status: 413 }), /30 секунд/)
  assert.match(mapAssistantError({ status: 429 }), /Слишком много/)
  assert.match(mapAssistantError({ status: 503 }), /недоступен/)
  assert.match(mapAssistantError(new TypeError("Failed to fetch")), /Нет связи/)
  assert.equal(mapAssistantError(Object.assign(new Error("Сервер сказал"), { status: 400 })), "Сервер сказал")
  assert.match(mapAssistantError("boom"), /Не удалось/)
})

test("secondsLeft and formatCountdown", () => {
  const now = Date.parse("2026-11-18T10:00:00Z")
  assert.equal(secondsLeft("2026-11-18T10:00:45Z", now), 45)
  assert.equal(secondsLeft("2026-11-18T09:59:00Z", now), 0)
  assert.equal(secondsLeft("not a date", now), 0)
  assert.equal(formatCountdown(45), "0:45")
  assert.equal(formatCountdown(125), "2:05")
  assert.equal(formatCountdown(-3), "0:00")
})

test("history keeps the last 20, survives bad storage and rejects broken entries", () => {
  let list: HistoryEntry[] = []
  for (let i = 0; i < 25; i++) list = appendHistory(list, entry(String(i)))
  assert.equal(list.length, HISTORY_LIMIT)
  assert.equal(list[0].id, "5")
  assert.equal(list[19].id, "24")
  assert.deepEqual(parseHistory(null), [])
  assert.deepEqual(parseHistory("{not json"), [])
  assert.deepEqual(parseHistory('{"a":1}'), [])
  const raw = JSON.stringify([entry("ok", { out: out() }), { id: 5 }, "x", { id: "n", at: "t", query: "q", out: { cards: "no" } }])
  const parsed = parseHistory(raw)
  assert.deepEqual(parsed.map((e) => e.id), ["ok", "n"])
  assert.equal(parsed[0].out?.heard, "x")
  assert.equal(parsed[1].out, null)
  assert.equal(patchHistory(list, "24", { resolved: "approved" })[19].resolved, "approved")
  assert.equal(patchHistory(list, "nope", { resolved: "approved" }).length, HISTORY_LIMIT)
})

test("openConfirmation finds the newest unanswered, unexpired confirmation", () => {
  const now = Date.parse("2026-11-18T10:00:00Z")
  const confirmOut = (sec: number) => out({ status: "needs_confirm", confirm: { token: "t".repeat(12), expires_at: new Date(now + sec * 1000).toISOString(), summary: "s", risk: "low" } })
  assert.equal(openConfirmation([entry("a", { out: confirmOut(30) })], now)?.id, "a")
  assert.equal(openConfirmation([entry("a", { out: confirmOut(-5) })], now), null)
  assert.equal(openConfirmation([entry("a", { out: confirmOut(30), resolved: "approved" })], now), null)
  assert.equal(openConfirmation([entry("a", { out: confirmOut(30) }), entry("b", { out: out() })], now)?.id, "a")
  assert.equal(openConfirmation([entry("a", { out: confirmOut(30), resolved: "cancelled" }), entry("b", { out: confirmOut(30) })], now)?.id, "b")
  assert.equal(openConfirmation([], now), null)
})

test("language helpers", () => {
  assert.equal(normalizeLang("uz"), "uz")
  assert.equal(normalizeLang("de"), "auto")
  assert.equal(normalizeLang(null), "auto")
  assert.equal(transcribeLanguage("auto"), undefined)
  assert.equal(transcribeLanguage("ru"), "ru")
})
