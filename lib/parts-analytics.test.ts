// Run with: npm run test:unit
import assert from "node:assert/strict"
import { describe, it } from "node:test"
import { coverageText, daysText, forecastConclusion, partsErrorHint, stockCounts, stockCoverDays, stockConclusion, trendView } from "./parts-analytics.ts"
import type { RepairForecast } from "./api.ts"

const norm = (s: string) => s.replace(/[  ]/g, " ")

describe("parts analytics helpers", () => {
  it("error hints", () => {
    assert.match(partsErrorHint(403), /Нет прав/)
    assert.match(partsErrorHint(404), /Участок/)
    assert.match(partsErrorHint(500, "boom"), /boom/)
  })
  it("days text", () => {
    assert.equal(daysText(null), "—")
    assert.equal(daysText(0), "сегодня")
    assert.equal(norm(daysText(-3)), "просрочено 3 дн.")
    assert.equal(daysText(5), "5 дн.")
  })
  it("counts and cover", () => {
    assert.deepEqual(stockCounts([{ status: "ok" }, { status: "ok" }, { status: "critical" }]), { critical: 1, order_now: 0, ok: 2, no_data: 0 })
    assert.equal(stockCoverDays({ status: "no_data", runs_out_in_days: 4 }), null)
    assert.equal(stockCoverDays({ status: "ok", runs_out_in_days: 40 }), 40)
  })
  it("coverage chip", () => {
    assert.equal(coverageText({ covers: true }, "шт"), "хватает")
    assert.equal(coverageText(undefined, "шт"), "нет данных")
    assert.match(norm(coverageText({ covers: false, shortfall_qty: 90, shortfall_cost: 378000 }, "шт")), /не хватает 90,0 шт · 378,000 тыс/)
  })
  it("trend", () => {
    assert.equal(trendView(null, null).arrow, "")
    assert.equal(trendView("up", 12.5).text, "+12,50%")
  })
  it("conclusions", () => {
    const f = { summary: { planned: 5, projected: 10, overdue: 2, total: 15, by_asset_type: { locomotive: 3, diesel: 2, wagon: 10 }, by_age: { new: 1, middle: 4, old: 10, unknown: 0 } } } as RepairForecast
    const text = norm(forecastConclusion(f, "Год"))
    assert.match(text, /15 ремонтов/)
    assert.match(text, /Просрочено уже сейчас: 2/)
    assert.match(stockConclusion({ critical: 0, order_now: 0, shortfall_cost_quarter: 0 }), /не требуется/)
  })
})
