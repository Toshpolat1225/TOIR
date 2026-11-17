// Real-browser (Edge) walk through the weighing-scale command center: overview -> wagon card -> train card -> locomotive card.
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
const topWagonLink = (page) => page.locator("section:has(h2:text-is('Вагоны: больше всего тонн')) a").first()

{
  const { context, page, errors } = await session()
  const body = () => page.locator("body").innerText()
  await page.goto(`${BASE}/dashboard/scales`, { waitUntil: "networkidle" })
  await check("overview: hero tonnes, six KPI tiles and the period switch", async () => {
    await page.waitForSelector("[data-testid=hero-tonnes]", { timeout: 25000 })
    assert.match(await page.locator("[data-testid=hero-tonnes]").innerText(), /т/)
    const t = await body()
    for (const label of ["Составов", "Рейсов вагонов", "Средний состав", "В среднем на вагон", "Составы с перегрузом", "Распознано"]) assert.ok(t.toLowerCase().includes(label.toLowerCase()), `no tile ${label}`)
    await page.getByRole("button", { name: "7 дн." }).click()
    await page.waitForTimeout(1500)
    assert.match(await body(), /Перевезено за 7 дн\./)
    await page.getByRole("button", { name: "30 дн." }).click()
    await page.waitForTimeout(1200)
  })
  await check("overview: the charts are drawn and the lists have rows", async () => {
    assert.ok((await page.locator("svg[aria-label='Тонн по дням'] rect").count()) > 3, "no bars")
    const t = await body()
    for (const h of ["Тонн по дням", "Сегодня на путях", "Когда работают весы", "Откуда везут", "Экскаваторы", "Локомотивы: кто перевёз больше", "Вагоны: больше всего тонн", "Качество данных"]) assert.ok(t.toLowerCase().includes(h.toLowerCase()), `no panel ${h}`)
  })
  await check("clicking a top wagon opens its card: stats, splits, recent trips", async () => {
    const link = topWagonLink(page)
    await link.waitFor({ timeout: 10000 })
    await link.click()
    await page.waitForURL(/\/dashboard\/scales\/wagon\//)
    await page.waitForSelector("[data-testid=wagon-card]", { timeout: 25000 })
    assert.ok((await page.locator("[data-testid=wagon-title]").innerText()).trim().length > 0)
    const t = await body()
    for (const h of ["Перевезено", "В среднем за рейс", "Точность", "Откуда везёт", "Какими локомотивами", "Последние рейсы"]) assert.ok(t.toLowerCase().includes(h.toLowerCase()), `no block ${h}`)
    assert.ok((await page.locator("[data-testid=wagon-recent]").count()) > 0, "no recent trips")
  })
  await check("the wagon's period switch reloads the card", async () => {
    await page.getByRole("button", { name: "90 дн." }).click()
    await page.waitForTimeout(1500)
    assert.equal(await page.getByRole("button", { name: "90 дн." }).getAttribute("aria-pressed"), "true")
  })
  await check("a trip time opens the train card: drawing, reconciliation, units", async () => {
    await page.locator("[data-testid=wagon-recent] a").first().click()
    await page.waitForURL(/\/dashboard\/scales\/train\//)
    await page.waitForSelector("[data-testid=train-card]", { timeout: 25000 })
    const t = await body()
    for (const h of ["Состав на весах", "Откуда берутся тонны", "Кто тянул", "Состав в GTK", "Взвешивание по единицам"]) assert.ok(t.toLowerCase().includes(h.toLowerCase()), `no block ${h}`)
    assert.ok((await page.locator("[data-testid=unit-row]").count()) > 3, "no units")
  })
  await check("the train card moves between neighbouring trains", async () => {
    const next = page.getByRole("link", { name: /Следующий состав|Предыдущий состав/ }).first()
    assert.ok(await next.count(), "no neighbour link")
    const before = page.url()
    await next.click()
    await page.waitForFunction((u) => location.href !== u, before, { timeout: 15000 })
    await page.waitForSelector("[data-testid=train-card]", { timeout: 25000 })
  })
  await check("the locomotive link opens the locomotive card", async () => {
    const loco = page.locator("section:has(h2:text-is('Кто тянул')) a").first()
    if (await loco.count()) {
      await loco.click()
      await page.waitForURL(/\/dashboard\/scales\/loco\//)
      await page.waitForSelector("[data-testid=loco-card]", { timeout: 25000 })
      const t = await body()
      for (const h of ["Составов за период", "Откуда везёт", "Наработка и обслуживание", "Связи с другими системами", "Какие вагоны тянул", "Последние составы"]) assert.ok(t.toLowerCase().includes(h.toLowerCase()), `no block ${h}`)
      assert.ok((await page.locator("[data-testid=loco-recent]").count()) > 0, "no recent trains")
    }
  })
  await check("an unlinked wagon from the ledger opens a card that explains how to link it", async () => {
    await page.goto(`${BASE}/dashboard/scales`, { waitUntil: "networkidle" })
    await page.waitForSelector("[data-testid=wagon-total]", { timeout: 25000 })
    const row = page.locator("[data-testid=wagon-total]", { hasText: "нет связи с ОС" }).first()
    if (await row.count()) {
      await row.locator("a").first().click()
      await page.waitForSelector("[data-testid=wagon-card]", { timeout: 25000 })
      assert.match(await body(), /известен только по GTK/)
    }
  })
  await check("no page errors in the console", async () => {
    const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh/i.test(t))
    assert.equal(serious.length, 0, serious.join(" | "))
  })
  await context.close()
}

{
  const { context, page } = await session({ width: 390, height: 844 })
  await check("phone width: overview does not scroll sideways", async () => {
    await page.goto(`${BASE}/dashboard/scales`, { waitUntil: "networkidle" })
    await page.waitForSelector("[data-testid=hero-tonnes]", { timeout: 25000 })
    assert.equal(await sideways(page), 0)
  })
  await check("phone width: wagon and train cards do not scroll sideways", async () => {
    await topWagonLink(page).click()
    await page.waitForSelector("[data-testid=wagon-card]", { timeout: 25000 })
    assert.equal(await sideways(page), 0, "wagon card")
    await page.locator("[data-testid=wagon-recent] a").first().click()
    await page.waitForSelector("[data-testid=train-card]", { timeout: 25000 })
    assert.equal(await sideways(page), 0, "train card")
  })
  await context.close()
}

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
