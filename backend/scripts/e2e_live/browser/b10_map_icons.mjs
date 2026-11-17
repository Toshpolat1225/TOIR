// Real-browser (Edge): pictograms instead of dots, train glyphs with a car count, and the true-scale formation at high zoom.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/ad828521-7e36-4458-a5d2-d41bd40096be/scratchpad"
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
await page.goto(`${BASE}/dashboard/map`, { waitUntil: "networkidle" })
await page.waitForSelector("[data-testid=train-row]", { timeout: 30000 })
await page.waitForSelector(".leaflet-container", { timeout: 20000 })
await page.waitForTimeout(2500)
const zoom = async () => Number(await page.locator("[data-testid=osm-map]").getAttribute("data-zoom"))

await check("the legend shows the pictograms of the vehicle types", async () => {
  const legend = page.locator("[data-testid=map-legend]")
  assert.ok((await legend.locator("svg").count()) >= 5, "no pictograms")
  const t = await legend.innerText()
  for (const label of ["Электровоз", "Тепловоз", "Вагон-самосвал", "Цистерна", "Платформа"]) assert.ok(t.includes(label), `no ${label}`)
})
await check("the map shows pictograms (svg icons), not dots", async () => {
  assert.ok((await page.locator(".leaflet-marker-icon.pt-icon svg").count()) > 5, "no svg pictograms")
  assert.equal(await page.locator(".leaflet-overlay-pane path.leaflet-interactive:not([stroke-dasharray])").count(), 0, "vector shapes at the country zoom")
})
await check("trains are single pictograms with a car count at the country zoom", async () => {
  assert.ok((await zoom()) < 16)
  const badges = await page.locator(".leaflet-marker-icon.pt-icon span").allInnerTexts()
  assert.ok(badges.filter((t) => /^\d{1,2}$/.test(t.trim())).length > 10, `badges: ${badges.slice(0, 5).join(",")}`)
})
await check("choosing a train zooms to it and draws the formation to scale (many vehicle polygons)", async () => {
  await page.locator("[data-testid=train-row] button").first().click()
  await page.waitForFunction(() => Number(document.querySelector("[data-testid=osm-map]")?.getAttribute("data-zoom")) >= 16, null, { timeout: 20000 })
  await page.waitForTimeout(1500)
  const polys = await page.locator(".leaflet-overlay-pane path.leaflet-interactive").count()
  assert.ok(polys >= 15, `only ${polys} polygons`)
})
await check("a wagon polygon is selectable and its popup lists the train in order", async () => {
  await page.locator(".leaflet-overlay-pane path.leaflet-interactive").nth(3).dispatchEvent("click")
  await page.waitForSelector(".leaflet-popup-content", { timeout: 10000 })
  const t = await page.locator(".leaflet-popup-content").first().innerText()
  assert.match(t, /вагонов/)
  assert.match(t, /Где был|Локомотив|вагон/i)
})
await check("zooming out brings the train back to one pictogram", async () => {
  for (let i = 0; i < 6; i++) { await page.locator(".leaflet-control-zoom-out").click(); await page.waitForTimeout(700) } // a click during the zoom animation is ignored
  await page.waitForFunction(() => Number(document.querySelector("[data-testid=osm-map]")?.getAttribute("data-zoom")) < 16, null, { timeout: 20000 })
  await page.waitForTimeout(1200)
  assert.equal(await page.locator(".leaflet-overlay-pane path.leaflet-interactive:not([stroke-dasharray])").count(), 0)
})
await check("a wagon chosen in the train list is highlighted inside the formation", async () => {
  await page.getByRole("tab", { name: /Единицы/ }).click()
  await page.getByRole("button", { name: "Все", exact: true }).click()
  await page.getByRole("button", { name: /Состав \(по локомотиву\):/ }).click()
  await page.waitForTimeout(600)
  await page.locator("aside li button").first().click()
  await page.waitForFunction(() => Number(document.querySelector("[data-testid=osm-map]")?.getAttribute("data-zoom")) >= 17, null, { timeout: 20000 })
  await page.waitForTimeout(1200)
  assert.ok((await page.locator(".leaflet-overlay-pane path[stroke='#ef4444']").count()) >= 1, "the chosen wagon is not outlined in red")
})
await check("no page errors in the console", async () => {
  const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh|tile.openstreetmap|Google Maps JavaScript API error/i.test(t))
  assert.equal(serious.length, 0, serious.join(" | "))
})
await page.screenshot({ path: `${SC}/snap_icons_wagon.png` })

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
