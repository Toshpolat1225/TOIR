// Browser regression of the frontend fixes on the live system (ZZTEST accounts and the ZZTEST interval only).
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/ad828521-7e36-4458-a5d2-d41bd40096be/scratchpad"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = "http://192.168.28.104"
const results = []
const check = async (name, fn) => { try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0]}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })

async function session(role, viewport = { width: 1440, height: 900 }) {
  const context = await browser.newContext({ viewport, locale: "ru-RU" })
  const page = await context.newPage()
  const requests = []
  page.on("request", (r) => { if (r.url().includes("/api/v1/")) requests.push(new URL(r.url()).pathname) })
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await page.locator("input[type=text]").first().fill(CREDS[role].email)
  await page.locator("input[type=password]").first().fill(CREDS[role].password)
  await page.locator("button[type=submit]").click()
  await page.waitForURL(/dashboard/)
  return { context, page, requests }
}

// operator typing admin addresses: redirected, nothing rendered, no request that would answer 403
{
  const { context, page, requests } = await session("operator")
  for (const path of ["/dashboard/admin/users", "/dashboard/admin/audit-logs", "/dashboard/admin/users/permissions"]) {
    requests.length = 0
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" })
    await page.waitForTimeout(500)
    await check(`operator at ${path}: sent home without calling the restricted API`, async () => {
      assert.equal(new URL(page.url()).pathname, "/dashboard")
      assert.ok(!requests.some((p) => /\/users$|\/audit-logs/.test(p)), `requests: ${requests.join(",")}`)
    })
  }
  await context.close()
}

// admin keeps access to them
{
  const { context, page } = await session("admin")
  await page.goto(`${BASE}/dashboard/admin/audit-logs`, { waitUntil: "networkidle" })
  await check("admin still opens the audit log", async () => assert.equal(new URL(page.url()).pathname, "/dashboard/admin/audit-logs"))

  // the interval directory can now edit the living-plan fields
  await page.goto(`${BASE}/dashboard/directories/maintenance-intervals`, { waitUntil: "networkidle" })
  const row = page.locator("tr", { hasText: "ZZTEST-I1" }).first()
  await check("the ZZTEST interval is listed with its rank", async () => assert.match(await row.innerText(), /ранг 1/))
  await row.getByRole("button", { name: "Редактировать" }).click()
  await page.waitForTimeout(400)
  const body = await page.locator("body").innerText()
  for (const label of ["Интервал (моточасы)", "Ранг (старший перекрывает младшие)", "Допуск сверх лимита (%)", "Упреждение планирования"]) {
    await check(`the interval form has «${label}»`, async () => assert.ok(body.includes(label), "label missing"))
  }
  await check("a rank outside 1-99 is refused in the form", async () => {
    const rank = page.getByLabel(/Ранг/)
    await rank.fill("120")
    await page.getByRole("button", { name: /Сохранить/ }).first().click()
    await page.waitForTimeout(300)
    assert.match(await page.locator("body").innerText(), /Ранг — целое число от 1 до 99/)
    await rank.fill("3")
  })
  await check("saving stores the new rank", async () => {
    await page.getByRole("button", { name: /Сохранить/ }).first().click()
    await page.waitForTimeout(800)
    assert.match(await page.locator("tr", { hasText: "ZZTEST-I1" }).first().innerText(), /ранг 3/)
  })
  await context.close()
}

// phone width: no sideways scrolling on the three pages that had it
{
  const { context, page } = await session("admin", { width: 390, height: 844 })
  for (const path of ["/dashboard/maintenance", "/dashboard/directories/assets", "/dashboard/work-orders", "/dashboard/directories/maintenance-intervals"]) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" })
    await page.waitForTimeout(400)
    await check(`phone width: ${path} does not scroll sideways`, async () => {
      const over = await page.evaluate(async () => { window.scrollTo(2000, 0); await new Promise((r) => setTimeout(r, 150)); return window.scrollX })
      assert.equal(over, 0, `scrolls ${over}px`)
    })
  }
  await context.close()
}
console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
