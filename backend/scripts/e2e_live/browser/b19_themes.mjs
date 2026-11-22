// Real-browser (Edge): the two new light themes «Рассвет» (dawn) and «Сакура» (sakura): they apply, differ strongly, and hover / active colours
// change (and differ between the themes). Needs a temporary ZZTEST account in zztest_creds.json (key "admin").
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
await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
await page.locator("input[type=text]").first().fill(CREDS.admin.email)
await page.locator("input[type=password]").first().fill(CREDS.admin.password)
await page.locator("button[type=submit]").click()
await page.waitForURL(/dashboard/)
await page.goto(`${BASE}/dashboard/directories/assets`, { waitUntil: "networkidle" })
await page.waitForTimeout(2500)

const snap = {}
for (const theme of ["dawn", "sakura"]) {
  await check(`theme ${theme}: appears in the switcher and applies`, async () => {
    await page.getByLabel("Выбрать тему оформления").click()
    await page.getByRole("option", { name: theme === "dawn" ? /Рассвет/ : /Сакура/ }).click()
    await page.waitForTimeout(600)
    assert.equal(await page.evaluate(() => document.documentElement.getAttribute("data-theme")), theme)
    assert.equal(await page.evaluate(() => document.documentElement.classList.contains("dark")), false)
  })
  await check(`theme ${theme}: hover on a table row changes the colour`, async () => {
    const row = page.locator("tbody tr").nth(2)
    const before = await row.evaluate((e) => getComputedStyle(e).backgroundColor)
    await row.hover(); await page.waitForTimeout(400)
    const after = await row.evaluate((e) => getComputedStyle(e).backgroundColor)
    assert.notEqual(before, after, `${before} == ${after}`)
    snap[theme] = { rowHover: after }
  })
  await check(`theme ${theme}: hover on a sidebar link and the active link colour`, async () => {
    const links = page.locator("nav a")
    const link = links.filter({ hasText: "Весовая" }).first()
    const before = await link.evaluate((e) => getComputedStyle(e).backgroundColor)
    await link.hover(); await page.waitForTimeout(400)
    const after = await link.evaluate((e) => getComputedStyle(e).backgroundColor)
    assert.notEqual(before, after)
    const active = page.locator("a[aria-current=page]").first()
    snap[theme].navHover = after
    snap[theme].navActive = await active.evaluate((e) => getComputedStyle(e).backgroundImage)
    assert.ok(snap[theme].navActive.includes("gradient"), snap[theme].navActive)
  })
  await check(`theme ${theme}: primary button colour changes on hover`, async () => {
    const button = page.getByRole("button", { name: /Добавить ОС/ }).first()
    const before = await button.evaluate((e) => getComputedStyle(e).backgroundColor)
    await button.hover(); await page.waitForTimeout(400)
    const after = await button.evaluate((e) => getComputedStyle(e).backgroundColor)
    assert.notEqual(before, after)
    snap[theme].btn = before
  })
  await page.mouse.move(5, 5)
  await page.screenshot({ path: `${SC}/b19_${theme}.png` })
}
await check("the two themes differ: page, row hover, nav hover and button colours are all different", async () => {
  for (const k of ["rowHover", "navHover", "btn"]) assert.notEqual(snap.dawn[k], snap.sakura[k], k)
})
await check("the choice survives a reload", async () => {
  await page.reload({ waitUntil: "networkidle" })
  assert.equal(await page.evaluate(() => document.documentElement.getAttribute("data-theme")), "sakura")
})
await check("no page errors", async () => assert.deepEqual(errors, []))
await browser.close()
console.log(JSON.stringify(snap))
for (const [s, n] of results) console.log(`${s}  ${n}`)
const failed = results.filter(([s]) => s === "FAIL").length
console.log(failed ? `FAILED ${failed}` : `ALL PASS ${results.length}/${results.length}`)
process.exit(failed ? 1 : 0)
