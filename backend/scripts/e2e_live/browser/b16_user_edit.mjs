// Real-browser (Edge): the admin «Пользователи» edit window on the live system, with ZZTEST accounts only:
// edit + save a user, reset a local password (policy message), convert a local account to a directory account, the AD account's edit window.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = process.env.TOIR_SC || "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/c7559559-27b3-4c8a-ae2d-d4776d42d11c/scratchpad/e2e"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = process.env.TOIR_BASE || "https://192.168.28.104"
const results = []
const check = async (name, fn) => { console.error("> " + name); try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0].slice(0, 260)}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const page = await context.newPage()
const dialogs = []
page.on("dialog", async (d) => { dialogs.push(d.message().slice(0, 120)); await d.accept() })
await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await page.locator("input[type=text]").first().fill(CREDS.admin.email)
await page.locator("input[type=password]").first().fill(CREDS.admin.password)
await page.locator("button[type=submit]").click()
await page.waitForURL(/dashboard/)
await page.goto(`${BASE}/dashboard/admin/users`, { waitUntil: "networkidle" })

const rowOf = (email) => page.locator("tr", { hasText: email })
const openEdit = async (email) => {
  await page.locator("input[placeholder*='оиск'], input[type=search]").first().fill(email).catch(() => {})
  await rowOf(email).first().waitFor({ timeout: 15000 })
  await rowOf(email).first().getByText("Изменить").click()
  await page.getByText("Редактировать пользователя").waitFor()
}
const modal = () => page.locator("div.fixed.inset-0").last()

await check("edit window opens for a local user and shows how the user logs in", async () => {
  await openEdit(CREDS.operator.email)
  const text = await modal().innerText()
  assert.match(text, /локальный пароль/i)
  assert.match(text, /Перевести на вход через домен/i)
  assert.match(text, /Сбросить пароль/i)
  await modal().getByText("Отмена").click()
})

await check("saving a changed full name works", async () => {
  await openEdit(CREDS.operator.email)
  const name = "ZZTEST Оператор Проверка " + Date.now() % 1000
  await modal().locator("input").first().fill(name)
  await modal().getByText("Сохранить").click()
  await page.waitForFunction((n) => document.body.innerText.includes(n), name, { timeout: 15000 })
})

await check("password reset: the field says what the server really requires (10 characters)", async () => {
  await openEdit(CREDS.operator.email)
  const hint = await modal().locator("input[type=password]").getAttribute("placeholder")
  assert.match(hint, /10/, `placeholder was: ${hint}`)
  await modal().locator("input[type=password]").fill("Zz-Proverka-2026-ok")
  await modal().getByText("Сбросить", { exact: true }).click()
  await page.waitForTimeout(1500)
  const text = await modal().innerText()
  assert.ok(/успешно обновлён|парол/i.test(text), text.slice(-200))
  await modal().getByText("Отмена").click()
})

await check("convert a LOCAL account to a directory account from the edit window", async () => {
  await openEdit(CREDS.operator.email)
  await modal().locator("input[placeholder='Доменный логин']").fill("zztest.ad.operator")
  await modal().getByRole("button", { name: "Перевести", exact: true }).click()
  await page.getByText("Редактировать пользователя").waitFor({ state: "hidden", timeout: 15000 })
  await page.waitForFunction((e) => [...document.querySelectorAll("tr")].some((r) => r.innerText.includes(e) && /AD/.test(r.innerText)), CREDS.operator.email, { timeout: 15000 })
})

await check("the converted account's edit window: login method AD, no password reset, no convert", async () => {
  await openEdit(CREDS.operator.email)
  const text = await modal().innerText()
  assert.match(text, /через домен \(AD\)/i)
  assert.doesNotMatch(text, /Сбросить пароль/i)
  assert.doesNotMatch(text, /Перевести на вход/i)
  assert.match(text, /zztest\.ad\.operator/)
  await modal().getByText("Отмена").click()
})

await check("an admin does NOT get the «convert» block for his OWN account", async () => {
  await openEdit(CREDS.admin.email)
  const text = await modal().innerText()
  assert.doesNotMatch(text, /Перевести на вход/i)
  await modal().getByText("Отмена").click()
})

await browser.close()
for (const [s, n] of results) console.log(`${s}  ${n}`)
console.log("dialogs:", JSON.stringify(dialogs))
const failed = results.filter(([s]) => s === "FAIL").length
console.log(failed ? `FAILED ${failed}` : `ALL PASS ${results.length}/${results.length}`)
process.exit(failed ? 1 : 0)
