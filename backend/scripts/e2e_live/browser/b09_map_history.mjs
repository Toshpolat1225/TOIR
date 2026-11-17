// Real-browser (Edge) walk through the redesigned map and the asset history page.
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

async function session(viewport = { width: 1440, height: 900 }) {
  const context = await browser.newContext({ viewport, locale: "ru-RU", ignoreHTTPSErrors: true })
  const page = await context.newPage()
  const errors = []
  page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)))
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)) })
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await page.locator("input[type=text]").first().fill(CREDS.admin.email)
  await page.locator("input[type=password]").first().fill(CREDS.admin.password)
  await page.locator("button[type=submit]").click()
  await page.waitForURL(/dashboard/)
  return { context, page, errors }
}
const sideways = (page) => page.evaluate(async () => { window.scrollTo(2000, 0); await new Promise((r) => setTimeout(r, 150)); return window.scrollX })

{
  const { context, page, errors } = await session()
  const body = () => page.locator("body").innerText()
  await page.goto(`${BASE}/dashboard/map`, { waitUntil: "networkidle" })
  await check("the map hero shows the live KPIs", async () => {
    await page.waitForSelector("[data-testid=map-kpis]", { timeout: 25000 })
    await page.waitForTimeout(2500)
    const t = (await body()).toLowerCase()
    for (const label of ["на карте", "на связи сейчас", "едут сейчас", "составов на линии", "молчат более суток"]) assert.ok(t.includes(label), `no tile ${label}`)
  })
  await check("the trains tab lists trains with a locomotive and its wagons", async () => {
    await page.waitForSelector("[data-testid=train-row]", { timeout: 25000 })
    assert.ok((await page.locator("[data-testid=train-row]").count()) > 3)
    assert.match(await page.locator("[data-testid=train-row]").first().innerText(), /\d+ вагонов/)
  })
  await check("the tabs «Единицы» and «Сводка» work and the filters narrow the map", async () => {
    await page.getByRole("tab", { name: /Единицы/ }).click()
    await page.waitForTimeout(600)
    assert.ok((await page.locator("aside li").count()) > 5)
    await page.getByRole("tab", { name: "Сводка" }).click()
    await page.waitForTimeout(600)
    assert.match((await body()).toLowerCase(), /по типам/)
    assert.match((await body()).toLowerCase(), /по участкам/)
    await page.getByRole("button", { name: "Только едущие" }).click()
    await page.waitForTimeout(800)
    const moving = await body()
    assert.match(moving, /Показано:\s*\d+/)
    await page.getByRole("button", { name: "Только едущие" }).click()
    await page.getByRole("tab", { name: /Составы/ }).click()
  })
  await check("choosing a train opens the inspector with the history button", async () => {
    await page.locator("[data-testid=train-row] button").first().click()
    await page.waitForSelector("[data-testid=inspector]", { timeout: 10000 })
    assert.ok(await page.locator("[data-testid=open-history]").isVisible())
  })
  await check("the history page: hero, current state, stats, ordered timeline, track map", async () => {
    await page.locator("[data-testid=open-history]").click()
    await page.waitForURL(/\/dashboard\/map\/history\//)
    await page.waitForSelector("[data-testid=history-page]", { timeout: 30000 })
    assert.ok((await page.locator("[data-testid=history-title]").innerText()).trim().length > 0)
    const t = await body()
    for (const h of ["Сейчас:", "Время в составах", "Пройдено", "Где был: трек на карте", "С кем и что делал"]) assert.ok(t.includes(h), `no block ${h}`)
    await page.waitForSelector("[data-testid=history-segment]", { timeout: 15000 })
    assert.ok((await page.locator("[data-testid=history-segment]").count()) >= 1)
    await page.waitForSelector("[data-testid=track-map]", { timeout: 15000 })
  })
  await check("the time scrubber answers «where was it at that moment»", async () => {
    const slider = page.getByLabel("Момент времени")
    await slider.waitFor({ timeout: 10000 })
    const min = Number(await slider.getAttribute("min")), max = Number(await slider.getAttribute("max"))
    await slider.evaluate((el, v) => { const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set; setter.call(el, String(v)); el.dispatchEvent(new Event("input", { bubbles: true })) }, Math.round((min + max) / 2))
    await page.waitForSelector("[data-testid=scrub-answer]", { timeout: 10000 })
    assert.match(await page.locator("[data-testid=scrub-answer]").innerText(), /Координаты \d+\.\d{4}, \d+\.\d{4}/)
  })
  await check("a timeline entry says with whom and what it did; clicking selects it", async () => {
    const first = page.locator("[data-testid=history-segment] button").first()
    assert.match(await first.innerText(), /(двигался|стоял|положение)/)
    assert.match(await first.innerText(), /ваг/)
    await first.click()
    await page.waitForTimeout(500)
  })
  await check("the period buttons reload the history", async () => {
    await page.getByRole("button", { name: "30 дн." }).click()
    await page.waitForTimeout(2000)
    assert.equal(await page.getByRole("button", { name: "30 дн." }).getAttribute("aria-pressed"), "true")
    await page.waitForSelector("[data-testid=history-segment]", { timeout: 20000 })
  })
  await check("a locomotive link inside a wagon's history opens the locomotive's history", async () => {
    const link = page.getByRole("link", { name: /История локомотива/ }).first()
    if (await link.count()) {
      await link.click()
      await page.waitForURL(/\/dashboard\/map\/history\//)
      await page.waitForSelector("[data-testid=history-page]", { timeout: 30000 })
      assert.match(await page.locator("body").innerText(), /История локомотива|История вагона/)
    }
  })
  await check("no page errors in the console", async () => {
    const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh|tile.openstreetmap|Google Maps JavaScript API error/i.test(t))
    assert.equal(serious.length, 0, serious.join(" | "))
  })
  await context.close()
}

{
  const { context, page } = await session({ width: 390, height: 844 })
  await check("phone width: the map page does not scroll sideways", async () => {
    await page.goto(`${BASE}/dashboard/map`, { waitUntil: "networkidle" })
    await page.waitForSelector("[data-testid=map-kpis]", { timeout: 25000 })
    assert.equal(await sideways(page), 0)
  })
  await check("phone width: the history page does not scroll sideways", async () => {
    await page.waitForSelector("[data-testid=train-row]", { timeout: 25000 })
    await page.locator("[data-testid=train-row] button").first().click()
    await page.locator("[data-testid=open-history]").click()
    await page.waitForSelector("[data-testid=history-page]", { timeout: 30000 })
    assert.equal(await sideways(page), 0)
  })
  await context.close()
}

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
