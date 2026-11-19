// Real-browser (Edge) check of the repair-type directory: the standard duration is shown, editable inline and survives a reload.
// Needs a repair type with code UI-ТР-1 and no duration (the rehearsal seed). Env: TOIR_BASE, TOIR_CREDS. It changes that type's duration.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const BASE = process.env.TOIR_BASE ?? "https://192.168.28.104"
const CREDS = JSON.parse(readFileSync(process.env.TOIR_CREDS, "utf-8"))
const CODE = process.env.TOIR_TYPE_CODE ?? "UI-ТР-1"
const results = []
process.on("unhandledRejection", (e) => { if (!/Target page, context or browser has been closed/.test(String(e?.message))) throw e })
const check = async (name, fn) => { console.error("> " + name); try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0]}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const page = await context.newPage()
await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await page.locator("input[type=text]").first().fill(CREDS.email)
await page.locator("input[type=password]").first().fill(CREDS.password)
await page.locator("button[type=submit]").click()
await page.waitForURL(/dashboard/)

const card = () => page.locator("div.rounded-xl", { has: page.locator(`span:text-is('${CODE}')`) }).first()
const open = async () => {
  await page.goto(`${BASE}/dashboard/directories/work-types`, { waitUntil: "networkidle" })
  await card().waitFor({ timeout: 25000 })
}

await open()
await check("a type without duration is flagged and has an editor when expanded", async () => {
  assert.match(await card().locator("[data-testid=wt-duration-badge]").innerText(), /время не задано/)
  await card().locator(`span:text-is('${CODE}')`).click()
  await card().locator("[data-testid=wt-duration-input]").waitFor({ timeout: 10000 })
})
await check("saving a duration updates the badge", async () => {
  await card().locator("[data-testid=wt-duration-input]").fill("3,5")
  await card().locator("[data-testid=wt-duration-save]").click()
  await page.waitForFunction((c) => [...document.querySelectorAll("[data-testid=wt-duration-badge]")].some((n) => n.textContent.includes("3,5 ч")), CODE, { timeout: 10000 })
})
await check("the duration is kept after a reload; a bad value is refused", async () => {
  await open()
  assert.match(await card().locator("[data-testid=wt-duration-badge]").innerText(), /3,5 ч/)
  await card().locator(`span:text-is('${CODE}')`).click()
  await card().locator("[data-testid=wt-duration-input]").fill("-2")
  await card().locator("[data-testid=wt-duration-save]").click()
  await card().getByRole("alert").waitFor({ timeout: 10000 })
  assert.match(await card().locator("[data-testid=wt-duration-badge]").innerText(), /3,5 ч/)
})
await check("the add form takes a duration", async () => {
  await open()
  await page.getByRole("button", { name: /Добавить/ }).first().click()
  await page.locator("[data-testid=wt-add-duration]").waitFor({ timeout: 10000 })
})
await context.close()
console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
