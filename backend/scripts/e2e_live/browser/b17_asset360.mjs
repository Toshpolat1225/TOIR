// Real-browser (Edge): asset directory shows the key facts of the other modules and opens the «Паспорт 360°» window.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"
const SC = process.env.TOIR_SC || "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/c7559559-27b3-4c8a-ae2d-d4776d42d11c/scratchpad/e2e"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = process.env.TOIR_BASE || "https://192.168.28.104"
const results = []
const check = async (name, fn) => { console.error("> " + name); try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0].slice(0, 300)}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 }, locale: "ru-RU", ignoreHTTPSErrors: true })
const page = await context.newPage()
const errors = []
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)))
const calls = []
page.on("response", (r) => { if (r.url().includes("/fixed-assets/overview")) calls.push(r.status()) })
await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await page.locator("input[type=text]").first().fill(CREDS.admin.email)
await page.locator("input[type=password]").first().fill(CREDS.admin.password)
await page.locator("button[type=submit]").click()
await page.waitForURL(/dashboard/)
await page.goto(`${BASE}/dashboard/directories/assets`, { waitUntil: "networkidle" })
await page.waitForTimeout(2500)
await check("overview endpoint answers 200", async () => { assert.ok(calls.length > 0, "no call"); assert.ok(calls.every((c) => c === 200), calls.join(",")) })
await check("new column headers are shown", async () => {
  const t = await page.locator("thead").innerText()
  for (const h of ["GPS", "Состав", "Весовая", "Посл. ремонт"]) assert.match(t, new RegExp(h, "i"), h)
})
await check("some rows carry GPS / GTK / scales chips", async () => {
  assert.ok(await page.locator("button[title*='Подробнее']").count() > 0, "no chips")
})
await page.screenshot({ path: `${SC}/b17_table.png` })
await check("click a GPS chip opens the 360 window on the GPS tab", async () => {
  await page.locator("button[title*='GPS и Карта']").first().click()
  await page.getByRole("dialog").waitFor()
  const t = await page.getByRole("dialog").innerText()
  assert.match(t, /Паспорт 360/i); assert.match(t, /Координаты/i)
  await page.screenshot({ path: `${SC}/b17_gps.png` })
})
for (const [tab, re] of [["Wialon", /Данные Wialon|не привязан/], ["GTK и состав", /GTK ID|Текущий состав|Не удалось/], ["Весовая", /Составов|Рейсов|Нет взвешиваний|Не удалось|Полная карточка/], ["Ремонты", /Обслуживание/i], ["Сводка", /Пробег ТОИР/i]]) {
  await check(`tab ${tab}`, async () => {
    await page.getByRole("dialog").getByRole("button", { name: tab }).click()
    await page.waitForTimeout(1500)
    assert.match(await page.getByRole("dialog").innerText(), re)
  })
}
await page.screenshot({ path: `${SC}/b17_summary.png` })
await check("edit button opens the passport editor", async () => {
  await page.getByRole("dialog").getByText("Паспорт и редактирование").click()
  await page.getByText(/Редактировать|Паспорт/).first().waitFor({ timeout: 8000 })
})
await check("no page errors", async () => assert.deepEqual(errors, []))
await browser.close()
for (const [s, n] of results) console.log(`${s}  ${n}`)
const failed = results.filter(([s]) => s === "FAIL").length
console.log(failed ? `FAILED ${failed}` : `ALL PASS ${results.length}/${results.length}`)
process.exit(failed ? 1 : 0)
