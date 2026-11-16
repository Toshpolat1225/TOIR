// Real-browser (Edge) check of the HTTPS switch: the same build must work over http:// and https://.
import { chromium } from "playwright-core"
import { readFileSync } from "node:fs"
import assert from "node:assert/strict"

const SC = "C:/Users/okmkh/AppData/Local/Temp/claude/2aa746e9242978ee/ad828521-7e36-4458-a5d2-d41bd40096be/scratchpad"
const CREDS = JSON.parse(readFileSync(`${SC}/zztest_creds.json`, "utf-8"))
const HOST = "192.168.28.104"
const results = []
const check = async (name, fn) => { try { await fn(); results.push(["PASS", name]) } catch (e) { results.push(["FAIL", `${name}: ${String(e.message).split("\n")[0]}`]) } }
const browser = await chromium.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true })

for (const scheme of ["https", "http"]) {
  const base = `${scheme}://${HOST}`
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", ignoreHTTPSErrors: true })
  const page = await context.newPage()
  const apiUrls = []
  const sockets = []
  const consoleErrors = []
  page.on("request", (r) => { if (r.url().includes("/api/v1/")) apiUrls.push(r.url()) })
  page.on("websocket", (ws) => sockets.push(ws.url()))
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 160)) })

  await page.goto(`${base}/auth/login`, { waitUntil: "networkidle" })
  await page.locator("input[type=text]").first().fill(CREDS.admin.email)
  await page.locator("input[type=password]").first().fill(CREDS.admin.password)
  await page.locator("button[type=submit]").click()
  await check(`${scheme}: login leads to the dashboard`, async () => { await page.waitForURL(/dashboard/, { timeout: 20000 }) })
  await page.waitForTimeout(3000) // the dashboard home page opens the realtime socket
  const socketsOnHome = [...sockets]
  await page.goto(`${base}/dashboard/maintenance`, { waitUntil: "networkidle" })
  await page.waitForTimeout(1500)

  await check(`${scheme}: every API call goes to the page's own origin (relative /api/v1), none to localhost`, async () => {
    assert.ok(apiUrls.length > 0, "no API calls seen")
    const bad = apiUrls.filter((u) => !u.startsWith(`${base}/api/v1/`))
    assert.equal(bad.length, 0, `foreign: ${bad.slice(0, 2).join(",")}`)
  })
  await check(`${scheme}: the realtime socket uses ${scheme === "https" ? "wss" : "ws"}:// on the same host`, async () => {
    assert.ok(socketsOnHome.length > 0, "no websocket opened on the dashboard home page")
    assert.ok(sockets.every((u) => u === `${scheme === "https" ? "wss" : "ws"}://${HOST}/ws`), sockets.join(","))
  })
  await check(`${scheme}: the maintenance page loaded without an error banner`, async () => {
    const text = await page.locator("body").innerText()
    assert.ok(!text.includes("Не удалось загрузить график"), "schedule error banner shown")
    assert.ok(text.length > 500, "page looks empty")
  })
  await check(`${scheme}: the refresh cookie flags are right in the browser`, async () => {
    const cookie = (await context.cookies()).find((c) => c.name === "toir_refresh_token")
    assert.ok(cookie, "no refresh cookie")
    assert.equal(cookie.httpOnly, true)
    assert.equal(cookie.secure, scheme === "https")
  })
  await check(`${scheme}: a page reload keeps the session (refresh cookie round-trip)`, async () => {
    await page.reload({ waitUntil: "networkidle" })
    await page.waitForTimeout(800)
    assert.match(new URL(page.url()).pathname, /^\/dashboard/)
  })
  await check(`${scheme}: no console errors about mixed content / CORS / sockets`, async () => {
    const serious = consoleErrors.filter((t) => /mixed|CORS|blocked|WebSocket|ERR_/i.test(t))
    assert.equal(serious.length, 0, serious.join(" | "))
  })
  await context.close()
}

// Does THIS Windows machine already trust the Caddy root certificate? (information, not a defect)
{
  const context = await browser.newContext({ ignoreHTTPSErrors: false })
  const page = await context.newPage()
  let trusted = true
  try { await page.goto(`https://${HOST}/auth/login`, { waitUntil: "domcontentloaded", timeout: 15000 }) } catch (e) { trusted = false }
  results.push(["INFO", `this PC's Edge ${trusted ? "TRUSTS" : "does NOT trust yet"} the Caddy root certificate (install toir-local-root.crt on client PCs to remove the warning)`])
  await context.close()
}

console.log(results.map(([r, n]) => `${r}  ${n}`).join("\n"))
console.log(`\n${results.filter(([r]) => r === "PASS").length} passed, ${results.filter(([r]) => r === "FAIL").length} failed`)
await browser.close()
process.exit(results.some(([r]) => r === "FAIL") ? 1 : 0)
