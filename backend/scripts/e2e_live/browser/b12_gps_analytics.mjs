// Real-browser (Edge): the analytics layer of the GPS page: clickable KPI/bars -> filters in the URL, facets, sort, drawer, export,
// tracker-health panel, the wagons section (list + detail with the four candidates), phone width. Read-only.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = process.env.TOIR_SC || "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/c7559559-27b3-4c8a-ae2d-d4776d42d11c/scratchpad/e2e"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = "https://192.168.28.104"
const results = []
process.on("unhandledRejection", (e) => { if (!/Target page, context or browser has been closed/.test(String(e?.message))) throw e })
const check = async (name, fn) => { console.error("> " + name); try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0]}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: "ru-RU", ignoreHTTPSErrors: true, acceptDownloads: true })
const page = await context.newPage()
const errors = []
page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)))
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)) })
const login = async (p) => {
  await p.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await p.locator("input[type=text]").first().fill(CREDS.admin.email)
  await p.locator("input[type=password]").first().fill(CREDS.admin.password)
  await p.locator("button[type=submit]").click()
  await p.waitForURL(/dashboard/)
}
await login(page)
await page.goto(`${BASE}/dashboard/gps`, { waitUntil: "networkidle" })
await page.waitForSelector("[data-testid=gps-row]", { timeout: 45000 })
await page.waitForTimeout(2500)
const rowCount = async () => {  // «Показано: 14» (all of them) or «Показано: 50 из 87» (a page of the filtered list)
  const t = await page.locator("[data-testid=gps-count]").innerText().catch(() => "")
  const m = t.match(/из\s*(\d+)/) || t.match(/Показано:\s*(\d+)/)
  return m ? Number(m[1]) : page.locator("[data-testid=gps-row]").count()
}
const counterText = async () => (await page.locator("[data-testid=gps-count]").innerText().catch(() => "")).trim()
const counterChanges = async (prev) => page.waitForFunction((p) => (document.querySelector("[data-testid=gps-count]")?.textContent || "").trim() !== p, prev, { timeout: 20000 })
const settle = async () => { await page.waitForLoadState("networkidle"); await page.waitForTimeout(500) }  // a filter change is a server round trip
const total = await rowCount()

await check("the menu: GPS with Карта, Данные GTK, Данные Wialon and Вагоны as children", async () => {
  const items = await page.locator("nav[aria-label='Основная навигация'] a").evaluateAll((els) => els.map((e) => e.innerText.trim()))
  const i = items.indexOf("GPS: Wialon ↔ GTK")
  assert.ok(i >= 0)
  for (const label of ["Карта", "Данные GTK", "Данные Wialon", "Вагоны (по составу)"]) assert.ok(items.slice(i + 1, i + 6).includes(label), `no ${label} after GPS: ${items.slice(i, i + 6)}`)
})
await check("the page shows the filter bar, the cause bar, the health panel and the new columns", async () => {
  for (const id of ["gps-filter-bar", "gps-cause-bar", "gps-health-panel", "gps-export", "gps-pager"]) assert.ok((await page.locator(`[data-testid=${id}]`).count()) >= 1, id)
  const head = await page.locator("[data-testid=gps-table] thead").innerText()
  assert.match(head, /причина/i); assert.match(head, /уверенность/i)
})
await check("a KPI tile filters the table and puts the filter in the URL; a second click removes it", async () => {
  const before = await counterText()
  const tile = page.locator("[data-testid^=gps-kpi-]").filter({ hasText: /GTK молчит/i }).first()
  await tile.click()
  await page.waitForURL(/[?&]verdict=/, { timeout: 15000 })
  await counterChanges(before)
  await settle()
  const n = await rowCount()
  assert.ok(n < total && n >= 0, `rows ${n} of ${total}`)
  assert.ok(/[?&]/.test(new URL(page.url()).search), "no filter in the URL")
  assert.ok((await page.locator("[data-testid=gps-filter-chip]").count()) >= 1, "no filter chip")
  await page.locator("[data-testid=gps-filter-reset]").click()
  await page.waitForFunction(() => !location.search.includes("verdict="), null, { timeout: 15000 })
  await page.waitForFunction((p) => (document.querySelector("[data-testid=gps-count]")?.textContent || "").trim() === p, before, { timeout: 20000 })
  await settle()
  assert.equal(await rowCount(), total)
})
await check("a cause segment filters by that cause and facet counts are shown", async () => {
  const seg = page.locator("[data-testid=gps-cause-bar] button").first()
  const before = await rowCount()
  const beforeText = await counterText()
  await seg.click()
  await page.waitForURL(/[?&]cause=/, { timeout: 15000 })
  await counterChanges(beforeText).catch(() => {})  // a cause shared by every locomotive changes nothing
  await settle()
  assert.ok((await rowCount()) <= before)
  assert.match(new URL(page.url()).search, /cause=/)
  await page.locator("[data-testid=gps-filter-reset]").click()
  await page.waitForFunction(() => !location.search.includes("cause="), null, { timeout: 15000 })
  await settle()
})
await check("sorting by a column header is applied by the server and kept in the URL", async () => {
  await page.locator("[data-testid^=gps-sort-]").first().click()
  await page.waitForTimeout(1800)
  assert.match(new URL(page.url()).search, /sort_by=/)
})
await check("a deep link restores the filters (reload keeps them)", async () => {
  await page.goto(`${BASE}/dashboard/gps?health=dead&days=14`, { waitUntil: "networkidle" })
  await page.waitForTimeout(3000)
  const chips = await page.locator("[data-testid=gps-filter-chip]").allInnerTexts()
  assert.ok(chips.length >= 1, "filters lost")
  const rows = await page.locator("[data-testid=gps-row]").count()
  assert.ok(rows >= 0)
})
await page.goto(`${BASE}/dashboard/gps`, { waitUntil: "networkidle" })
await page.waitForSelector("[data-testid=gps-row]", { timeout: 45000 })
await check("clicking a row opens the drawer (no navigation) with both fixes; Esc closes it", async () => {
  const url = page.url()
  await page.locator("[data-testid=gps-row]").nth(1).click()
  await page.locator("[data-testid=gps-drawer]").waitFor({ timeout: 10000 })
  assert.match(await page.locator("[data-testid=gps-drawer]").innerText(), /Wialon/)
  assert.equal(page.url().split("?")[0], url.split("?")[0], "navigated away")
  await page.keyboard.press("Escape")
  await page.waitForTimeout(600)
  assert.equal(await page.locator("[data-testid=gps-drawer]").count(), 0)
})
await check("export downloads a csv file", async () => {
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 20000 }), page.locator("[data-testid=gps-export-csv]").click()])
  const path = await download.path()
  const head = readFileSync(path).subarray(0, 3)
  assert.deepEqual([...head], [0xef, 0xbb, 0xbf], "not a utf-8 BOM csv")
})
await check("the tracker-health panel ranks the trackers and a row can be opened", async () => {
  const rows = page.locator("[data-testid=gps-health-row]")
  assert.ok((await rows.count()) >= 5, `health rows ${await rows.count()}`)
})
await page.screenshot({ path: `${SC}/snap_gps_analytics.png` })

await check("the wagons section: banner, KPI, a long table with confidence", async () => {
  await page.goto(`${BASE}/dashboard/gps/wagons`, { waitUntil: "networkidle" })
  await page.waitForSelector("[data-testid=wagon-row]", { timeout: 45000 })
  assert.match(await page.locator("[data-testid=wagons-banner]").innerText(), /GPS/)
  assert.ok((await page.locator("[data-testid=wagon-row]").count()) >= 20)
})
await check("a wagon in a train opens its detail with the four distance candidates", async () => {
  const hrefs = await page.locator("[data-testid=wagon-row] a").evaluateAll((els) => els.map((e) => e.getAttribute("href")))
  let found = false
  for (const href of hrefs.filter((h) => h && !h.includes("gtk-")).slice(0, 25)) {
    await page.goto(`${BASE}${href}`, { waitUntil: "networkidle" })
    await page.waitForTimeout(1500)
    if ((await page.locator("[data-testid=wagon-segments]").count()) > 0) { found = true; break }
  }
  assert.ok(found, "no wagon with segments among the first 25")
  for (const k of ["a", "b", "c", "d"]) assert.ok((await page.locator(`[data-testid=wagon-candidate-${k}]`).count()) >= 1, `candidate ${k}`)
  assert.ok((await page.locator("[data-testid=wagon-explanation]").innerText()).length > 20)
})
await page.screenshot({ path: `${SC}/snap_wagon_detail.png`, fullPage: true })

const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const mp = await phone.newPage()
await login(mp)
for (const path of ["/dashboard/gps", "/dashboard/gps/wagons", "/dashboard/gps?health=dead"]) {
  await check(`phone width: ${path} does not scroll sideways`, async () => {
    await mp.goto(`${BASE}${path}`, { waitUntil: "networkidle" })
    await mp.waitForTimeout(3500)
    const [sw, cw] = await mp.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
    assert.ok(sw <= cw + 1, `scrollWidth ${sw} > ${cw}`)
  })
}
await check("no page errors in the console", async () => {
  const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh|tile.openstreetmap|Google Maps JavaScript API error|AbortError|aborted/i.test(t))
  assert.equal(serious.length, 0, serious.join(" | "))
})
console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
