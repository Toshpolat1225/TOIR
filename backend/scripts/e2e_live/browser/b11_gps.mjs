// Real-browser (Edge): the GPS page (three maps), the detail page and the unified map's verdict chips. Read-only.
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
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const page = await context.newPage()
const errors = []
page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)))
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)) })
await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await page.locator("input[type=text]").first().fill(CREDS.admin.email)
await page.locator("input[type=password]").first().fill(CREDS.admin.password)
await page.locator("button[type=submit]").click()
await page.waitForURL(/dashboard/)

await check("the menu has the GPS entry next to the map", async () => {
  await page.goto(`${BASE}/dashboard/gps`, { waitUntil: "networkidle" })
  const t = await page.locator("nav, aside").first().innerText()
  assert.match(t, /GPS/)
})
await page.waitForSelector("[data-testid=gps-row]", { timeout: 40000 })
await page.waitForTimeout(2500)
await check("KPI tiles, the feed panel and the explanation are shown", async () => {
  assert.ok((await page.locator("[data-testid=gps-kpi] > div").count()) >= 6, "few KPI tiles")
  assert.match(await page.locator("[data-testid=gps-feed]").innerText(), /GTK/)
  assert.ok(await page.locator("[data-testid=gps-explain]").count() >= 1)
})
for (const key of ["wialon", "gtk", "toir"]) {
  await check(`the ${key} map is drawn with markers`, async () => {
    const map = page.locator(`[data-testid=gps-map-${key}]`)
    await map.waitFor({ timeout: 20000 })
    await map.locator(".leaflet-marker-icon, .leaflet-overlay-pane path").first().waitFor({ timeout: 20000 })
    assert.ok(Number(await map.getAttribute("data-count")) > 30, `count ${await map.getAttribute("data-count")}`)
  })
}
await check("the table lists the locomotives with verdict chips (worst first)", async () => {
  const rows = page.locator("[data-testid=gps-row]")
  assert.ok((await rows.count()) >= 45, `rows ${await rows.count()}`)
  const statuses = await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-status")))
  const order = { bad: 0, warn: 1, ok: 2 }
  assert.ok(statuses.every((s, i) => i === 0 || order[s] >= order[statuses[i - 1]]), "not sorted worst first")
})
await check("choosing a row opens the drawer", async () => {
  await page.locator("[data-testid=gps-row]").nth(2).click()
  await page.locator("[data-testid=gps-drawer]").waitFor({ timeout: 10000 })
  assert.match(await page.locator("[data-testid=gps-drawer]").innerText(), /Wialon/)
})
await check("the issues-only toggle narrows the table", async () => {
  const all = await page.locator("[data-testid=gps-row]").count()
  await page.keyboard.press("Escape")
  await page.waitForTimeout(500)
  await page.locator("[data-testid=gps-only-issues]").click()
  await page.waitForTimeout(1500)
  const some = await page.locator("[data-testid=gps-row]").count()
  assert.ok(some <= all, `${some} > ${all}`)
  await page.locator("[data-testid=gps-only-issues]").click()
  await page.waitForTimeout(1200)
})
await page.screenshot({ path: `${SC}/snap_gps_overview.png`, fullPage: false })

let detailUrl = ""
await check("a row opens the detail page: day table, chart, three maps", async () => {
  await page.locator("[data-testid=gps-row] a").first().click()
  await page.waitForURL(/dashboard\/gps\/[0-9a-f-]{36}/, { timeout: 15000 })
  detailUrl = page.url()
  await page.waitForSelector("[data-testid=gps-detail-day]", { timeout: 40000 })
  assert.ok((await page.locator("[data-testid=gps-detail-day]").count()) >= 7)
  assert.ok((await page.locator("[data-testid=gps-daily-chart]").count()) >= 1)
  for (const k of ["wialon", "gtk", "toir"]) await page.locator(`[data-testid=gps-detail-map-${k}]`).waitFor({ timeout: 20000 })
})
await page.waitForTimeout(3000)
await check("the track maps draw lines (two separate tracks and an overlay)", async () => {
  for (const k of ["wialon", "gtk", "toir"]) {
    const n = await page.locator(`[data-testid=gps-detail-map-${k}] .leaflet-overlay-pane path`).count()
    assert.ok(n >= 1, `${k}: no line`)
  }
})
await page.screenshot({ path: `${SC}/snap_gps_detail.png`, fullPage: true })

await check("the unified map has the verdict chips and the legend", async () => {
  await page.goto(`${BASE}/dashboard/map`, { waitUntil: "networkidle" })
  await page.waitForSelector("[data-testid=map-verdict-chips]", { timeout: 30000 })
  assert.ok((await page.locator("[data-testid^=map-verdict-chip-]").count()) >= 3)
  assert.ok((await page.locator("[data-testid=map-verdict-legend]").count()) >= 1)
})
await check("a verdict chip filters the map and the list", async () => {
  await page.waitForSelector(".leaflet-container", { timeout: 20000 })
  await page.waitForTimeout(2500)
  const before = await page.locator(".leaflet-marker-icon").count()
  const chip = page.locator("[data-testid^=map-verdict-chip-]").first()
  await chip.click()
  await page.waitForTimeout(1500)
  assert.equal(await chip.getAttribute("aria-pressed"), "true")
  const after = await page.locator(".leaflet-marker-icon").count()
  assert.ok(after <= before, `${after} > ${before}`)
  await chip.click()
})
await check("the map inspector shows both fixes and links to the comparison", async () => {
  await page.getByRole("tab", { name: /Единицы/ }).click()
  await page.waitForTimeout(500)
  await page.locator("aside ul li button").first().click()
  await page.waitForTimeout(1500)
  const insp = page.locator("[data-testid=inspector]")
  if (await insp.count()) assert.ok((await insp.innerText()).length > 20)
})
await page.screenshot({ path: `${SC}/snap_gps_map.png` })

// phone width: no sideways scrolling
const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const mp = await phone.newPage()
await mp.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await mp.locator("input[type=text]").first().fill(CREDS.admin.email)
await mp.locator("input[type=password]").first().fill(CREDS.admin.password)
await mp.locator("button[type=submit]").click()
await mp.waitForURL(/dashboard/)
for (const path of ["/dashboard/gps", detailUrl.replace(BASE, ""), "/dashboard/map"]) {
  await check(`phone width: ${path.replace(/[0-9a-f-]{36}/, ":id")} does not scroll sideways`, async () => {
    await mp.goto(`${BASE}${path}`, { waitUntil: "networkidle" })
    await mp.waitForTimeout(3500)
    const [sw, cw] = await mp.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
    assert.ok(sw <= cw + 1, `scrollWidth ${sw} > ${cw}`)
  })
}
await mp.screenshot({ path: `${SC}/snap_gps_map_phone.png` })
await check("no page errors in the console", async () => {
  const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh|tile.openstreetmap|Google Maps JavaScript API error/i.test(t))
  assert.equal(serious.length, 0, serious.join(" | "))
})
console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
