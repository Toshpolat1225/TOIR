// Run with: npm run test:unit   (Node built-in test runner, no extra dependencies)
import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  buildCsv, clampShift, compareEnriched, csvCell, diffDaysIso, enrich, equipmentSubtitle, equipmentTitle,
  formatDate, groupByUnit, intervalCode, intervalKind, intervalTitle, inventoryNumberOf, isInRange,
  isReschedulable, isTestInterval, paletteForCode, parseDate, progressPct, recommend, rescheduleImpact,
  shiftDate, shiftFromPixels, toIsoDate, validateRescheduleDate, type Enriched, type ScheduleItem,
  canBlock, canSetBaseline, canUnblock, canWaive, markerTimeline, paceOf, paceText, parseKmInput,
  priorityTone, validateBaselineDate,
} from "./maintenance-view.ts"

const base: ScheduleItem = {
  id: "1", entity_type: "forecast", unit: "ТЭМ2 3145 · 38700", type: "ТО-1 — ТО-1", startDate: "2026-11-20",
  durationH: 8, depot: "", tech: "", status: "upcoming", urgency: null, note: null, mileage: null,
  remainingKm: null, nextThreshold: null, intervalKm: null, asset_id: "a1", section_id: null,
  interval_id: null, work_type_id: null, plan_id: null, work_order_id: null,
}
const make = (over: Partial<ScheduleItem>): ScheduleItem => ({ ...base, ...over })
const entry = (over: Partial<ScheduleItem>, dailyKm: number | null = 200): Enriched => enrich(make(over), dailyKm)

describe("progressPct", () => {
  it("measures progress inside the current interval, not against the absolute odometer", () => {
    // 7300 km on a 5000 km interval: threshold 10000, 2700 km left -> 46 %, not 73 %
    assert.equal(Math.round(progressPct(7300, 10000, 5000, 2700) as number), 46)
  })
  it("falls back to mileage/threshold when the interval length is unknown", () => {
    assert.equal(Math.round(progressPct(716, 900, null, 184) as number), 80)
  })
  it("never goes below zero and is null without data", () => {
    assert.equal(progressPct(1, 10, 5, 99), 0)
    assert.equal(progressPct(null, null, null, null), null)
  })
  it("exceeds 100 when the threshold is overrun", () => {
    assert.equal(Math.round(progressPct(5100, 5000, 5000, -100) as number), 102)
  })
})

describe("enrich", () => {
  it("computes days left with the daily average, rounding up", () => {
    assert.equal(entry({ mileage: 716, remainingKm: 184, nextThreshold: 900, intervalKm: 900 }).daysLeft, 1)
    assert.equal(entry({ mileage: 100, remainingKm: 401, nextThreshold: 501, intervalKm: 501 }).daysLeft, 3)
  })
  it("has no days left when overdue in km or when no daily average is configured", () => {
    assert.equal(entry({ mileage: 950, remainingKm: -50, nextThreshold: 900 }).daysLeft, null)
    assert.equal(entry({ mileage: 100, remainingKm: 400, nextThreshold: 500 }, null).daysLeft, null)
  })
})

describe("recommend", () => {
  const rec = (over: Partial<ScheduleItem>) => entry(over).rec
  it("flags an overrun threshold as critical with the exact overrun", () => {
    const r = rec({ mileage: 950, remainingKm: -50, nextThreshold: 900, intervalKm: 900 })
    assert.equal(r.level, "critical")
    assert.match(r.text, /Порог превышен на 50 км/)
  })
  it("warns from 90 % of the interval, plans ahead from 70 %, otherwise ok", () => {
    assert.equal(rec({ mileage: 4600, remainingKm: 400, nextThreshold: 5000, intervalKm: 5000 }).level, "warning")
    assert.equal(rec({ mileage: 3800, remainingKm: 1200, nextThreshold: 5000, intervalKm: 5000 }).level, "info")
    assert.equal(rec({ mileage: 500, remainingKm: 4500, nextThreshold: 5000, intervalKm: 5000 }).level, "ok")
  })
  it("warns about missing mileage data and reports work-order states", () => {
    assert.equal(rec({ mileage: null }).level, "warning")
    assert.equal(rec({ entity_type: "work_order", status: "overdue" }).level, "critical")
    assert.equal(rec({ entity_type: "work_order", status: "completed" }).level, "ok")
    assert.equal(rec({ entity_type: "work_order", status: "in_progress" }).level, "info")
  })
  it("uses the plan date for date-based intervals and escalates when it has passed", () => {
    assert.match(rec({ mileage: 10, remainingKm: null, startDate: "2026-12-05" }).text, /05\.12\.2026/)
    assert.equal(rec({ mileage: 10, remainingKm: null, status: "overdue" }).level, "critical")
  })
  it("recommend() is usable directly", () => {
    assert.equal(recommend(make({ status: "completed" }), 1, 1, 1, 1).level, "ok")
  })
})

describe("sorting", () => {
  const rows = [
    entry({ id: "a", unit: "A · 1", mileage: 100 }),
    entry({ id: "b", unit: "B · 2", mileage: 300 }),
    entry({ id: "c", unit: "C · 3", mileage: null }),
    entry({ id: "d", unit: "D · 4", mileage: 200 }),
  ]
  const order = (key: "mileage" | "unit", dir: "asc" | "desc") =>
    [...rows].sort((x, y) => compareEnriched(x, y, key, dir)).map((e) => e.item.id).join("")

  it("puts the largest mileage first and empty mileage always last", () => {
    assert.equal(order("mileage", "desc"), "bdac")
    assert.equal(order("mileage", "asc"), "adbc")
  })
  it("sorts names with the Russian collation", () => {
    assert.equal(order("unit", "asc"), "abcd")
    assert.equal(order("unit", "desc"), "dcba")
  })
  it("breaks mileage ties by the interval that is due first", () => {
    const tied = [
      entry({ id: "far", mileage: 500, remainingKm: 4000, nextThreshold: 4500 }),
      entry({ id: "near", mileage: 500, remainingKm: 10, nextThreshold: 510 }),
    ].sort((x, y) => compareEnriched(x, y, "mileage", "desc"))
    assert.deepEqual(tied.map((e) => e.item.id), ["near", "far"])
  })
})

describe("groupByUnit", () => {
  const entries = [
    entry({ id: "a1", asset_id: "A", unit: "A · 1", type: "ТО-1", mileage: 500, remainingKm: 4500, nextThreshold: 5000, intervalKm: 5000 }),
    entry({ id: "a2", asset_id: "A", unit: "A · 1", type: "ТО-2", mileage: 500, remainingKm: -10, nextThreshold: 490, intervalKm: 1000 }),
    entry({ id: "a3", asset_id: "A", unit: "A · 1", type: "ТР-1", mileage: 500, remainingKm: 30000, nextThreshold: 30500, intervalKm: 30000 }),
    entry({ id: "b1", asset_id: "B", unit: "B · 2", type: "ТО-1", mileage: 900, remainingKm: 4100, nextThreshold: 5000, intervalKm: 5000 }),
    entry({ id: "c1", asset_id: "C", unit: "C · 3", type: "ТО-1", mileage: null }),
  ]

  it("makes one group per asset, largest mileage first, no data last", () => {
    const groups = groupByUnit(entries, "mileage", "desc")
    assert.deepEqual(groups.map((g) => g.key), ["B", "A", "C"])
  })
  it("picks the most urgent interval as the lead and lists intervals nearest-first", () => {
    const a = groupByUnit(entries, "mileage", "desc").find((g) => g.key === "A")!
    assert.equal(a.lead.item.id, "a2")
    assert.equal(a.level, "critical")
    assert.deepEqual(a.entries.map((e) => e.item.id), ["a2", "a1", "a3"])
  })
  it("keeps every interval of every unit", () => {
    const total = groupByUnit(entries, "unit", "asc").reduce((sum, g) => sum + g.entries.length, 0)
    assert.equal(total, entries.length)
  })
})

describe("isInRange", () => {
  const start = new Date(2026, 10, 1)
  const end = new Date(2026, 10, 30)
  it("shows overdue work whatever month is displayed", () => {
    assert.equal(isInRange(make({ status: "overdue", startDate: "2026-06-01" }), start, end, 1), true)
  })
  it("limits other work to the displayed month", () => {
    assert.equal(isInRange(make({ startDate: "2026-11-15" }), start, end, 1), true)
    assert.equal(isInRange(make({ startDate: "2026-12-15" }), start, end, 1), false)
    assert.equal(isInRange(make({ startDate: "" }), start, end, 1), false)
  })
})

describe("helpers", () => {
  it("formats and parses dates", () => {
    assert.equal(formatDate("2026-11-16"), "16.11.2026")
    assert.equal(formatDate("2026-11-16T10:00:00Z"), "16.11.2026")
    assert.equal(formatDate(""), "")
    assert.equal(parseDate("16.11.2026").getMonth(), 10)
    assert.equal(parseDate("2026-11-16").getDate(), 16)
  })
  it("extracts the inventory number and detects test intervals", () => {
    assert.equal(inventoryNumberOf(make({ unit: "ТЭМ2 3145 · 38700" })), "38700")
    assert.equal(isTestInterval(make({ type: "test — test" })), true)
    assert.equal(isTestInterval(make({ type: "ТО-1 — ТО-1" })), false)
  })
  it("neutralises spreadsheet formulas and escapes quotes in CSV", () => {
    assert.equal(csvCell("=SUM(A1)"), `"'=SUM(A1)"`)
    assert.equal(csvCell('say "hi"'), `"say ""hi"""`)
    assert.equal(csvCell(null), "")
    assert.equal(csvCell(12.5), `"12.5"`)
  })
  it("builds a BOM-prefixed, semicolon-separated CSV", () => {
    const csv = buildCsv(["a", "b"], [[1, "x;y"], [null, "z"]])
    assert.ok(csv.startsWith("﻿"))
    // an empty value is a truly empty cell, not a quoted empty string
    assert.equal(csv.slice(1), `"a";"b"\r\n"1";"x;y"\r\n;"z"`)
  })
})

describe("equipment naming", () => {
  const joined = {
    asset_model: "МПЭ-2у", asset_serial: "1", asset_type: "locomotive", asset_type_name: "Локомотив",
    asset_inv_number: "38390",
  }
  it("builds the title from model and factory number", () => {
    assert.equal(equipmentTitle(make(joined)), "МПЭ-2у №1")
    assert.equal(equipmentTitle(make({ ...joined, asset_serial: null })), "МПЭ-2у")
    assert.equal(equipmentTitle(make({ ...joined, asset_model: null })), "Локомотив №1")
  })
  it("falls back to the legacy label when the joined names are missing", () => {
    assert.equal(equipmentTitle(make({ unit: "ТЭМ2 3145 · 38700" })), "ТЭМ2 3145 · 38700")
  })
  it("builds the subtitle with the type name and the inventory number", () => {
    assert.equal(equipmentSubtitle(make(joined)), "Локомотив · Инв. № 38390")
    assert.equal(equipmentSubtitle(make({ asset_type: "diesel", unit: "x · 777" })), "diesel · Инв. № 777")
  })
})

describe("interval naming", () => {
  it("extracts the code and the full title", () => {
    assert.equal(intervalCode("ТО-1 — ТО-1"), "ТО-1")
    assert.equal(intervalTitle("ТО-2 — ТО-2"), "Техническое обслуживание №2")
    assert.equal(intervalTitle("КР — КР"), "Капитальный ремонт")
    assert.equal(intervalTitle("test — test"), "Тестовый интервал")
    assert.equal(intervalTitle("Что-то — иное"), "Что-то — иное")
  })
  it("classifies intervals for the icon", () => {
    assert.equal(intervalKind("ТО-3 — ТО-3"), "to")
    assert.equal(intervalKind("ТР-1 — ТР-1"), "tr")
    assert.equal(intervalKind("СР — СР"), "sr")
    assert.equal(intervalKind("КР — КР"), "kr")
    assert.equal(intervalKind("test — test"), "other")
  })
})

describe("date arithmetic", () => {
  it("shifts and diffs calendar days, also across month, year and daylight-saving boundaries", () => {
    assert.equal(shiftDate("2026-11-30", 1), "2026-12-01")
    assert.equal(shiftDate("2026-12-31", 1), "2027-01-01")
    assert.equal(shiftDate("2026-03-28", 3), "2026-03-31")
    assert.equal(diffDaysIso("2026-11-16", "2026-11-20"), 4)
    assert.equal(diffDaysIso("2026-11-20", "2026-11-16"), -4)
    assert.equal(diffDaysIso("2026-03-28", "2026-03-30"), 2) // DST change weekend in Europe
  })
  it("formats a local date without the UTC off-by-one", () => {
    assert.equal(toIsoDate(new Date(2026, 10, 16, 0, 30)), "2026-11-16")
    assert.equal(toIsoDate(new Date(2026, 10, 16, 23, 59)), "2026-11-16")
  })
})

describe("drag helpers", () => {
  it("turns pointer movement into whole days", () => {
    assert.equal(shiftFromPixels(100, 50), 2)
    assert.equal(shiftFromPixels(74, 50), 1)
    assert.equal(shiftFromPixels(-130, 50), -3)
    assert.equal(shiftFromPixels(20, 0), 0)
    assert.equal(shiftFromPixels(Number.NaN, 50), 0)
  })
  it("never lets a bar go before the minimum or after the maximum date", () => {
    assert.equal(clampShift("2026-11-20", -10, "2026-11-16", "2026-11-30"), -4)
    assert.equal(clampShift("2026-11-20", 25, "2026-11-16", "2026-11-30"), 10)
    assert.equal(clampShift("2026-11-20", 3, "2026-11-16", "2026-11-30"), 3)
  })
  it("lets an overdue bar (before the minimum) move only forward into the window", () => {
    assert.equal(clampShift("2026-11-10", -2, "2026-11-16", "2026-11-30"), 6)
    assert.equal(clampShift("2026-11-10", 9, "2026-11-16", "2026-11-30"), 9)
  })
})

describe("isReschedulable", () => {
  it("allows scheduled plans and forecasts, never work orders or running/finished plans", () => {
    assert.equal(isReschedulable(make({ entity_type: "forecast", interval_id: "i1" }), true), true)
    assert.equal(isReschedulable(make({ entity_type: "maintenance_plan", plan_id: "p1", status: "upcoming" }), true), true)
    assert.equal(isReschedulable(make({ entity_type: "maintenance_plan", plan_id: "p1", status: "overdue" }), true), true)
    assert.equal(isReschedulable(make({ entity_type: "maintenance_plan", plan_id: "p1", status: "in_progress" }), true), false)
    assert.equal(isReschedulable(make({ entity_type: "maintenance_plan", plan_id: "p1", status: "completed" }), true), false)
    assert.equal(isReschedulable(make({ entity_type: "work_order", status: "upcoming" }), true), false)
  })
  it("needs the right to update and the ids the API requires", () => {
    assert.equal(isReschedulable(make({ entity_type: "forecast", interval_id: "i1" }), false), false)
    assert.equal(isReschedulable(make({ entity_type: "forecast", interval_id: null }), true), false)
    assert.equal(isReschedulable(make({ entity_type: "maintenance_plan", plan_id: null, status: "upcoming" }), true), false)
  })
})

describe("validateRescheduleDate", () => {
  it("accepts today and the far boundary, rejects the past, the too distant and garbage", () => {
    assert.equal(validateRescheduleDate("2026-11-16", "2026-11-16"), null)
    assert.equal(validateRescheduleDate(shiftDate("2026-11-16", 366), "2026-11-16"), null)
    assert.match(validateRescheduleDate("2026-11-15", "2026-11-16") ?? "", /прошедшую/)
    assert.match(validateRescheduleDate(shiftDate("2026-11-16", 367), "2026-11-16") ?? "", /дальше/)
    assert.equal(validateRescheduleDate("", "2026-11-16"), "Укажите дату")
  })
})

describe("rescheduleImpact", () => {
  // 184 km to the threshold, 200 km per day: the system recommends tomorrow
  const item = make({ startDate: "2026-11-17", remainingKm: 184, nextThreshold: 900, mileage: 716 })
  const today = "2026-11-16"

  it("flags a later date that overruns the threshold, with the exact overrun", () => {
    const impact = rescheduleImpact(item, "2026-11-19", today, 200)
    assert.equal(impact.shiftDays, 2)
    assert.equal(impact.vsRecommendedDays, 2)
    assert.equal(impact.remainingAtNewKm, 184 - 600)
    assert.equal(impact.overrunKm, 416)
    assert.equal(impact.level, "danger")
  })
  it("treats an earlier date as safe but informs that part of the interval stays unused", () => {
    const impact = rescheduleImpact(item, "2026-11-16", today, 200)
    assert.equal(impact.vsRecommendedDays, -1)
    assert.equal(impact.overrunKm, 0)
    assert.equal(impact.level, "info")
  })
  it("is fine to keep the recommended date", () => {
    const impact = rescheduleImpact(item, "2026-11-17", today, 200)
    assert.equal(impact.level, "ok")
    assert.equal(impact.shiftDays, 0)
  })
  it("keeps reporting an overrun that already exists today, whatever date is chosen", () => {
    const over = make({ startDate: "2026-11-16", remainingKm: -50 })
    const impact = rescheduleImpact(over, "2026-11-16", today, 200)
    assert.equal(impact.overrunKm, 50)
    assert.equal(impact.level, "danger")
    assert.equal(rescheduleImpact(over, "2026-11-18", today, 200).overrunKm, 450)
  })
  it("cannot estimate kilometres without a daily average or without remaining km", () => {
    assert.equal(rescheduleImpact(item, "2026-11-25", today, null).overrunKm, 0)
    assert.equal(rescheduleImpact(item, "2026-11-25", today, null).remainingAtNewKm, null)
    assert.equal(rescheduleImpact(make({ startDate: "2026-11-17", remainingKm: null }), "2026-11-25", today, 200).level, "ok")
  })
  it("compares with the system recommendation, not with the previous manual date", () => {
    const manual = make({ startDate: "2026-11-20", dateManual: true, recommendedDate: "2026-11-17", remainingKm: 1000 })
    const impact = rescheduleImpact(manual, "2026-11-22", today, 200)
    assert.equal(impact.recommendedIso, "2026-11-17")
    assert.equal(impact.vsRecommendedDays, 5)
    assert.equal(impact.shiftDays, 2)
  })
})

describe("paletteForCode", () => {
  it("is stable for a code and returns real class names", () => {
    const first = paletteForCode("ТО-1В")
    assert.deepEqual(paletteForCode("ТО-1В"), first)
    assert.match(first.color, /^#[0-9a-f]{6}$/)
    assert.ok(first.bar.startsWith("bg-"))
  })
})


describe("living plan: per-asset pace", () => {
  it("prefers the asset's own pace over the page-wide default", () => {
    assert.equal(paceOf(make({ paceKmPerDay: "54" }), 200), 54)
    assert.equal(paceOf(make({}), 200), 200)
    assert.equal(paceOf(make({ paceKmPerDay: 0 }), null), null)
    // 350 km at 54 km/day = 7 days (not 2 days at the default 200)
    assert.equal(entry({ mileage: 4650, remainingKm: 350, nextThreshold: 5000, intervalKm: 5000, paceKmPerDay: 54 }, 200).daysLeft, 7)
  })
  it("estimates a move with the asset's own pace and flags the need for approval", () => {
    const item = make({
      entity_type: "maintenance_plan", plan_id: "p", startDate: "2026-11-20", mileage: 4900, remainingKm: 100,
      nextThreshold: 5000, intervalKm: 5000, paceKmPerDay: 100, tolerance: 500, limiting: "km", deferralCount: 0,
    })
    const near = rescheduleImpact(item, "2026-11-22", "2026-11-16", null)
    assert.equal(near.paceKm, 100)
    assert.equal(near.remainingAtNewKm, -500) // 100 - 100 * 6 days
    assert.equal(near.needsApproval, false) // 500 km over is exactly the tolerance, not beyond it
    const far = rescheduleImpact(item, "2026-11-30", "2026-11-16", null)
    assert.equal(far.needsApproval, true) // 1300 km over, tolerance 500
    const earlier = rescheduleImpact(item, "2026-11-18", "2026-11-16", null)
    assert.equal(earlier.needsApproval, false) // moving earlier never needs approval
    // a slow typical pace (2 km/day) must not hide a long deferral: the cautious pace (28 km/day) decides
    const slow = make({ ...item, paceKmPerDay: 2, paceFastKmPerDay: 28, remainingKm: 120 })
    assert.equal(rescheduleImpact(slow, "2026-12-16", "2026-11-16", null).needsApproval, true) // 30 days: 840 km vs 120 left, tolerance 500
    assert.equal(rescheduleImpact(slow, "2026-11-20", "2026-11-16", null).needsApproval, false) // 4 days: 112 km, inside
    const tired = make({ ...item, deferralCount: 2 })
    assert.equal(rescheduleImpact(tired, "2026-11-21", "2026-11-16", null).needsApproval, true) // third deferral
  })
})

describe("living plan: blocked plans and states", () => {
  it("explains a blocked plan and says the obligation is not lost", () => {
    const rec = entry({
      entity_type: "maintenance_plan", plan_id: "p", status: "blocked", planStatus: "blocked",
      blockedReason: "parts", blockedUntil: "2026-11-25",
    }).rec
    assert.equal(rec.level, "warning")
    assert.match(rec.text, /нет запчастей/)
    assert.match(rec.text, /25\.11\.2026/)
    assert.match(rec.text, /не потеряно/)
  })
  it("shouts when the tolerance is exceeded", () => {
    const rec = entry({ mileage: 5600, remainingKm: -600, nextThreshold: 5000, intervalKm: 5000, state: "over_tolerance" }).rec
    assert.equal(rec.level, "critical")
    assert.match(rec.text, /Допуск превышен/)
  })
  it("a blocked plan cannot be dragged, but can be unblocked", () => {
    const blocked = make({ entity_type: "maintenance_plan", plan_id: "p", status: "blocked", planStatus: "blocked" })
    assert.equal(isReschedulable(blocked, true), false)
    assert.equal(canUnblock(blocked, true), true)
    assert.equal(canBlock(blocked, true), false)
    assert.equal(canUnblock(blocked, false), false)
  })
})

describe("living plan: who may do what", () => {
  const plan = make({ entity_type: "maintenance_plan", plan_id: "p", status: "upcoming", planStatus: "scheduled", interval_id: "i" })
  it("operators block and set baselines, only administrators waive", () => {
    assert.equal(canBlock(plan, true), true)
    assert.equal(canBlock(plan, false), false)
    assert.equal(canWaive(plan, false), false)
    assert.equal(canWaive(plan, true), true)
    assert.equal(canWaive(make({ ...plan, planStatus: "in_progress", status: "in_progress" }), true), false)
    assert.equal(canSetBaseline(plan, true), true)
    assert.equal(canSetBaseline(make({ entity_type: "work_order", interval_id: null }), true), false)
  })
  it("a forecast row has no plan to block or waive", () => {
    const forecast = make({ interval_id: "i" })
    assert.equal(canBlock(forecast, true), false)
    assert.equal(canWaive(forecast, true), false)
    assert.equal(canSetBaseline(forecast, true), true)
  })
})

describe("living plan: markers timeline", () => {
  it("places the window, the three dates and today on one 0-100 % line", () => {
    const line = markerTimeline(
      make({ windowOpen: "2026-11-14", dateEarly: "2026-11-21", dateTypical: "2026-11-23", dateLate: "2026-11-25" }),
      "2026-11-16",
    )
    assert.ok(line)
    assert.equal(line.points.length, 4)
    const byKey = Object.fromEntries(line.points.map((point) => [point.key, point.pct]))
    assert.equal(byKey.window, 0) // earliest
    assert.equal(byKey.late, 100) // latest
    assert.ok(byKey.early < byKey.typical && byKey.typical < byKey.late)
    assert.ok(line.todayPct > 0 && line.todayPct < byKey.early)
    assert.equal(line.fromIso, "2026-11-14")
    assert.equal(line.toIso, "2026-11-25")
  })
  it("draws a slow-pace date that is years away at the right edge instead of squashing the other dates", () => {
    const line = markerTimeline(
      make({ windowOpen: "2026-11-14", dateEarly: "2026-11-21", dateTypical: "2026-11-30", dateLate: "2028-07-04" }),
      "2026-11-16",
    )
    assert.ok(line)
    const byKey = Object.fromEntries(line.points.map((point) => [point.key, point]))
    assert.equal(byKey.late.pct, 100)
    assert.equal(byKey.late.clamped, true)
    assert.equal(byKey.late.iso, "2028-07-04") // the real date is still shown in the list
    assert.equal(byKey.typical.clamped, false)
    assert.ok(byKey.typical.pct < 30, `typical at ${byKey.typical.pct}%`) // not pushed to the left by the far date
    assert.equal(line.toIso, "2027-03-16") // 120 days from today
  })
  it("is null without any marker and survives a single date", () => {
    assert.equal(markerTimeline(make({}), "2026-11-16"), null)
    assert.equal(markerTimeline(make({ windowOpen: "2026-11-10" }), "2026-11-16"), null) // a window alone says nothing
    const single = markerTimeline(make({ dateEarly: "2026-11-16" }), "2026-11-16")
    assert.ok(single)
    assert.equal(single.points[0].pct, 0)
  })
})

describe("living plan: small helpers", () => {
  it("maps a priority score to a tone", () => {
    assert.equal(priorityTone(95), "critical")
    assert.equal(priorityTone(80), "critical")
    assert.equal(priorityTone(60), "high")
    assert.equal(priorityTone(35), "medium")
    assert.equal(priorityTone(10), "low")
    assert.equal(priorityTone(null), "low")
  })
  it("describes the pace and its source", () => {
    assert.equal(paceText(make({})), null)
    const text = paceText(make({ paceKmPerDay: "54.2", paceSource: "asset", paceDays: 30 }))
    assert.match(text as string, /54,2 км\/сут/)
    assert.match(text as string, /по самой технике, 30 дн\. данных/)
  })
  it("validates the date of the last service", () => {
    assert.equal(validateBaselineDate("2026-11-10", "2026-11-16"), null)
    assert.equal(validateBaselineDate("2026-11-16", "2026-11-16"), null)
    assert.match(validateBaselineDate("2026-11-17", "2026-11-16") as string, /будущем/)
    assert.match(validateBaselineDate("", "2026-11-16") as string, /Укажите/)
  })
  it("parses typed kilometres with spaces and a decimal comma", () => {
    assert.equal(parseKmInput("1 234,5"), 1234.5)
    assert.equal(parseKmInput("-3000"), -3000)
    assert.equal(parseKmInput(""), null)
    assert.equal(parseKmInput("abc"), null)
  })
})
