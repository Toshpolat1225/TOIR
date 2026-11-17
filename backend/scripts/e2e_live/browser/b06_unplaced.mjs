// Real-browser (Edge) check of the "without coordinates" page: the chip on the map opens it, every object shows why / since when / from where.
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
  await page.goto(`${BASE}/dashboard/map`, { waitUntil: "networkidle" })
  await page.waitForTimeout(2500)
  await check("the «Без координат» chip on the map is a link to the details page", async () => {
    const chip = page.locator("a", { hasText: "Без координат" }).first()
    assert.ok(await chip.isVisible(), "chip is not a link")
    assert.equal(await chip.getAttribute("href"), "/dashboard/map/unplaced")
    await chip.click()
    await page.waitForURL(/\/dashboard\/map\/unplaced/)
    await page.waitForSelector("[data-testid=unplaced-item]", { timeout: 15000 })
  })
  const body = () => page.locator("body").innerText()
  await check("the page has the title, the reason chips and the total", async () => {
    const t = await body()
    assert.match(t, /Объекты без координат/)
    assert.match(t, /Все:\s*\d+/)
    assert.match(t, /Не привязан к Wialon\/GTK:\s*\d+/)
    assert.match(t, /Показано 1–\d+ из \d+/)
  })
  await check("every object answers WHY, HOW LONG and FROM WHERE", async () => {
    const items = page.locator("[data-testid=unplaced-item]")
    const n = await items.count()
    assert.ok(n > 10, `only ${n} items`)
    const texts = await items.allInnerTexts()
    assert.ok(texts.every((t) => /Как давно:/.test(t) && /Откуда позиция:/.test(t) && /Инв\. №/.test(t)), "an item misses a part")
    assert.ok(texts.every((t) => /Не привязан|Юнит Wialon|Wialon не|Только GTK|Вагон не найден|GTK не передаёт|В составе/.test(t)), "an item has no reason")
  })
  await check("a GTK candidate hint is shown for unlinked wagons that can be linked", async () => {
    await page.getByText("Можно привязать к GTK сразу").first().click()
    await page.waitForTimeout(800)
    const texts = await page.locator("[data-testid=unplaced-item]").allInnerTexts()
    assert.ok(texts.length > 0 && texts.every((t) => /Возможно, это вагон GTK/.test(t)), "no candidate hint")
    await page.getByText("Можно привязать к GTK сразу").first().click()
    await page.waitForTimeout(500)
  })
  await check("a reason chip filters the list (GTK не передаёт координаты)", async () => {
    await page.getByRole("button", { name: /GTK не передаёт координаты/ }).first().click()
    await page.waitForTimeout(800)
    const texts = await page.locator("[data-testid=unplaced-item]").allInnerTexts()
    assert.ok(texts.length > 0 && texts.every((t) => t.includes("GTK не передаёт координаты")), "filter leaks")
    assert.ok(texts.every((t) => /GTK видит вагон с \d{2}\.\d{2}\.\d{4}/.test(t)), "no since-date")
    await page.getByRole("button", { name: /^Все:/ }).click()
    await page.waitForTimeout(500)
  })
  await check("search and the type filter narrow the list", async () => {
    await page.getByLabel("Поиск").fill("zzzz-no-such-asset")
    await page.waitForTimeout(900)
    assert.match(await body(), /Нет объектов без координат/)
    await page.getByLabel("Поиск").fill("")
    await page.waitForTimeout(600)
    await page.getByLabel("Тип").selectOption({ index: 1 })
    await page.waitForTimeout(800)
    assert.ok((await page.locator("[data-testid=unplaced-item]").count()) > 0)
  })
  await check("paging: the next page shows other objects", async () => {
    await page.getByLabel("Тип").selectOption("")
    await page.waitForTimeout(800)
    const first = (await page.locator("[data-testid=unplaced-item]").first().innerText()).split("\n")[0]
    await page.getByRole("button", { name: "Дальше" }).click()
    await page.waitForTimeout(900)
    assert.match(await body(), /Показано 51–/)
    assert.notEqual((await page.locator("[data-testid=unplaced-item]").first().innerText()).split("\n")[0], first)
  })
  await check("the back link returns to the map", async () => {
    await page.getByRole("link", { name: /К карте/ }).click()
    await page.waitForURL(/\/dashboard\/map$/)
  })
  await check("no page errors in the console", async () => {
    const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh|Google Maps JavaScript API error|tile.openstreetmap/i.test(t))
    assert.equal(serious.length, 0, serious.join(" | "))
  })
  await context.close()
}

{
  const { context, page } = await session("master")
  await page.goto(`${BASE}/dashboard/map/unplaced`, { waitUntil: "networkidle" })
  await page.waitForTimeout(2000)
  await check("a master (empty ZZTEST section) sees an empty list, not the other sections", async () => {
    assert.match(await page.locator("body").innerText(), /Нет объектов без координат/)
    assert.equal(await page.locator("[data-testid=unplaced-item]").count(), 0)
  })
  await context.close()
}

{
  const { context, page } = await session("admin", { width: 390, height: 844 })
  await page.goto(`${BASE}/dashboard/map/unplaced`, { waitUntil: "networkidle" })
  await page.waitForSelector("[data-testid=unplaced-item]", { timeout: 15000 })
  await check("phone width: the page does not scroll sideways", async () => {
    const over = await page.evaluate(async () => { window.scrollTo(2000, 0); await new Promise((r) => setTimeout(r, 150)); return window.scrollX })
    assert.equal(over, 0, `scrolls ${over}px`)
  })
  await context.close()
}

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
