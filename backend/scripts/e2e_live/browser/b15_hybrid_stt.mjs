// Real-browser (Edge): HYBRID speech recognition. A FAKE browser SpeechRecognition (injected) and a FAKE microphone; /assistant/transcribe is stubbed.
// 1) the browser hears the sentence -> the command runs and the audio is NOT uploaded. 2) the browser fails (network) -> the recording goes to Whisper.
// 3) «Только Whisper» -> the browser recogniser is never started. 4) «Только браузер» + failure -> a clear message, no upload. Read-only on live data.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = process.env.TOIR_SC || "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/c7559559-27b3-4c8a-ae2d-d4776d42d11c/scratchpad/e2e"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = process.env.TOIR_BASE || "https://192.168.28.104"
const results = []
await new Promise((r) => setTimeout(r, Number(process.env.B15_WAIT_MS || 0)))
const check = async (name, fn) => { console.error("> " + name); try { await fn() ; results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0].slice(0, 220)}`]) } }
const browser = await chromium.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true,
  args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
})
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: "ru-RU", ignoreHTTPSErrors: true, permissions: ["microphone"] })
await context.addInitScript(() => {
  window.__sr = { mode: "text", starts: 0 }
  class FakeSR {
    constructor() { this.lang = ""; this.onresult = null; this.onerror = null; this.onend = null; this._t = null }
    start() {
      window.__sr.starts += 1
      window.__sr.lang = this.lang
      const m = window.__sr.mode
      this._t = setTimeout(() => {
        if (m === "text") this.onresult && this.onresult({ results: [Object.assign([{ transcript: "yordam", confidence: 0.92 }], { isFinal: true })] })
        else if (m === "network") { this.onerror && this.onerror({ error: "network" }); this.onend && this.onend() }
      }, 400)
    }
    stop() { clearTimeout(this._t); setTimeout(() => this.onend && this.onend(), 50) }
    abort() { clearTimeout(this._t); this.onend && this.onend() }
  }
  window.SpeechRecognition = FakeSR
  window.webkitSpeechRecognition = FakeSR
})
const login = async (p) => {
  await p.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await p.locator("input[type=text]").first().fill(CREDS.admin.email)
  await p.locator("input[type=password]").first().fill(CREDS.admin.password)
  await p.locator("button[type=submit]").click()
  await p.waitForURL(/dashboard/)
}
const first = await context.newPage()
await login(first)
await first.close()

const session = async (mode, pref) => {
  const page = await context.newPage()
  let transcribed = 0
  await page.route("**/api/v1/assistant/status", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ voice_available: true, voice_model: "stub", max_audio_s: 30, write_actions: true, browser_stt: true }) }))
  await page.route("**/api/v1/assistant/transcribe", (route) => { transcribed += 1; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ text: "yordam", language: "ru", confidence: 0.95, duration_s: 1.2, ms: 40 }) }) })
  await page.addInitScript(([m, p]) => { window.__sr.mode = m; try { if (p) localStorage.setItem("toir.assistant.stt.v1", p) } catch {} }, [mode, pref])
  await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  await page.locator("[data-testid=assistant-fab]").click()
  const mic = page.locator("[data-testid=assistant-mic]")
  await mic.waitFor({ timeout: 10000 })
  const press = async () => { await mic.hover(); await page.mouse.down(); await page.waitForTimeout(1300); await page.mouse.up() }
  return { page, press, transcribed: () => transcribed, starts: () => page.evaluate(() => window.__sr.starts) }
}
const cards = (page) => page.locator("[data-testid=assistant-card]").count()

await check("the browser hears the sentence: the command runs, the audio is NOT uploaded to Whisper", async () => {
  const s = await session("text")
  const before = await cards(s.page)
  await s.press()
  await s.page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before, { timeout: 20000 })
  assert.equal(s.transcribed(), 0, "no upload expected")
  assert.equal(await s.starts(), 1)
  assert.equal(await s.page.evaluate(() => window.__sr.lang), "ru-RU")
  await s.page.close()
})

await check("the browser fails (network): the SAME recording goes to Whisper and the command still runs", async () => {
  const s = await session("network")
  const before = await cards(s.page)
  await s.press()
  await s.page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before, { timeout: 20000 })
  assert.equal(s.transcribed(), 1)
  // after a hard error the browser recogniser is not tried again in this session
  const startsAfterFirst = await s.starts()
  await s.page.waitForTimeout(500)
  const before2 = await cards(s.page)
  await s.press()
  await s.page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before2, { timeout: 20000 })
  assert.equal(s.transcribed(), 2)
  assert.equal(await s.starts(), startsAfterFirst, "browser recogniser must not restart after a network error")
  await s.page.close()
})

await check("«Только Whisper»: the browser recogniser is never started", async () => {
  const s = await session("text", "whisper")
  const before = await cards(s.page)
  await s.press()
  await s.page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before, { timeout: 20000 })
  assert.equal(await s.starts(), 0)
  assert.equal(s.transcribed(), 1)
  await s.page.close()
})

await check("«Только браузер» and the browser hears nothing: a clear message, nothing uploaded", async () => {
  const s = await session("silent", "browser")
  await s.press()
  await s.page.waitForFunction(() => /Браузер не распознал/.test(document.body.innerText), null, { timeout: 15000 })
  assert.equal(s.transcribed(), 0)
  await s.page.close()
})

await check("the recogniser selector exists and is saved", async () => {
  const s = await session("text")
  const sel = s.page.locator("[data-testid=assistant-stt]")
  await sel.selectOption("whisper")
  assert.equal(await s.page.evaluate(() => localStorage.getItem("toir.assistant.stt.v1")), "whisper")
  await s.page.close()
})

await browser.close()
for (const [s, n] of results) console.log(`${s}  ${n}`)
const failed = results.filter(([s]) => s === "FAIL").length
console.log(failed ? `FAILED ${failed}` : `ALL PASS ${results.length}/${results.length}`)
process.exit(failed ? 1 : 0)
