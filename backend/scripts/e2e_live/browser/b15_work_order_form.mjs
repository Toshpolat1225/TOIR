// Real-browser (Edge) check of the "Создать наряд-заказ" form: type-ahead selects, automatic defaults (start, executor, section,
// planned end from the repair-type durations), type filtering by asset kind, creator/plan/fact transparency on the saved order.
// Needs an admin whose full name equals an employee's name, two sections, locomotive + wagon assets and repair types with and without
// a duration (the rehearsal seed does this). Env: TOIR_BASE (default live), TOIR_CREDS (json {email,password}).
// NOTE: it really creates one work order whose description starts with ZZTEST - clean it up afterwards.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const BASE = process.env.TOIR_BASE ?? "https://192.168.28.104"
const CREDS = JSON.parse(readFileSync(process.env.TOIR_CREDS, "utf-8"))
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
  await page.locator("input[type=text]").first().fill(CREDS.email)
  await page.locator("input[type=password]").first().fill(CREDS.password)
  await page.locator("button[type=submit]").click()
  await page.waitForURL(/dashboard/)
  return { context, page, errors }
}

const options = (page) => page.locator("[role=listbox] [role=option]")
const openForm = async (page) => {
  await page.goto(`${BASE}/dashboard/work-orders`, { waitUntil: "networkidle" })
  await page.getByRole("button", { name: /Создать наряд/ }).first().click()
  await page.waitForSelector("[data-testid=wo-asset]", { timeout: 25000 })
}
const addHours = (value, hours) => {
  const d = new Date(value)
  const t = new Date(d.getTime() + hours * 3600000)
  const p = (n) => String(n).padStart(2, "0")
  return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())}T${p(t.getHours())}:${p(t.getMinutes())}`
}

{
  const { context, page, errors } = await session()
  await openForm(page)
  let start = ""

  await check("planned start is filled with the current time, planned end is empty until types are chosen", async () => {
    start = await page.locator("[data-testid=wo-start]").inputValue()
    assert.ok(start, "no planned start")
    assert.ok(Math.abs(new Date(start).getTime() - Date.now()) < 3 * 60000, `start is not 'now': ${start}`)
    assert.equal(await page.locator("[data-testid=wo-end]").inputValue(), "")
  })
  await check("before anything is chosen the section and the executor already default to the signed-in person", async () => {
    assert.equal(await page.locator("[data-testid=wo-section]").inputValue(), "Участок Альфа")
    assert.equal(await page.locator("[data-testid=wo-executor]").inputValue(), "Тестов Админ Иванович")
  })
  await check("asset search narrows on every keystroke (name, inventory number, no match)", async () => {
    const asset = page.locator("[data-testid=wo-asset]")
    await asset.click()
    const all = await options(page).count()
    assert.ok(all >= 3, `expected the full list, got ${all}`)
    await asset.pressSequentially("LOC")
    const loco = await options(page).count()
    assert.ok(loco >= 1 && loco < all, `typing did not filter: ${all} -> ${loco}`)
    await asset.pressSequentially("-001")
    assert.equal(await options(page).count(), 1)
    await asset.fill("LOC-002")
    assert.equal(await options(page).count(), 1)
    await asset.fill("qqqqzzzz")
    assert.equal(await options(page).count(), 0)
    assert.match(await page.locator("[role=listbox]").innerText(), /Ничего не найдено/)
  })
  await check("Enter picks the highlighted asset; the section and the signed-in executor fill in by themselves", async () => {
    const asset = page.locator("[data-testid=wo-asset]")
    await asset.fill("LOC-001")
    await page.keyboard.press("Enter")
    assert.match(await asset.inputValue(), /LOC-001/)
    assert.equal(await page.locator("[data-testid=wo-section]").inputValue(), "Участок Альфа")
    assert.equal(await page.locator("[data-testid=wo-executor]").inputValue(), "Тестов Админ Иванович")
  })
  await check("executor list is limited to the section's staff and is searchable", async () => {
    const ex = page.locator("[data-testid=wo-executor]")
    await ex.click()
    const names = await options(page).allInnerTexts()
    assert.ok(names.some((n) => n.includes("Сидоров")), "section colleague missing")
    assert.ok(!names.some((n) => n.includes("Козлов")), "other section's employee shown")
    await ex.fill("9002")
    assert.equal(await options(page).count(), 1)
    await page.keyboard.press("Enter")
    assert.equal(await ex.inputValue(), "Сидоров Пётр")
    await ex.click(); await ex.fill("Тестов"); await page.keyboard.press("Enter")
    assert.equal(await ex.inputValue(), "Тестов Админ Иванович")
  })
  await check("repair types are limited to the asset kind and filter as you type", async () => {
    const types = page.locator("[data-testid=wo-types]")
    await types.click()
    const texts = await options(page).allInnerTexts()
    assert.ok(texts.some((t) => t.includes("UI-ТО-1")) && !texts.some((t) => t.includes("UI-ВАГ-1")), "locomotive filter broken")
    await types.fill("то-2")
    assert.equal(await options(page).count(), 1)
    await types.fill("")
  })
  await check("choosing repair types computes the planned end (start + sum of standard hours) and the description", async () => {
    const types = page.locator("[data-testid=wo-types]")
    await types.fill("UI-ТО-1"); await page.keyboard.press("Enter")
    await types.fill("UI-ТО-2"); await page.keyboard.press("Enter")
    await page.waitForFunction(() => document.querySelectorAll("[data-testid=chip]").length === 2)
    assert.equal(await page.locator("[data-testid=wo-end]").inputValue(), addHours(start, 6.5))
    assert.match(await page.locator("[data-testid=wo-end-hint]").innerText(), /Рассчитано автоматически/)
    const desc = await page.locator("textarea").first().inputValue()
    assert.ok(desc.includes("UI-ТО-1") && desc.includes("UI-ТО-2"), `description not suggested: ${desc}`)
  })
  await check("a type without duration leaves the end empty and says where to fill it; removing it restores the calculation", async () => {
    const types = page.locator("[data-testid=wo-types]")
    await types.fill("UI-ТР-1"); await page.keyboard.press("Enter")
    await page.waitForFunction(() => document.querySelectorAll("[data-testid=chip]").length === 3)
    assert.equal(await page.locator("[data-testid=wo-end]").inputValue(), "")
    assert.match(await page.locator("[data-testid=wo-end-hint]").innerText(), /UI-ТР-1/)
    await page.getByRole("button", { name: "Убрать UI-ТР-1" }).click()
    await page.waitForFunction(() => document.querySelectorAll("[data-testid=chip]").length === 2)
    assert.equal(await page.locator("[data-testid=wo-end]").inputValue(), addHours(start, 6.5))
  })
  await check("changing the start moves the automatic end; a hand-typed end is respected", async () => {
    await page.locator("[data-testid=wo-start]").fill("2030-01-10T08:00")
    assert.equal(await page.locator("[data-testid=wo-end]").inputValue(), "2030-01-10T14:30")
    await page.locator("[data-testid=wo-end]").fill("2030-01-10T20:00")
    await page.locator("[data-testid=wo-start]").fill("2030-01-10T09:00")
    assert.equal(await page.locator("[data-testid=wo-end]").inputValue(), "2030-01-10T20:00")
    assert.match(await page.locator("[data-testid=wo-end-hint]").innerText(), /вручную/)
    await page.getByRole("button", { name: "вернуть расчёт" }).click()
    assert.equal(await page.locator("[data-testid=wo-end]").inputValue(), "2030-01-10T15:30")
  })
  await check("switching to a wagon drops the locomotive types and offers wagon types only", async () => {
    const asset = page.locator("[data-testid=wo-asset]")
    await asset.click(); await asset.fill("WAG-777"); await page.keyboard.press("Enter")
    await page.waitForFunction(() => document.querySelectorAll("[data-testid=chip]").length === 0)
    const types = page.locator("[data-testid=wo-types]")
    await types.click()
    const texts = await options(page).allInnerTexts()
    assert.ok(texts.length === 1 && texts[0].includes("UI-ВАГ-1"), `wagon types: ${texts.join("|")}`)
    await types.fill("")
  })
  await check("an order is created with creator, plan and empty fact; the list and the card show them", async () => {
    const asset = page.locator("[data-testid=wo-asset]")
    await asset.click(); await asset.fill("LOC-001"); await page.keyboard.press("Enter")
    const types = page.locator("[data-testid=wo-types]")
    await types.fill("UI-ТО-1"); await page.keyboard.press("Enter")
    await page.waitForFunction(() => document.querySelectorAll("[data-testid=chip]").length === 1)
    await page.getByRole("button", { name: "Изменить", exact: true }).click()
    await page.getByText("Виды ремонта и ТМЦ").first().waitFor({ timeout: 10000 })
    assert.equal(await page.getByText("Добавить вид ремонта").count(), 0, "second type picker shown")
    assert.equal(await page.getByRole("button", { name: "Удалить вид ремонта" }).count(), 0)
    await page.getByRole("button", { name: "Применить" }).click()
    await page.getByText("Виды ремонта и ТМЦ").first().waitFor({ state: "detached", timeout: 10000 })
    await page.locator("textarea").first().fill("ZZTEST форма наряда")
    await page.getByRole("button", { name: "Создать наряд", exact: true }).last().click()
    await page.waitForSelector("[data-testid=wo-asset]", { state: "detached", timeout: 25000 })
    const row = page.locator("button", { hasText: "ZZTEST форма наряда" }).first()
    await row.waitFor({ timeout: 25000 })
    assert.match(await row.innerText(), /Тестов Админ Иванович/)
    await row.click()
    await page.waitForSelector("[data-testid=wo-created]", { timeout: 25000 })
    assert.match(await page.locator("[data-testid=wo-created]").innerText(), /Создал:\s*Тестов Админ Иванович/)
    assert.match(await page.locator("[data-testid=wo-updated]").innerText(), /Изменил:\s*Тестов Админ Иванович/)
    assert.match(await page.locator("[data-testid=wo-plan]").innerText(), /\(4 ч\)/)
    assert.match(await page.locator("[data-testid=wo-fact]").innerText(), /—\s*→\s*—/)
  })
  await check("no page errors in the console", async () => {
    const serious = errors.filter((t) => !/favicon|ERR_CERT|Failed to load resource|auth.refresh/i.test(t))
    assert.equal(serious.length, 0, serious.join(" | "))
  })
  await context.close()
}

{
  const { context, page } = await session({ width: 390, height: 844 })
  await check("phone width: the form does not scroll sideways", async () => {
    await openForm(page)
    await page.locator("[data-testid=wo-asset]").click()
    const x = await page.evaluate(async () => { window.scrollTo(2000, 0); await new Promise((r) => setTimeout(r, 150)); return window.scrollX })
    assert.equal(x, 0)
  })
  await context.close()
}

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
