// Real browser (Edge) against the LIVE frontend + API with the ZZTEST accounts. Visits every page as every role.
import { chromium } from "playwright-core"
import { readFileSync, appendFileSync, mkdirSync } from "node:fs"

const SC = "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/ad828521-7e36-4458-a5d2-d41bd40096be/scratchpad"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const BASE = "http://192.168.28.104"
const OUT = `${SC}/shots/live`
mkdirSync(OUT, { recursive: true })
const PAGES = [
  "/dashboard", "/dashboard/maintenance", "/dashboard/work-orders", "/dashboard/directories", "/dashboard/directories/assets",
  "/dashboard/directories/asset-catalogs", "/dashboard/directories/conflicts", "/dashboard/directories/employees",
  "/dashboard/directories/maintenance-intervals", "/dashboard/directories/sections", "/dashboard/directories/work-types",
  "/dashboard/os/gtk", "/dashboard/os/wialon", "/dashboard/reports", "/dashboard/tmc", "/dashboard/analytics",
  "/dashboard/admin/users", "/dashboard/admin/users/permissions", "/dashboard/admin/audit-logs",
]
const roles = process.argv.slice(2).length ? process.argv.slice(2) : ["admin", "operator", "master", "management"]
const log = (row) => appendFileSync(`${SC}/browser_results.jsonl`, JSON.stringify(row) + "\n")
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })

for (const role of roles) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU" })
  const page = await context.newPage()
  const problems = []
  const failed = []
  page.on("pageerror", (e) => problems.push(`pageerror: ${String(e).slice(0, 160)}`))
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) problems.push(`console: ${m.text().slice(0, 160)}`) })
  page.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) failed.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`) })
  const t0 = Date.now()
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" })
  await page.locator("input[type=text]").first().fill(CREDS[role].email)
  await page.locator("input[type=password]").first().fill(CREDS[role].password)
  await page.locator("button[type=submit]").click()
  try {
    await page.waitForURL(/\/dashboard/, { timeout: 20000 })
    log({ role, page: "LOGIN", ok: true, ms: Date.now() - t0 })
    console.log(`${role}: logged in via the UI in ${Date.now() - t0} ms`)
  } catch {
    const msg = (await page.locator("body").innerText()).slice(0, 200).replace(/\s+/g, " ")
    log({ role, page: "LOGIN", ok: false, detail: msg })
    console.log(`${role}: LOGIN FAILED -> ${msg}`)
    await context.close()
    continue
  }
  const nav = await page.locator("nav a, aside a").evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute("href")).filter(Boolean))])
  log({ role, page: "NAV", links: nav })
  console.log(`${role}: sidebar links = ${nav.filter((h) => h.startsWith("/dashboard")).length}`)
  for (const path of PAGES) {
    problems.length = 0
    failed.length = 0
    const started = Date.now()
    let status = "ok"
    try {
      const resp = await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 45000 })
      status = String(resp?.status() ?? "?")
    } catch (e) {
      status = `nav-error: ${String(e).slice(0, 80)}`
    }
    await page.waitForTimeout(400)
    const ms = Date.now() - started
    const final = new URL(page.url()).pathname
    const text = (await page.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ")
    const crashed = /Application error|Unhandled Runtime Error|Internal Server Error|Something went wrong|Произошла ошибка|Ошибка приложения/i.test(text)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    const h1 = await page.locator("h1").count()
    const row = { role, page: path, status, final: final === path ? undefined : final, ms, crashed, overflow: overflow > 4 ? overflow : 0, h1, problems: [...problems], failed: [...new Set(failed)], chars: text.length }
    log(row)
    const flag = crashed || problems.length || failed.length || (final !== path)
    console.log(`${flag ? "!!" : "ok"} ${role.padEnd(10)} ${path.padEnd(46)} ${String(ms).padStart(5)}ms ${final !== path ? "-> " + final + " " : ""}${crashed ? "CRASH " : ""}${failed.length ? [...new Set(failed)].join(",") + " " : ""}${problems.length ? problems[0] : ""}`)
    if (role === "admin") await page.screenshot({ path: `${OUT}/${path.replace(/\W+/g, "_")}.png` })
  }
  // mobile width of the busiest pages
  await page.setViewportSize({ width: 390, height: 844 })
  for (const path of ["/dashboard", "/dashboard/maintenance", "/dashboard/directories/assets", "/dashboard/work-orders"]) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 45000 }).catch(() => {})
    await page.waitForTimeout(400)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    log({ role, page: `${path} @390px`, overflow: overflow > 4 ? overflow : 0 })
    console.log(`${overflow > 4 ? "!!" : "ok"} ${role.padEnd(10)} ${path.padEnd(46)} mobile 390px overflow=${overflow > 4 ? overflow + "px" : "none"}`)
  }
  await context.close()
}
await browser.close()
