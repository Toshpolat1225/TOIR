// Real-browser (Edge) check of the Map page (without a Google key: OpenStreetMap map + list).
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/ad828521-7e36-4458-a5d2-d41bd40096be/scratchpad"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = "https://192.168.28.104"
const results = []
const check = async (name, fn) => { try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0]}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })

async function session(role, viewport = { width: 1440, height: 900 }) {
  const context = await browser.newContext({ viewport, locale: "ru-RU", ignoreHTTPSErrors: true })
  const page = await context.newPage()
  const errors = []
  page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)))
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)) })
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await page.locator("input[type=text]").first().fill(CREDS[role].email)
  await page.locator("input[type=password]").first().fill(CREDS[role].password)
  await page.locator("button[type=submit]").click()
  await page.waitForURL(/dashboard/)
  return { context, page, errors }
}

{
  const { context, page, errors } = await session("admin")
  await check("the sidebar has «Карта» right after «Аналитика»", async () => {
    const labels = await page.locator("nav a").allInnerTexts()
    const clean = labels.map((t) => t.trim())
    const i = clean.indexOf("Аналитика")
    assert.ok(i >= 0 && clean[i + 1] === "Карта", clean.join(" | "))
  })
  await page.locator("nav a", { hasText: "Карта" }).first().click()
  await page.waitForURL(/\/dashboard\/map/)
  await page.waitForTimeout(2500)
  const body = () => page.locator("body").innerText()
  await check("the map page shows the summary (on the map / Wialon / GTK / without coordinates)", async () => {
    const t = await body()
    assert.match(t, /на карте\s*\d+\s*из\s*\d+/i)
    assert.match(t, /Wialon \(GPS\):\s*\d+/)
    assert.match(t, /GTK:\s*\d+/)
    assert.match(t, /Состав \(по локомотиву\):\s*\d+/)
    assert.match(t, /без координат\s*\d+/i)
  })
  await check("the list shows assets with their source and age", async () => {
    await page.getByRole("tab", { name: /Единицы/ }).click()
    await page.waitForTimeout(500)
    const items = page.locator("aside ul li button")
    assert.ok((await items.count()) > 20, "list too short")
    assert.match(await items.first().innerText(), /Wialon|GTK|Состав|составе/)
  })
  await check("without a Google key the OpenStreetMap map (Leaflet) is shown with all points as clusters/markers", async () => {
    await page.waitForSelector(".leaflet-container", { timeout: 15000 })
    await page.waitForTimeout(1500)
    const n = await page.locator(".marker-cluster, .leaflet-interactive").count()
    assert.ok(n > 0, "no clusters or markers on the map")
    assert.ok((await page.locator(".leaflet-control-attribution").innerText()).includes("OpenStreetMap"), "no OSM attribution")
  })
  await check("selecting an asset opens its popup on the map with links", async () => {
    await page.locator("aside ul li button").first().click()
    await page.waitForSelector(".leaflet-popup-content a", { timeout: 15000 })
    await page.waitForTimeout(600)
    const t = (await page.locator(".leaflet-popup-content").first().textContent()) ?? ""
    assert.match(t, /Источник: (Wialon|GTK)/)
    assert.ok(await page.locator(".leaflet-popup a", { hasText: "Google Maps" }).first().isVisible())
    assert.ok(await page.locator(".leaflet-popup a", { hasText: "Где был и с кем" }).first().isVisible())
  })
  await check("wagons ride with their locomotive: the train filter lists wagons with a train caption, and the popup names the locomotive", async () => {
    await page.getByRole("button", { name: /Состав \(по локомотиву\):/ }).click()
    await page.waitForTimeout(500)
    const texts = await page.locator("aside ul li button").allInnerTexts()
    assert.ok(texts.length > 0 && texts.every((t) => t.includes("В составе")), "not all train captions")
    await page.locator("aside ul li button").first().click()
    await page.waitForSelector(".leaflet-popup-content a", { timeout: 15000 })
    await page.waitForTimeout(600)
    const popup = (await page.locator(".leaflet-popup-content").first().textContent()) ?? ""
    assert.match(popup, /\d+ вагонов · \d+ м/)  // the train caption: how many cars, how long it is
    assert.match(popup, /\d+-й от локомотива/)  // which car of the formation was chosen
    assert.match(await page.locator("[data-testid=inspector]").innerText(), /Состав \(по локомотиву\)/)
  })
  await check("the source filter narrows the list to GTK only", async () => {
    await page.getByRole("button", { name: "Все", exact: true }).click()
    await page.getByRole("button", { name: /GTK:/ }).click()
    await page.waitForTimeout(500)
    const texts = await page.locator("aside ul li button").allInnerTexts()
    assert.ok(texts.length > 0 && texts.every((t) => t.includes("GTK")), "not all GTK")
  })
  await check("search narrows the list", async () => {
    await page.getByRole("button", { name: "Все", exact: true }).click()
    await page.getByLabel("Поиск").fill("zzzz-no-such-asset")
    await page.waitForTimeout(400)
    assert.match(await body(), /Нет единиц с координатами/)
  })
  await check("no page errors in the console", async () => {
    const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh|Google Maps JavaScript API error/i.test(t))
    assert.equal(serious.length, 0, serious.join(" | "))
  })
  await context.close()
}

{
  const { context, page } = await session("master")
  await page.goto(`${BASE}/dashboard/map`, { waitUntil: "networkidle" })
  await page.waitForTimeout(2000)
  await check("a master (empty ZZTEST section) sees an empty map, not the other sections", async () => {
    const t = await page.locator("body").innerText()
    assert.match(t, /на карте\s*0\s*из\s*0/i)
  })
  await context.close()
}

{
  const { context, page } = await session("admin", { width: 390, height: 844 })
  await page.goto(`${BASE}/dashboard/map`, { waitUntil: "networkidle" })
  await page.waitForTimeout(1500)
  await check("phone width: the map page does not scroll sideways", async () => {
    const over = await page.evaluate(async () => { window.scrollTo(2000, 0); await new Promise((r) => setTimeout(r, 150)); return window.scrollX })
    assert.equal(over, 0, `scrolls ${over}px`)
  })
  await context.close()
}

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
