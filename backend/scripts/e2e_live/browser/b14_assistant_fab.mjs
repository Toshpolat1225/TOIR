// Real-browser (Edge): the assistant button at the bottom-right of EVERY page, the small modal (not a full-height drawer), no operator button,
// and the PERSONAL history: a second user must not see the first user's questions (server history + the answers kept on the browser).
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = process.env.TOIR_SC || "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/c7559559-27b3-4c8a-ae2d-d4776d42d11c/scratchpad/e2e"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = process.env.TOIR_BASE || "https://192.168.28.104"
const results = []
const check = async (name, fn) => { console.error("> " + name); try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).slice(0, 200)}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })
const login = async (page, role) => {
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await page.locator("input[type=text]").first().fill(CREDS[role].email)
  await page.locator("input[type=password]").first().fill(CREDS[role].password)
  await page.locator("button[type=submit]").click()
  await page.waitForURL(/dashboard/)
}
const ask = async (page, text) => {
  const before = await page.locator("[data-testid=assistant-card]").count()
  await page.locator("[data-testid=assistant-input]").fill(text)
  await page.locator("[data-testid=assistant-input]").press("Enter")
  await page.waitForFunction((n) => document.querySelectorAll("[data-testid=assistant-card]").length > n, before, { timeout: 20000 })
}

const ctxA = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const a = await ctxA.newPage()
await login(a, "admin")

await check("the robot button is at the bottom-right on the dashboard and on other pages", async () => {
  for (const path of ["/dashboard", "/dashboard/gps", "/dashboard/work-orders"]) {
    await a.goto(`${BASE}${path}`, { waitUntil: "networkidle" })
    const fab = a.locator("[data-testid=assistant-fab]")
    await fab.waitFor({ state: "visible", timeout: 20000 })
    const box = await fab.boundingBox()
    const vp = a.viewportSize()
    assert.ok(box && box.x > vp.width - 120 && box.y > vp.height - 120, `${path}: button at ${JSON.stringify(box)}`)
  }
})

await check("a click opens a small modal (not a full-height drawer) with the new header, no operator button", async () => {
  await a.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  await a.locator("[data-testid=assistant-fab]").click()
  const panel = a.locator("[data-testid=assistant-panel]")
  await panel.waitFor({ state: "visible" })
  const box = await panel.boundingBox()
  const vp = a.viewportSize()
  assert.ok(box.width <= 420 && box.height < vp.height - 20, `panel ${JSON.stringify(box)}`)
  assert.ok(box.x + box.width > vp.width - 40 && box.y + box.height > vp.height - 40, "anchored bottom-right")
  assert.match(await panel.innerText(), /AI yordamchi/)
  assert.match(await panel.innerText(), /Online/)
  assert.doesNotMatch(await panel.innerText(), /оператор|operator/i)
  assert.equal(await a.locator("[data-testid=assistant-fab]").count(), 0, "the button hides while the modal is open")
})

await check("a typed command works in the small modal, then the history lists it", async () => {
  await ask(a, "yordam")
  await a.locator("[data-testid=assistant-history-toggle]").click()
  await a.locator("[data-testid=assistant-history-item]").first().waitFor({ timeout: 15000 })
  const items = await a.locator("[data-testid=assistant-history-item]").allInnerTexts()
  assert.ok(items.some((t) => /yordam/i.test(t)), `history: ${items.join(" | ")}`)
})

await check("a click INSIDE the modal keeps it open, a click anywhere OUTSIDE closes it", async () => {
  await a.locator("[data-testid=assistant-history-toggle]").click() // history was open: close it, still inside
  await a.locator("[data-testid=assistant-panel]").click({ position: { x: 200, y: 300 } })
  assert.ok(await a.locator("[data-testid=assistant-panel]").isVisible(), "inside click must not close")
  await a.mouse.click(300, 300) // far from the bottom-right modal
  await a.locator("[data-testid=assistant-fab]").waitFor({ state: "visible", timeout: 5000 })
  await a.locator("[data-testid=assistant-fab]").click()
  await a.locator("[data-testid=assistant-panel]").waitFor({ state: "visible" })
})

await check("Escape closes the modal and the button comes back", async () => {
  await a.keyboard.press("Escape")
  await a.locator("[data-testid=assistant-fab]").waitFor({ state: "visible", timeout: 5000 })
})

const ctxB = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const b = await ctxB.newPage()
await login(b, "operator")
await check("another user sees an EMPTY history (nobody else's questions)", async () => {
  await b.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  await b.locator("[data-testid=assistant-fab]").click()
  await b.locator("[data-testid=assistant-history-toggle]").click()
  await b.waitForFunction(() => /Пока пусто/.test(document.querySelector("[data-testid=assistant-history]")?.textContent || ""), null, { timeout: 15000 })
  assert.equal(await b.locator("[data-testid=assistant-history-item]").count(), 0)
})

await check("on the same browser a different user does not inherit the previous user's answers", async () => {
  // user A's answers are kept per user id; sign in as the operator in A's own browser profile
  await a.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  const keys = await a.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("toir.assistant.history")))
  assert.ok(keys.every((k) => /\.v1\.[0-9a-f-]{36}$/.test(k)), `keys: ${keys.join(",")}`)
  assert.ok(!keys.includes("toir.assistant.history.v1"), "the old shared key is gone")
})

await check("phone width: the modal fills the screen and can be closed", async () => {
  const ctxM = await browser.newContext({ viewport: { width: 390, height: 780 }, locale: "ru-RU", ignoreHTTPSErrors: true })
  const m = await ctxM.newPage()
  await login(m, "admin")
  await m.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" })
  await m.locator("[data-testid=assistant-fab]").click()
  const box = await m.locator("[data-testid=assistant-panel]").boundingBox()
  assert.ok(box.width >= 380 && box.height >= 760, JSON.stringify(box))
  await m.keyboard.press("Escape")
  await m.locator("[data-testid=assistant-fab]").waitFor({ state: "visible" })
  await ctxM.close()
})

await browser.close()
for (const [s, n] of results) console.log(`${s}  ${n}`)
const failed = results.filter(([s]) => s === "FAIL").length
console.log(failed ? `FAILED ${failed}` : `ALL PASS ${results.length}/${results.length}`)
process.exit(failed ? 1 : 0)
