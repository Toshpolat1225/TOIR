// Real-browser (Edge) check of the weighing-scale page: both scales, the wagon ledger (totals -> one wagon's trips -> CSV), trains, unmatched.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/ad828521-7e36-4458-a5d2-d41bd40096be/scratchpad"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = "https://192.168.28.104"
const results = []
// closing a context right after a file download leaves Playwright's pending navigation promise rejecting: not a test failure
process.on("unhandledRejection", (e) => { if (!/Target page, context or browser has been closed/.test(String(e?.message))) throw e })
const check = async (name, fn) => { try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0]}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })

async function session(role, viewport = { width: 1440, height: 900 }) {
  const context = await browser.newContext({ viewport, locale: "ru-RU", ignoreHTTPSErrors: true, acceptDownloads: true })
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
  await check("the menu has «Весовая» and it opens the page", async () => {
    await page.getByRole("link", { name: "Весовая" }).first().click()
    await page.waitForURL(/\/dashboard\/scales/)
    await page.waitForSelector("[data-testid=scale-post]", { timeout: 15000 })
  })
  const body = () => page.locator("body").innerText()
  await check("both scales are shown with their state", async () => {
    assert.equal(await page.locator("[data-testid=scale-post]").count(), 2)
    const t = await body()
    assert.match(t, /Весы 93/); assert.match(t, /Весы 97/)
    assert.match(t, /Составов за 24 ч/)
  })
  await check("the wagon ledger opens first: totals with trips and tonnes", async () => {
    await page.waitForSelector("[data-testid=wagon-total]", { timeout: 20000 })
    assert.ok((await page.locator("[data-testid=wagon-total]").count()) > 5)
    assert.match(await page.locator("[data-testid=ledger-summary]").innerText(), /Вагонов: \d+ · рейсов: \d+ · тонн:/)
  })
  let wagon = ""
  await check("clicking a wagon shows its trips: when, how much, behind which locomotive", async () => {
    const first = page.locator("[data-testid=wagon-total]").first()
    wagon = (await first.locator("td").first().innerText()).split("\n")[0].replace(/нет связи с ОС/, "").trim()
    await first.click()
    await page.waitForSelector("[data-testid=wagon-trip]", { timeout: 20000 })
    const rows = await page.locator("[data-testid=wagon-trip]").allInnerTexts()
    assert.ok(rows.length > 0)
    assert.ok(rows.every((r) => /\d{2}\.\d{2}/.test(r) && /т|—/.test(r)), "a row misses the date or tonnes")
    assert.ok(rows.every((r) => /взвешивание вагона|доля состава|оценка по весу состава|неизвестно/.test(r)), "a row has no basis")
    assert.match(await page.locator("[data-testid=ledger-summary]").innerText(), /Рейсов: \d+ · вагонов: 1 ·/)
  })
  await check("the trips are only that wagon's (its label is in every row)", async () => {
    const rows = await page.locator("[data-testid=wagon-trip]").allInnerTexts()
    assert.ok(rows.every((r) => r.includes(wagon.split(" ")[0])), `a row is another wagon than ${wagon}`)
  })
  await check("the CSV export downloads a file for that wagon", async () => {
    const [download] = await Promise.all([page.waitForEvent("download", { timeout: 30000 }), page.getByRole("button", { name: /Выгрузить в Excel/ }).click()])
    assert.equal(download.suggestedFilename(), "wagon_trips.csv")
    const path = await download.path()
    const text = readFileSync(path, "utf-8")
    assert.ok(text.startsWith("\ufeff") && text.includes("Дата и время;Весы;Вагон"), "no BOM/header")
    assert.ok(text.trim().split("\n").length > 1)
  })
  await check("search by wagon number narrows the totals; «все вагоны» resets", async () => {
    await page.getByRole("button", { name: "Итоги по вагонам" }).click()
    await page.getByLabel("Вагон").fill("zzzz-no-such-wagon")
    await page.waitForTimeout(1200)
    assert.match(await body(), /Нет рейсов по выбранным условиям/)
    await page.getByLabel("Вагон").fill("")
    await page.waitForSelector("[data-testid=wagon-total]", { timeout: 20000 })
  })
  await check("a future-only period is empty", async () => {
    const d = new Date(Date.now() + 5 * 86400000).toISOString().slice(0, 10)
    await page.getByLabel("С даты").fill(d)
    await page.getByLabel("По дату").fill(d)
    await page.waitForTimeout(1200)
    assert.match(await body(), /Нет рейсов по выбранным условиям/)
  })
  await check("the «Составы» and «Не распознано» tabs load", async () => {
    await page.getByRole("tab", { name: "Составы" }).click()
    await page.waitForSelector("[data-testid=scale-train]", { timeout: 20000 })
    await page.getByRole("tab", { name: /Не распознано/ }).click()
    await page.waitForTimeout(1500)
    assert.match(await body(), /Подтвердите верный вариант|Все составы распознаны/)
  })
  await check("no page errors in the console", async () => {
    const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh/i.test(t))
    assert.equal(serious.length, 0, serious.join(" | "))
  })
  await context.close()
}

{
  const { context, page } = await session("admin", { width: 390, height: 844 })
  await check("phone width: the page itself does not scroll sideways", async () => {
    await page.goto(`${BASE}/dashboard/scales`, { waitUntil: "networkidle" })
    await page.waitForSelector("[data-testid=wagon-total]", { timeout: 25000 })
    const over = await page.evaluate(async () => { window.scrollTo(2000, 0); await new Promise((r) => setTimeout(r, 150)); return window.scrollX })
    assert.equal(over, 0, `scrolls ${over}px`)
  })
  await context.close()
}

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
