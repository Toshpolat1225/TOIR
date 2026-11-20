import assert from "node:assert/strict"
import { test } from "node:test"

import { browserLang, isHardBrowserError, joinResults, normalizeSttPref, shouldTryBrowser } from "./browser-stt.ts"

test("normalizeSttPref: only the three known values, anything else is «auto»", () => {
  assert.equal(normalizeSttPref("whisper"), "whisper")
  assert.equal(normalizeSttPref("browser"), "browser")
  assert.equal(normalizeSttPref("auto"), "auto")
  assert.equal(normalizeSttPref(null), "auto")
  assert.equal(normalizeSttPref("cloud"), "auto")
})

test("browserLang: Uzbek only when chosen, otherwise Russian", () => {
  assert.equal(browserLang("uz"), "uz-UZ")
  assert.equal(browserLang("ru"), "ru-RU")
  assert.equal(browserLang("auto"), "ru-RU")
})

test("shouldTryBrowser: needs support, the user's internet and the server's permission; «whisper» never tries it", () => {
  const ok = { supported: true, online: true, allowed: true }
  assert.equal(shouldTryBrowser("auto", ok), true)
  assert.equal(shouldTryBrowser("browser", ok), true)
  assert.equal(shouldTryBrowser("whisper", ok), false)
  assert.equal(shouldTryBrowser("auto", { ...ok, online: false }), false) // offline: straight to Whisper
  assert.equal(shouldTryBrowser("auto", { ...ok, supported: false }), false)
  assert.equal(shouldTryBrowser("auto", { ...ok, allowed: false }), false) // closed-circuit policy
})

test("joinResults: joins the final parts, keeps the lowest confidence, ignores empty and interim parts", () => {
  const r = (transcript: string, confidence: number, isFinal = true) => Object.assign([{ transcript, confidence }], { isFinal })
  assert.deepEqual(joinResults([r("открой", 0.9), r("карту", 0.7)]), { text: "открой карту", confidence: 0.7 })
  assert.deepEqual(joinResults([r("  найди   вагон 8121 ", 0)]), { text: "найди вагон 8121", confidence: null })
  assert.equal(joinResults([r("", 0.9)]), null)
  assert.equal(joinResults([r("черновик", 0.9, false)]), null)
  assert.equal(joinResults([]), null)
})

test("isHardBrowserError: no internet or a blocked service means «use Whisper from now on»", () => {
  assert.equal(isHardBrowserError("network"), true)
  assert.equal(isHardBrowserError("service-not-allowed"), true)
  assert.equal(isHardBrowserError("no-speech"), false)
  assert.equal(isHardBrowserError(undefined), false)
})
