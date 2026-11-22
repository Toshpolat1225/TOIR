// Real-browser (Edge): GPS «Вагоны (по составу)» and the wagon page have «С [дата] по [дата]» pickers (Russian) that drive the requests.
// Needs a temporary ZZTEST account in zztest_creds.json (key "admin" = any role that may open GPS).
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"
const SC = process.env.TOIR_SC || "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/c7559559-27b3-4c8a-ae2d-d4776d42d11c/scratchpad/e2e"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = process.env.TOIR_BASE || "https://192.168.28.104"
const results = []
const check = async (name, fn) => { console.error("> " + name); try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0].slice(0, 300)}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const page = await context.newPage()
const urls = []
page.on("request", (r) => { if (r.url().includes("/gps/wagons")) urls.push(r.url()) })
const errors = []
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)))
await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await page.locator("input[type=text]").first().fill(CREDS.admin.email)
await page.locator("input[type=password]").first().fill(CREDS.admin.password)
await page.locator("button[type=submit]").click()
await page.waitForURL(/dashboard/)
await page.goto(`${BASE}/dashboard/gps/wagons`, { waitUntil: "networkidle" })
await page.waitForTimeout(2000)
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const dayAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return iso(d) }

await check("list page shows «С» and «по» date pickers", async () => {
  assert.equal(await page.getByTestId("period-from").count(), 1)
  assert.equal(await page.getByTestId("period-to").count(), 1)
  assert.equal(await page.getByTestId("period-to").inputValue(), iso(new Date()))
})
await page.screenshot({ path: `${SC}/b18_list.png` })
await check("choosing a start date sends date_from / date_to to the server", async () => {
  urls.length = 0
  await page.getByTestId("period-from").fill(dayAgo(3))
  await page.waitForTimeout(2500)
  const u = urls.find((x) => x.includes("date_from=")) || ""
  assert.ok(u.includes(`date_from=${dayAgo(3)}`), u)
})
await check("«3 дней» window is accepted (200) and rows still render", async () => {
  assert.ok(await page.locator("tbody tr").count() > 0)
})
let detailUrl = ""
await check("open a wagon: its page has the same pickers", async () => {
  await page.locator("[data-testid=wagon-row] a[href*=\"/gps/wagons/\"]").first().click()
  await page.waitForURL(/gps\/wagons\//, { timeout: 15000 })
  detailUrl = page.url()
  await page.getByTestId("period-from").waitFor()
})
await check("wagon page: changing «С» reloads with date_from", async () => {
  urls.length = 0
  await page.getByTestId("period-from").fill(dayAgo(5))
  await page.waitForTimeout(2500)
  assert.ok(urls.some((x) => x.includes(`date_from=${dayAgo(5)}`)), urls.join("\n"))
  assert.ok(await page.getByTestId("wagon-detail-page").count() === 1)
})
await page.screenshot({ path: `${SC}/b18_detail.png` })
await check("no page errors", async () => assert.deepEqual(errors, []))
await browser.close()
for (const [s, n] of results) console.log(`${s}  ${n}`)
const failed = results.filter(([s]) => s === "FAIL").length
console.log(failed ? `FAILED ${failed}` : `ALL PASS ${results.length}/${results.length}`)
process.exit(failed ? 1 : 0)
