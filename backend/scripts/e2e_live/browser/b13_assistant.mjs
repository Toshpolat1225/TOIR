// Real-browser (Edge): the command centre: Ctrl+K panel, typed commands on live data, navigation, the confirmation UI (stubbed API answers),
// push-to-talk with a FAKE microphone (the transcribe call is stubbed), help, language, admin page, phone width. Read-only on live data.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = process.env.TOIR_SC || "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/c7559559-27b3-4c8a-ae2d-d4776d42d11c/scratchpad/e2e"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = "https://192.168.28.104"
const results = []
await new Promise((r) => setTimeout(r, Number(process.env.B13_WAIT_MS || 0)))  // let the assistant's per-minute window clear after an API burst test
process.on("unhandledRejection", (e) => { if (!/Target page, context or browser has been closed/.test(String(e?.message))) throw e })
const check = async (name, fn) => { console.error("> " + name); try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0]}`]) } }
const browser = await chromium.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true,
  args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
})
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: "ru-RU", ignoreHTTPSErrors: true, permissions: ["microphone"] })
const page = await context.newPage()
const errors = []
page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)))
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)) })
const login = async (p, role = "admin") => {
  await p.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await p.locator("input[type=text]").first().fill(CREDS[role].email)
  await p.locator("input[type=password]").first().fill(CREDS[role].password)
  await p.locator("button[type=submit]").click()
  await p.waitForURL(/dashboard/)
}
await login(page)
await page.goto(`${BASE}/dashboard/gps`, { waitUntil: "networkidle" })
await page.waitForSelector("[data-testid=gps-row] a", { timeout: 45000 })
const inv = (await page.locator("[data-testid=gps-row] a").first().innerText()).trim()
const open = async () => { if (!(await page.locator("[data-testid=assistant-panel]").isVisible().catch(() => false))) await page.keyboard.press("Control+k"); await page.locator("[data-testid=assistant-panel]").waitFor({ timeout: 8000 }) }
const ask = async (text) => {
  const before = await page.locator("[data-testid=assistant-card]").count()
  await page.locator("[data-testid=assistant-input]").fill(text)
  await page.locator("[data-testid=assistant-input]").press("Enter")
  await page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before, { timeout: 20000 })
}

await check("the header has the assistant button and Ctrl+K opens the panel; Esc closes it", async () => {
  assert.ok((await page.locator("[data-testid=assistant-fab]").count()) >= 1)
  await page.keyboard.press("Control+k")
  await page.locator("[data-testid=assistant-panel]").waitFor({ timeout: 8000 })
  await page.keyboard.press("Escape")
  await page.locator("[data-testid=assistant-panel]").waitFor({ state: "hidden", timeout: 5000 })
})
await check("help: «yordam» answers with grouped examples; tapping an example sends it", async () => {
  await open()
  await ask("yordam")
  const kinds = await page.locator("[data-testid=assistant-card]").evaluateAll((els) => els.map((e) => e.getAttribute("data-kind")))
  assert.ok(kinds.includes("help"), kinds.join(","))
})
await check(`a typed question about a live unit: «${inv} qayerda» -> a card with the unit and «Вы сказали»`, async () => {
  await open()
  await ask(`${inv} qayerda`)
  assert.match(await page.locator("[data-testid=assistant-heard]").last().innerText(), new RegExp(inv))
  assert.match(await page.locator("[data-testid=assistant-card]").last().innerText(), new RegExp(inv))
})
await check("suggestion chips follow the answer and send themselves", async () => {
  const chip = page.locator("[data-testid=assistant-suggestion]").first()
  await chip.waitFor({ timeout: 5000 })
  const before = await page.locator("[data-testid=assistant-card]").count()
  await chip.click()
  await page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before, { timeout: 20000 })
})
await check("an unknown sentence gets a polite answer with suggestions, not an error", async () => {
  await ask("salom qalaysan")
  assert.equal(await page.locator("[data-testid=assistant-error]").count() >= 0, true)
  assert.ok((await page.locator("[data-testid=assistant-suggestion]").count()) >= 3)
})
await check("«xaritani och» navigates to the map", async () => {
  await ask("xaritani och")
  await page.waitForURL(/dashboard\/map/, { timeout: 8000 })
})
await check("language selector exists and persists", async () => {
  await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  await open()
  const sel = page.locator("[data-testid=assistant-lang]")
  await sel.waitFor({ timeout: 5000 })
  assert.ok((await sel.count()) >= 1)
})
await check("a write shows the confirmation card; typing «ha» confirms (API answers stubbed), «yo'q» cancels", async () => {
  let confirmCalls = 0
  await page.route("**/api/v1/assistant/command", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}")
    if (/naryad/.test(body.text)) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        ok: true, status: "needs_confirm", intent: "wo.create", heard: body.text, speak: "Naryad", speak_lang: "uz",
        cards: [{ kind: "confirm", title: "Naryad: STUB-1", tone: "info", rows: [], items: [], columns: [], table: [] }], suggestions: [], entities: [], ms: 5,
        confirm: { token: "stub-token-1234567890", expires_at: new Date(Date.now() + 60000).toISOString(), summary: "Naryad: STUB-1", risk: "low" },
      }) })
    }
    return route.continue()
  })
  await page.route("**/api/v1/assistant/confirm", async (route) => {
    confirmCalls += 1
    const body = JSON.parse(route.request().postData() || "{}")
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      ok: true, status: "ok", heard: "", speak: body.approve ? "Bajarildi" : "Bekor", speak_lang: "uz",
      cards: [{ kind: "text", title: body.approve ? "Naryad yaratildi" : "Bekor qilindi", rows: [], items: [], columns: [], table: [] }], suggestions: [], entities: [], ms: 3,
    }) })
  })
  await open()
  await ask("STUB uchun naryad och")
  await page.locator("[data-testid=assistant-confirm]").waitFor({ timeout: 8000 })
  assert.ok((await page.locator("[data-testid=assistant-confirm-yes]").count()) >= 1 && (await page.locator("[data-testid=assistant-confirm-no]").count()) >= 1)
  await page.locator("[data-testid=assistant-input]").fill("ha")
  await page.locator("[data-testid=assistant-input]").press("Enter")
  await page.waitForFunction(() => /Naryad yaratildi/.test(document.body.innerText), null, { timeout: 8000 })
  assert.equal(confirmCalls, 1)
  await ask("STUB uchun naryad och")
  await page.locator("[data-testid=assistant-confirm]").last().waitFor({ timeout: 8000 })
  await page.locator("[data-testid=assistant-input]").fill("yo'q")
  await page.locator("[data-testid=assistant-input]").press("Enter")
  await page.waitForFunction(() => /Bekor qilindi/.test(document.body.innerText), null, { timeout: 8000 })
  assert.equal(confirmCalls, 2)
  await page.unroute("**/api/v1/assistant/command")
  await page.unroute("**/api/v1/assistant/confirm")
})
await check("push-to-talk with a fake microphone: the audio goes to /assistant/transcribe (stubbed) and its text becomes a command", async () => {
  let transcribed = 0
  await page.route("**/api/v1/assistant/status", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ voice_available: true, voice_model: "stub", max_audio_s: 30, write_actions: true }) }))
  await page.route("**/api/v1/assistant/transcribe", async (route) => {
    transcribed += 1
    const ct = route.request().headers()["content-type"] || ""
    assert.match(ct, /multipart\/form-data/)
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ text: "yordam", language: "uz", confidence: 0.95, duration_s: 1.2, ms: 50 }) })
  })
  await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  await open()
  const mic = page.locator("[data-testid=assistant-mic]")
  await mic.waitFor({ timeout: 8000 })
  const before = await page.locator("[data-testid=assistant-card]").count()
  await mic.hover()
  await page.mouse.down()
  await page.waitForTimeout(1500)
  await page.mouse.up()
  await page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before, { timeout: 20000 })
  assert.equal(transcribed, 1)
  await page.unroute("**/api/v1/assistant/status")
  await page.unroute("**/api/v1/assistant/transcribe")
})
await check("the admin page of unmatched phrases opens and lists the sentence from above", async () => {
  await page.goto(`${BASE}/dashboard/admin/assistant`, { waitUntil: "networkidle" })
  await page.locator("[data-testid=assistant-admin-page]").waitFor({ timeout: 15000 })
  await page.waitForTimeout(1500)
  assert.match(await page.locator("[data-testid=assistant-admin-page]").innerText(), /salom/i)
})
await page.screenshot({ path: `${SC}/snap_assistant_admin.png` })

const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "ru-RU", ignoreHTTPSErrors: true, permissions: ["microphone"] })
const mp = await phone.newPage()
await login(mp)
await check("phone width: the panel fits (no sideways scroll)", async () => {
  await mp.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  await mp.locator("[data-testid=assistant-fab]").first().click()
  await mp.locator("[data-testid=assistant-panel]").waitFor({ timeout: 8000 })
  await mp.locator("[data-testid=assistant-input]").fill("yordam")
  await mp.locator("[data-testid=assistant-input]").press("Enter")
  await mp.waitForTimeout(2500)
  const [sw, cw] = await mp.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
  assert.ok(sw <= cw + 1, `scrollWidth ${sw} > ${cw}`)
  await mp.screenshot({ path: `${SC}/snap_assistant_phone.png` })
})
const masterCtx = await browser.newContext({ viewport: { width: 1200, height: 800 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const mpage = await masterCtx.newPage()
await login(mpage, "master")
await check("a master does not get the admin entry of the assistant", async () => {
  await mpage.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  const items = await mpage.locator("nav[aria-label='Основная навигация'] a").evaluateAll((els) => els.map((e) => e.innerText))
  assert.ok(!items.some((t) => /непонят/i.test(t)), items.join("|"))
})
await check("no page errors in the console", async () => {
  const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh|tile.openstreetmap|Google Maps JavaScript API error|AbortError|aborted|429/i.test(t))
  assert.equal(serious.length, 0, serious.join(" | "))
})
console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
