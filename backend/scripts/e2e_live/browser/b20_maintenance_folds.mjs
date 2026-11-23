// Real-browser (Edge): /dashboard/maintenance — the secondary blocks are collapsible folds, the Gantt/table comes up higher,
// and the «средний суточный пробег» card opens a detailed calculation. Needs a temporary ZZTEST account in zztest_creds.json (key "admin").
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
const errors = []
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)))
await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await page.locator("input[type=text]").first().fill(CREDS.admin.email)
await page.locator("input[type=password]").first().fill(CREDS.admin.password)
await page.locator("button[type=submit]").click()
await page.waitForURL(/dashboard/)
await page.goto(`${BASE}/dashboard/maintenance`, { waitUntil: "networkidle" })
await page.waitForTimeout(3000)
await page.screenshot({ path: `${SC}/b20_collapsed.png` })

await check("three folds exist and start collapsed", async () => {
  for (const id of ["filters", "summary"]) {
    assert.equal(await page.getByTestId(`fold-${id}`).count(), 1, id)
    assert.equal(await page.getByTestId(`fold-${id}`).locator("button").first().getAttribute("aria-expanded"), "false", id)
  }
  assert.equal(await page.getByTestId("avg-daily-mileage").count(), 1)
})
await check("opening «Фильтры» shows the type and work-kind chips", async () => {
  await page.getByTestId("fold-filters").locator("button").first().click()
  await page.waitForTimeout(300)
  assert.ok(await page.getByTestId("fold-filters").getByText("Виды работ:").count() > 0)
})
await check("opening «Показатели» shows the cards; choice is remembered after reload", async () => {
  await page.getByTestId("fold-summary").locator("button").first().click()
  await page.waitForTimeout(300)
  assert.ok((await page.getByTestId("fold-summary").innerText()).length > 50)
  await page.reload({ waitUntil: "networkidle" })
  await page.waitForTimeout(2000)
  assert.equal(await page.getByTestId("fold-summary").locator("button").first().getAttribute("aria-expanded"), "true")
})
await check("avg daily mileage: card opens a calculation dialog with steps and a table", async () => {
  await page.getByTestId("avg-daily-mileage").locator("button").first().click()
  await page.waitForTimeout(1500)
  assert.ok(await page.getByTestId("avg-daily-card").count() > 0)
  await page.getByTestId("avg-daily-card").first().click()
  await page.getByTestId("avg-daily-detail").waitFor()
  await page.waitForTimeout(1500)
  const text = await page.getByTestId("avg-daily-detail").innerText()
  assert.ok(/Большой список/.test(text) && /Малый список/.test(text) && /Результат/.test(text), text.slice(0, 200))
  await page.screenshot({ path: `${SC}/b20_detail.png` })
  await page.keyboard.press("Escape")
  await page.waitForTimeout(300)
  assert.equal(await page.getByTestId("avg-daily-detail").count(), 0)
})
await check("the manual «Расчётная средняя суточная наработка» form is gone; «Без прогноза» is at the very bottom", async () => {
  assert.equal(await page.getByText("Расчётная средняя суточная наработка").count(), 0)
  const y = await page.evaluate(() => {
    const d = [...document.querySelectorAll("details")].find((e) => /Без прогноза/.test(e.textContent || ""))
    const t = document.querySelector("table")
    return d && t ? { d: d.getBoundingClientRect().top + scrollY, t: t.getBoundingClientRect().top + scrollY } : null
  })
  assert.ok(y && y.d > y.t, JSON.stringify(y))
})
await check("no page errors", async () => assert.deepEqual(errors, []))
await browser.close()
for (const [s, n] of results) console.log(`${s}  ${n}`)
const failed = results.filter(([s]) => s === "FAIL").length
console.log(failed ? `FAILED ${failed}` : `ALL PASS ${results.length}/${results.length}`)
process.exit(failed ? 1 : 0)
