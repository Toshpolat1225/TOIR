import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  axisTicks, deltaPercent, deltaText, deltaTone, dayFraction, durationMinutes, fillRatio, locoHref, parseWagonKey, percent, postColor,
  sinceServiceText, tonnesCompact, trainHref, wagonHref, wagonKey,
} from "./scales-insights.ts"

describe("scales insights helpers", () => {
  it("writes big tonnage compactly", () => {
    assert.equal(tonnesCompact(null), "—")
    assert.match(tonnesCompact(950).replace(/\s/g, " "), /^950 т$/)
    assert.match(tonnesCompact(12400), /^12,4 тыс\. т$/)
    assert.match(tonnesCompact("1250000"), /^1,25 млн т$/)
    assert.equal(percent(0.876), "87,60%")
    assert.equal(percent(null), "—")
  })

  it("compares with the previous period", () => {
    assert.equal(deltaPercent(120, 100), 20)
    assert.equal(deltaPercent("80", "100"), -20)
    assert.equal(deltaPercent(5, 0), null)
    assert.equal(deltaText(20), "+20,00% к прошлому периоду")
    assert.equal(deltaText(-7.4), "-7,40% к прошлому периоду")
    assert.equal(deltaText(null), "нет базы сравнения")
    assert.deepEqual([deltaTone(null), deltaTone(0.4), deltaTone(5), deltaTone(-5)], ["flat", "flat", "up", "down"])
  })

  it("builds links for linked and unlinked wagons", () => {
    assert.equal(wagonKey({ asset_id: "abc", carriage_gtk_id: 7 }), "abc")
    assert.equal(wagonKey({ asset_id: null, carriage_gtk_id: 7 }), "gtk-7")
    assert.equal(wagonHref({ asset_id: null, carriage_gtk_id: 7 }), "/dashboard/scales/wagon/gtk-7")
    assert.deepEqual(parseWagonKey("gtk-7"), { carriage_gtk_id: 7 })
    assert.deepEqual(parseWagonKey("0b6c1f2e-1111-2222-3333-444455556666"), { asset_id: "0b6c1f2e-1111-2222-3333-444455556666" })
    assert.equal(locoHref("L1"), "/dashboard/scales/loco/L1")
    assert.equal(trainHref("T1"), "/dashboard/scales/train/T1")
  })

  it("computes chart geometry", () => {
    assert.equal(fillRatio(52.5), 0.5)
    assert.ok(fillRatio(110) > 1)
    assert.equal(fillRatio(null), 0)
    assert.equal(postColor("97", ["93", "97"]), "#f59e0b")
    assert.equal(durationMinutes("2026-11-17T08:00:00Z", "2026-11-17T08:12:30Z"), 13)
    assert.equal(durationMinutes(null, "2026-11-17T08:00:00Z"), null)
    assert.equal(dayFraction(null), null)
    const f = dayFraction(new Date(2026, 10, 17, 12, 0, 0).toISOString())
    assert.ok(f !== null && Math.abs(f - 0.5) < 0.001)
  })

  it("thins long axes", () => {
    const items = Array.from({ length: 30 }, (_, i) => i)
    assert.ok(axisTicks(items, 8).length <= 8)
    assert.deepEqual(axisTicks([1, 2, 3], 8), [1, 2, 3])
  })

  it("explains the work since the last service", () => {
    assert.match(sinceServiceText({ last_service_at: null, trips_since: 0, tonnes_since: 0 }), /введите «последнее ТО»/)
    assert.match(sinceServiceText({ last_service_at: "2026-11-01", trips_since: 40, tonnes_since: 4200 }).replace(/\s/g, " "), /40 рейсов, 4 200 т/)
  })
})
