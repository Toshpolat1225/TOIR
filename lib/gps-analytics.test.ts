import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  BASIS_LABEL, CAUSE_HINT, CAUSE_LABEL, CAUSE_ORDER, CAUSE_TONE, CONFIDENCE_LABEL, CONFIDENCE_ORDER, DEFAULT_FILTERS, DEFAULT_WAGON_FILTERS, FLAG_HINT, FLAG_LABEL, FLAG_ORDER,
  GTK_LOSS_CAUSES, HEALTH_HINT, HEALTH_LABEL, HEALTH_ORDER, OVERVIEW_SORTS, addDays, addSavedView, bboxText, causeColor, causeLabel, confidenceText, confidenceTone,
  datePreset, daysBetween, fusedText, gpsApiParams, gpsFilterChips, healthLabel, hoursText, isDefaultFilters, localDay, okShareText, parseGpsFilters, parseSavedViews,
  filterTrackToDay, parseWagonFilters, patchActive, timelineBars, pointInBbox, segKm, serializeGpsFilters, serializeWagonFilters, sumGap, toggleValue, wagonApiParams, wagonFilterChips, windowText, worstDay,
} from "./gps-analytics.ts"
import { TONE_COLOR, type CauseCode, type Confidence, type GpsDayRow, type HealthClass, type WagonBasis, type WagonFlag } from "./gps-view.ts"

const nb = (text: string): string => text.replace(/ /g, " ") // the formatters use a non-breaking space
const day = (over: Partial<GpsDayRow>): GpsDayRow => ({
  day: "2026-11-16", wialon_points: 600, gtk_points: 500, gtk_raw_points: 2000, gtk_final: true, verdict: "match", cause: "ok", ...over,
})

describe("causes, health, confidence and wagon vocabularies", () => {
  it("has a label, hint and tone for every cause the backend can send", () => {
    const all: CauseCode[] = ["ok", "method", "day_open", "gtk_dead", "gtk_no_day", "gtk_gaps", "gtk_sparse", "wialon_gaps", "both_gaps", "not_collected", "idle", "no_data"]
    assert.deepEqual([...CAUSE_ORDER].sort(), [...all].sort())
    for (const c of all) assert.ok(CAUSE_LABEL[c] && CAUSE_HINT[c] && CAUSE_TONE[c], c)
    assert.equal(CAUSE_LABEL.gtk_dead, "GTK мёртв")
    assert.equal(CAUSE_LABEL.gtk_no_day, "GTK не писал")
    assert.equal(CAUSE_LABEL.gtk_sparse, "GTK: редкие точки")
    assert.equal(CAUSE_LABEL.both_gaps, "Провалы у обоих")
    assert.equal(CAUSE_LABEL.not_collected, "GTK не собран")
    assert.ok(GTK_LOSS_CAUSES.every((c) => c.startsWith("gtk_")))
  })

  it("falls back for an unknown cause instead of throwing", () => {
    assert.equal(causeLabel("something_new"), "something_new")
    assert.equal(causeLabel(null), "—")
    assert.equal(causeColor("nope"), TONE_COLOR.mute)
    assert.equal(causeColor("gtk_dead"), TONE_COLOR.bad)
  })

  it("covers every health class, confidence, flag and basis", () => {
    const health: HealthClass[] = ["ok", "intermittent", "dead", "frozen", "no_gtk"]
    assert.deepEqual([...HEALTH_ORDER].sort(), [...health].sort())
    for (const h of health) assert.ok(HEALTH_LABEL[h] && HEALTH_HINT[h], h)
    assert.equal(HEALTH_LABEL.intermittent, "Нестабильный")
    assert.equal(HEALTH_LABEL.dead, "Мёртвый")
    assert.equal(HEALTH_LABEL.frozen, "Замёрз")
    assert.equal(healthLabel("weird"), "weird")
    const conf: Confidence[] = ["high", "medium", "low", "none"]
    assert.deepEqual([...CONFIDENCE_ORDER].sort(), [...conf].sort())
    for (const c of conf) assert.ok(CONFIDENCE_LABEL[c], c)
    const flags: WagonFlag[] = ["two_trains", "stale_membership", "loco_silent", "no_loco", "no_history"]
    assert.deepEqual([...FLAG_ORDER].sort(), [...flags].sort())
    for (const f of flags) assert.ok(FLAG_LABEL[f] && FLAG_HINT[f], f)
    const basis: WagonBasis[] = ["fused_track", "track", "odometer", "conflict", "single_source", "held"]
    for (const b of basis) assert.ok(BASIS_LABEL[b], b)
  })
})

describe("formatting of the analytics figures", () => {
  it("states the confidence in words and tone", () => {
    assert.equal(confidenceText(0.94), "высокая 94%")
    assert.equal(confidenceText(0.8), "средняя 80%")
    assert.equal(confidenceText(0.31), "низкая 31%")
    assert.equal(confidenceText(null), "—")
    assert.equal(confidenceTone(0.95), "ok")
    assert.equal(confidenceTone(0.75), "warn")
    assert.equal(confidenceTone(0.2), "bad")
    assert.equal(confidenceTone(undefined), "mute")
  })

  it("shows the unified distance with the uncertainty only when there is one", () => {
    assert.equal(nb(fusedText(34_900, 1_200)), "34,9 км ± 1,2 км")
    assert.equal(nb(fusedText(34_900, 0)), "34,9 км")
    assert.equal(nb(fusedText(null, 100)), "—")
    assert.equal(sumGap([day({ unknown_gap_m: 500 }), day({ unknown_gap_m: null }), day({ unknown_gap_m: 700 })]), 1200)
  })

  it("formats hours, km of wagon segments and the ok share", () => {
    assert.equal(nb(hoursText(18.5)), "18,5 ч")
    assert.equal(nb(hoursText(null)), "—")
    assert.equal(nb(segKm(12.4)), "12,4 км")
    assert.equal(nb(segKm(null)), "—")
    assert.equal(okShareText({ health_class: "intermittent", window_days: 30, active_days: 20, ok_days: 8, partial_days: 5, none_days: 7, km_lost_m: 0 }), "8 из 20 дн. (40%)")
    assert.equal(okShareText(null), "—")
    assert.equal(okShareText({ health_class: "no_gtk", window_days: 30, active_days: 0, ok_days: 0, partial_days: 0, none_days: 0, km_lost_m: 0 }), "—")
  })

  it("picks the worst recent day and ignores clean ones", () => {
    const days = [day({ day: "2026-11-17", cause: "day_open" }), day({ day: "2026-11-16", cause: "gtk_gaps" }), day({ day: "2026-11-15", cause: "gtk_no_day" }), day({ day: "2026-11-14", cause: "gtk_no_day" })]
    assert.equal(worstDay(days)?.day, "2026-11-15") // the heaviest cause, the newer of equals
    assert.equal(worstDay([day({ cause: "ok" }), day({ cause: "idle" })]), null)
    assert.equal(worstDay([]), null)
  })
})

describe("local days, presets and bounds", () => {
  const nowMs = Date.UTC(2026, 10, 17, 20, 30) // 17.11 20:30 UTC = 18.11 01:30 in UTC+5
  it("computes the GTK local day across midnight", () => {
    assert.equal(localDay(nowMs, 5), "2026-11-18")
    assert.equal(localDay(nowMs, 0), "2026-11-17")
    assert.equal(addDays("2026-03-01", -1), "2026-02-28")
    assert.equal(addDays("2026-12-31", 1), "2027-01-01")
    assert.equal(daysBetween("2026-11-12", "2026-11-18"), 7)
    assert.equal(daysBetween("bad", "2026-11-18"), 0)
  })

  it("builds the presets in the GTK zone", () => {
    assert.deepEqual(datePreset("today", nowMs), { date_from: "2026-11-18", date_to: "2026-11-18" })
    assert.deepEqual(datePreset("yesterday", nowMs), { date_from: "2026-11-17", date_to: "2026-11-17" })
    assert.deepEqual(datePreset("7", nowMs), { date_from: "2026-11-12", date_to: "2026-11-18" })
    assert.equal(daysBetween(datePreset("30", nowMs).date_from, datePreset("30", nowMs).date_to), 30)
  })

  it("writes a bbox and tests points against it", () => {
    const bbox = bboxText([[40.8, 69.5], [40.9, 69.7]])
    assert.equal(bbox, "40.80000,69.50000,40.90000,69.70000")
    assert.equal(pointInBbox({ lat: 40.85, lon: 69.6 }, bbox), true)
    assert.equal(pointInBbox({ lat: 41, lon: 69.6 }, bbox), false)
    assert.equal(pointInBbox({ lat: 40.85, lon: 69.6 }, "garbage"), false)
  })
})

describe("URL <-> filter state of the overview", () => {
  it("round-trips a rich state and omits defaults", () => {
    const f = { ...DEFAULT_FILTERS, q: " 3204 ", verdict: ["diverged", "gtk_stale"], cause: ["gtk_dead"], link: "both", min_diff_m: "500", moving: true, days: 14, sort_by: "diff_m" as const, sort_dir: "desc" as const, page: 2 }
    const query = serializeGpsFilters(f)
    assert.equal(query, "q=3204&verdict=diverged%2Cgtk_stale&cause=gtk_dead&link=both&min_diff_m=500&moving=1&days=14&sort_by=diff_m&page=2")
    const back = parseGpsFilters(query)
    assert.deepEqual(back, { ...f, q: "3204" })
    assert.equal(serializeGpsFilters(DEFAULT_FILTERS), "")
    assert.equal(isDefaultFilters(DEFAULT_FILTERS), true)
    assert.equal(isDefaultFilters({ ...DEFAULT_FILTERS, sort_by: "diff_m", page: 3 }), true) // sort and page are not filters
    assert.equal(isDefaultFilters({ ...DEFAULT_FILTERS, only_issues: true }), false)
  })

  it("drops unknown values, bad numbers and bad dates", () => {
    const f = parseGpsFilters("verdict=nonsense,confirmed&cause=zzz&severity=bad,huh&link=weird&min_diff_m=-5&days=99&date_from=2026-11-01&date_to=2026-11-30&sort_by=hack&page=-1&health=dead,unknown")
    assert.deepEqual(f.verdict, ["confirmed"])
    assert.deepEqual(f.cause, [])
    assert.deepEqual(f.severity, ["bad"])
    assert.equal(f.link, "")
    assert.equal(f.min_diff_m, "")
    assert.equal(f.days, DEFAULT_FILTERS.days) // 99 is out of range
    assert.equal(f.date_from, "2026-11-01") // a 30-day window is allowed
    assert.equal(f.sort_by, "severity")
    assert.equal(f.page, 0)
    assert.deepEqual(f.health, ["dead"])
  })

  it("keeps a valid date window and refuses one longer than 31 days", () => {
    const ok = parseGpsFilters("date_from=2026-11-01&date_to=2026-11-30")
    assert.equal(ok.date_from, "2026-11-01")
    assert.equal(windowText(ok), "01.11 – 30.11")
    const long = parseGpsFilters("date_from=2026-10-01&date_to=2026-11-30")
    assert.equal(long.date_from, "")
    const swapped = parseGpsFilters("date_from=2026-11-30&date_to=2026-11-01")
    assert.equal(swapped.date_from, "")
    assert.equal(serializeGpsFilters(ok), "date_from=2026-11-01&date_to=2026-11-30")
    assert.equal(windowText({ days: 1, date_from: "", date_to: "" }), "сегодня")
    assert.equal(windowText({ days: 7, date_from: "", date_to: "" }), "7 дн.")
  })

  it("defaults the sort direction by the column", () => {
    assert.equal(parseGpsFilters("sort_by=inv_number").sort_dir, "asc")
    assert.equal(parseGpsFilters("sort_by=diff_m").sort_dir, "desc")
    assert.equal(parseGpsFilters("sort_by=inv_number&sort_dir=desc").sort_dir, "desc")
    assert.equal(serializeGpsFilters({ ...DEFAULT_FILTERS, sort_by: "inv_number", sort_dir: "asc" }), "sort_by=inv_number")
    assert.deepEqual([...OVERVIEW_SORTS].slice(0, 2), ["severity", "inv_number"])
  })

  it("accepts URLSearchParams and a leading question mark", () => {
    assert.equal(parseGpsFilters("?link=gtk_only").link, "gtk_only")
    assert.equal(parseGpsFilters(new URLSearchParams("only_issues=1")).only_issues, true)
  })

  it("turns the state into API parameters (arrays stay arrays, dates override days)", () => {
    const p = gpsApiParams({ ...DEFAULT_FILTERS, verdict: ["diverged"], health: ["dead", "frozen"], min_km: "100", moving: true, only_issues: true }, { limit: 50, offset: 100, facets: true, bbox: "1,2,3,4" })
    assert.deepEqual(p, { limit: 50, offset: 100, days: 7, verdict: ["diverged"], health: ["dead", "frozen"], min_km: 100, moving: true, only_issues: true, facets: true, bbox: "1,2,3,4", sort_by: "severity", sort_dir: "desc" })
    const dated = gpsApiParams({ ...DEFAULT_FILTERS, date_from: "2026-11-10", date_to: "2026-11-12" }, { limit: 500, offset: 0, withSort: false })
    assert.equal(dated.days, undefined)
    assert.equal(dated.date_from, "2026-11-10")
    assert.equal(dated.sort_by, undefined)
  })

  it("lists a removable chip per active value and removing it restores the default", () => {
    const f = { ...DEFAULT_FILTERS, q: "37", section_id: "s1", verdict: ["diverged", "gtk_stale"], cause: ["gtk_gaps"], link: "both", moving: true, date_from: "2026-11-10", date_to: "2026-11-12", page: 3 }
    const chips = gpsFilterChips(f, (id) => (id === "s1" ? "Участок А" : undefined))
    assert.deepEqual(chips.map((c) => c.id), ["q", "section", "verdict:diverged", "verdict:gtk_stale", "cause:gtk_gaps", "link", "moving", "dates"])
    assert.ok(chips.find((c) => c.id === "section")?.label.includes("Участок А"))
    const removed = { ...f, ...chips.find((c) => c.id === "verdict:diverged")!.patch }
    assert.deepEqual(removed.verdict, ["gtk_stale"])
    assert.equal(removed.page, 0) // the page resets when a filter changes
    assert.deepEqual(gpsFilterChips(DEFAULT_FILTERS), [])
  })

  it("toggles a value and recognises an applied KPI patch", () => {
    assert.deepEqual(toggleValue(["a"], "b"), ["a", "b"])
    assert.deepEqual(toggleValue(["a", "b"], "a"), ["b"])
    const f = { ...DEFAULT_FILTERS, verdict: ["diverged", "both_stale_apart"] }
    assert.equal(patchActive(f, { verdict: ["both_stale_apart", "diverged"] }), true) // order does not matter
    assert.equal(patchActive(f, { verdict: ["diverged"] }), false)
    assert.equal(patchActive(f, { link: "both" }), false)
    assert.equal(patchActive(f, {}), false)
    assert.equal(patchActive({ ...f, link: "both" }, { link: "both" }), true)
  })
})

describe("URL <-> filter state of the wagons page", () => {
  it("round-trips and validates", () => {
    const f = { ...DEFAULT_WAGON_FILTERS, q: "W-1", train: "439", confidence: ["low", "none"], flag: ["two_trains"], in_train: "1" as const, days: 7, sort_by: "km_period" as const, sort_dir: "desc" as const, page: 1 }
    const query = serializeWagonFilters(f)
    assert.deepEqual(parseWagonFilters(query), f)
    assert.equal(serializeWagonFilters(DEFAULT_WAGON_FILTERS), "")
    const bad = parseWagonFilters("confidence=huge,high&flag=x&in_train=maybe&days=0&sort_by=zzz")
    assert.deepEqual(bad.confidence, ["high"])
    assert.deepEqual(bad.flag, [])
    assert.equal(bad.in_train, "")
    assert.equal(bad.days, 14)
    assert.equal(bad.sort_by, "inv_number")
  })

  it("builds the API parameters and the chips", () => {
    const f = { ...DEFAULT_WAGON_FILTERS, loco: "3204", confidence: ["low"], flag: ["no_loco"], in_train: "0" as const }
    assert.deepEqual(wagonApiParams(f, { limit: 50, offset: 0 }), { limit: 50, offset: 0, days: 14, sort_by: "inv_number", sort_dir: "asc", loco: "3204", confidence: ["low"], flag: ["no_loco"], in_train: false })
    assert.deepEqual(wagonFilterChips(f).map((c) => c.id), ["loco", "conf:low", "flag:no_loco", "in_train"])
  })
})

describe("saved views", () => {
  it("keeps the newest first, replaces a view of the same name and caps the list", () => {
    let views = addSavedView([], "Проблемные", "only_issues=1")
    views = addSavedView(views, "GTK мёртвые", "health=dead")
    views = addSavedView(views, "Проблемные", "only_issues=1&days=14")
    assert.deepEqual(views.map((v) => v.name), ["Проблемные", "GTK мёртвые"])
    assert.equal(views[0].query, "only_issues=1&days=14")
    assert.deepEqual(addSavedView(views, "   ", "x"), views)
    let many = views
    for (let i = 0; i < 20; i++) many = addSavedView(many, `v${i}`, "q=1")
    assert.equal(many.length, 12)
  })

  it("parses broken storage as an empty list", () => {
    assert.deepEqual(parseSavedViews(null), [])
    assert.deepEqual(parseSavedViews("{not json"), [])
    assert.deepEqual(parseSavedViews('{"a":1}'), [])
    assert.deepEqual(parseSavedViews('[{"name":"a","query":"b"},{"name":1},null]'), [{ name: "a", query: "b" }])
  })
})

describe("one local day of a track and the wagon timeline", () => {
  it("keeps only the points of the local day (UTC+5)", () => {
    const pts = [{ at: "2026-11-15T18:59:59Z" }, { at: "2026-11-15T19:00:00Z" }, { at: "2026-11-16T12:00:00Z" }, { at: "2026-11-16T19:00:00Z" }]
    // local 2026-11-16 = 2026-11-15T19:00Z .. 2026-11-16T19:00Z (end exclusive)
    assert.deepEqual(filterTrackToDay(pts, "2026-11-16", 5).map((p) => p.at), ["2026-11-15T19:00:00Z", "2026-11-16T12:00:00Z"])
    assert.equal(filterTrackToDay(pts, "garbage", 5).length, 4)
  })

  it("places segments proportionally and keeps a thin one visible", () => {
    const segs = [
      { period_from: "2026-11-10T00:00:00Z", period_to: "2026-11-12T00:00:00Z" },
      { period_from: "2026-11-12T00:00:00Z", period_to: "2026-11-12T00:01:00Z" },
      { period_from: "2026-11-12T00:00:00Z", period_to: "2026-11-14T00:00:00Z" },
    ]
    const { bars } = timelineBars(segs, 400)
    assert.equal(bars[0].x, 0)
    assert.equal(Math.round(bars[0].w), 200)
    assert.equal(bars[1].w, 3)
    assert.equal(Math.round(bars[2].x), 200)
    assert.deepEqual(timelineBars([], 400).bars, [])
  })
})
