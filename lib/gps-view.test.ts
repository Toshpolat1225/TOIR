import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  gpsPointLines,
  DISTANCE_LABEL, DISTANCE_ORDER, DISTANCE_TONE, POSITION_HINT, POSITION_LABEL, POSITION_ORDER, POSITION_TONE, TONE_COLOR,
  ageMinText, boundsOfLists, dayShort, distText, distanceColor, groupCounts, groupedBars, isStale, kmText, lagText, matchesQuery, miniBarHeights,
  niceMax, positionColor, positionSentence, ratioText, runStatusText, severityTone, signedDistText, stackSegments, statusTone, timeText, verdictGroup,
  type DistanceVerdict, type PositionVerdict,
} from "./gps-view.ts"

describe("verdict tables", () => {
  it("has a Russian label, hint, tone and a place in the order for every position verdict", () => {
    const all: PositionVerdict[] = ["confirmed", "diverged", "gtk_stale", "wialon_stale", "both_stale_agree", "both_stale_apart", "wialon_only", "gtk_only", "no_position"]
    assert.deepEqual([...POSITION_ORDER].sort(), [...all].sort())
    for (const v of all) assert.ok(POSITION_LABEL[v] && POSITION_HINT[v] && POSITION_TONE[v], v)
    assert.equal(POSITION_LABEL.confirmed, "Подтверждено")
    assert.equal(POSITION_LABEL.diverged, "Расхождение")
    assert.equal(POSITION_LABEL.gtk_stale, "GTK молчит")
    assert.equal(POSITION_LABEL.wialon_stale, "Wialon молчит")
    assert.equal(POSITION_LABEL.wialon_only, "Только Wialon")
    assert.equal(POSITION_LABEL.gtk_only, "Только GTK")
  })

  it("has a label and a tone for every distance verdict", () => {
    const all: DistanceVerdict[] = ["match", "minor_diff", "gtk_gap", "wialon_gap", "idle", "no_data", "not_collected"]
    assert.deepEqual([...DISTANCE_ORDER].sort(), [...all].sort())
    for (const v of all) assert.ok(DISTANCE_LABEL[v] && DISTANCE_TONE[v], v)
  })

  it("colours by tone and falls back to grey for an unknown verdict", () => {
    assert.equal(positionColor("confirmed"), TONE_COLOR.ok)
    assert.equal(positionColor("diverged"), TONE_COLOR.bad)
    assert.equal(positionColor("gtk_stale"), TONE_COLOR.warn)
    assert.equal(positionColor("nonsense"), TONE_COLOR.mute)
    assert.equal(positionColor(null), TONE_COLOR.mute)
    assert.equal(distanceColor("gtk_gap"), TONE_COLOR.bad)
    assert.equal(distanceColor("match"), TONE_COLOR.ok)
  })

  it("maps severity and backend status to a tone", () => {
    assert.deepEqual([0, 1, 2, 3, 9].map(severityTone), ["ok", "info", "warn", "bad", "bad"])
    assert.deepEqual(["ok", "warn", "bad", "?"].map(statusTone), ["ok", "warn", "bad", "mute"])
  })
})

describe("map verdict groups", () => {
  it("folds nine verdicts into five chips", () => {
    assert.equal(verdictGroup("confirmed"), "confirmed")
    assert.equal(verdictGroup("both_stale_agree"), "confirmed")
    assert.equal(verdictGroup("both_stale_apart"), "diverged")
    assert.equal(verdictGroup("diverged"), "diverged")
    assert.equal(verdictGroup("wialon_only"), "single")
    assert.equal(verdictGroup("gtk_only"), "single")
    assert.equal(verdictGroup("no_position"), null)
    assert.equal(verdictGroup(undefined), null)
  })

  it("sums the backend counters into the chip counters", () => {
    assert.deepEqual(groupCounts({ confirmed: 28, both_stale_agree: 1, diverged: 1, gtk_stale: 10, wialon_only: 3, gtk_only: 2, no_position: 4 }), {
      confirmed: 29, diverged: 1, gtk_stale: 10, wialon_stale: 0, single: 5,
    })
    assert.deepEqual(groupCounts(null), { confirmed: 0, diverged: 0, gtk_stale: 0, wialon_stale: 0, single: 0 })
  })
})

describe("formatting", () => {
  it("formats kilometres with a decimal comma and groups big numbers", () => {
    assert.equal(kmText(27747), "27,7 км")
    assert.equal(kmText(0), "0,0 км")
    assert.equal(kmText(33_607_800), "33 608 км")
    assert.equal(kmText(115_412), "115 км")
    assert.equal(kmText(12345, false), "12,3")
    assert.equal(kmText(null), "—")
    assert.equal(kmText(Number.NaN), "—")
  })

  it("formats short distances in metres and long ones in kilometres, with a sign for differences", () => {
    assert.equal(distText(250), "250 м")
    assert.equal(distText(1240), "1,2 км")
    assert.equal(distText(undefined), "—")
    assert.equal(signedDistText(1240), "+1,2 км")
    assert.equal(signedDistText(-350), "−350 м")
    assert.equal(signedDistText(0.2), "0")
    assert.equal(signedDistText(null), "—")
  })

  it("formats ages as minutes, hours and days", () => {
    assert.equal(ageMinText(0.4), "сейчас")
    assert.equal(ageMinText(2), "2 мин")
    assert.equal(ageMinText(59.4), "59 мин")
    assert.equal(ageMinText(180), "3 ч")
    assert.equal(ageMinText(6703), "5 сут") // over 48 h the age is shown in days (4,65 -> 5)
    assert.equal(ageMinText(2000), "33 ч")
    assert.equal(ageMinText(7200), "5 сут")
    assert.equal(ageMinText(null), "нет данных")
  })

  it("formats ratios, lags, days and moments", () => {
    assert.equal(ratioText(0.943), "94%")
    assert.equal(ratioText(1), "100%")
    assert.equal(ratioText(null), "—")
    assert.equal(lagText(45), "45 с")
    assert.equal(lagText(130), "2 мин")
    assert.equal(dayShort("2026-11-17"), "17.11")
    assert.equal(dayShort("oops"), "oops")
    assert.equal(timeText(null), "—")
    assert.equal(timeText("garbage"), "—")
    assert.match(timeText("2026-11-17T12:00:00Z"), /^\d{2}\.\d{2}\.2026 \d{2}:\d{2}$/)
  })

  it("names the sync run state and detects a stale sync", () => {
    assert.equal(runStatusText("success"), "успешно")
    assert.equal(runStatusText("failed"), "сбой")
    assert.equal(runStatusText(null), "запусков не было")
    const now = new Date("2026-11-17T12:00:00Z")
    assert.equal(isStale("2026-11-17T11:50:00Z", 30, now), false)
    assert.equal(isStale("2026-11-17T10:00:00Z", 30, now), true)
    assert.equal(isStale(null, 30, now), true)
  })

  it("explains a verdict with the numbers behind it", () => {
    const text = positionSentence(
      { verdict: "confirmed", diff_m: 646, tolerance_m: 850, lag_s: 108 },
      { lat: 1, lon: 1, fresh: true, age_min: 2.6 },
      { lat: 1, lon: 1, fresh: true, age_min: 0.8 },
    )
    assert.match(text, /Между точками 646 м при допуске 850 м/)
    assert.match(text, /Wialon 3 мин, GTK сейчас/)
  })
})

describe("filtering", () => {
  it("matches the inventory number, name, section and model case-insensitively", () => {
    const row = { inv_number: "38911", name: "Тепловоз ТЭМ2", section_name: "ПТОЛ", model_name: "ТЭМ2" }
    assert.equal(matchesQuery(row, ""), true)
    assert.equal(matchesQuery(row, "  389 "), true)
    assert.equal(matchesQuery(row, "птол"), true)
    assert.equal(matchesQuery(row, "zzz"), false)
  })
})

describe("chart geometry", () => {
  it("rounds an axis maximum up to 1, 2 or 5 x 10^k", () => {
    assert.deepEqual([0, -3, 0.7, 1, 1.4, 2.1, 4.9, 5.1, 9.9, 130].map(niceMax), [1, 1, 1, 1, 2, 5, 5, 10, 10, 200])
  })

  it("cuts a stacked bar into proportional segments in the given order, skipping zeros", () => {
    const seg = stackSegments(["a", "b", "c"], { a: 1, b: 0, c: 3 }, 200)
    assert.deepEqual(seg.map((s) => [s.key, s.value, Math.round(s.x), Math.round(s.w)]), [["a", 1, 0, 50], ["c", 3, 50, 150]])
    assert.equal(seg.reduce((s, x) => s + x.pct, 0), 100)
    assert.deepEqual(stackSegments(["a"], {}, 100), [])
  })

  it("draws a pair of bars per day, both scaled to the same nice maximum", () => {
    const { bars, max } = groupedBars([{ day: "a", a: 100_000, b: 90_000 }, { day: "b", a: null, b: 40_000 }], 200, 100)
    assert.equal(max, 100_000)
    assert.equal(bars[0].a.h, 100)
    assert.equal(bars[0].b.h, 90)
    assert.equal(bars[1].a.h, 0)
    assert.equal(bars[1].b.y, 60)
    assert.ok(bars[0].a.x + bars[0].a.w <= bars[0].b.x + 0.001, "the pair does not overlap")
    assert.deepEqual(groupedBars([], 100, 50), { bars: [], max: 1 })
  })

  it("scales mini bars by the common maximum", () => {
    assert.deepEqual(miniBarHeights([10, 5], [20, null]), { a: [0.5, 0.25], b: [1, 0] })
    assert.deepEqual(miniBarHeights([0], [null]), { a: [0], b: [0] })
  })

  it("finds the bounds of several lists of points", () => {
    assert.equal(boundsOfLists([[], []]), null)
    assert.deepEqual(boundsOfLists([[{ lat: 40, lon: 69 }], [{ lat: 41, lon: 68 }, { lat: 39, lon: 70 }]]), [[39, 68], [41, 70]])
  })
})

describe("map point of a locomotive with two trackers", () => {
  const base = { source: "gtk_gps" as const, speed: "12.4", gps_verdict: "confirmed", gps_diff_m: 646, gps_wialon_age_min: 2.6, gps_gtk_age_min: 0.8, alt_source: "wialon" as const, alt_lat: 40.85, alt_lon: 69.57 }

  it("shows the drawn fix, the other tracker and the distance between them", () => {
    const lines = gpsPointLines(base)
    assert.ok(lines)
    assert.equal(lines.verdictLabel, "Подтверждено")
    assert.equal(lines.drawn, "GTK GPS: сейчас · 12\u00a0км/ч")
    assert.equal(lines.other, "Wialon: 3\u00a0мин")
    assert.equal(lines.diff, "646\u00a0м")
    assert.equal(lines.ghost, true)
  })

  it("names a silent tracker and has no ghost when there is no other fix", () => {
    const silent = gpsPointLines({ ...base, source: "wialon", gps_verdict: "gtk_stale", gps_wialon_age_min: 2, gps_gtk_age_min: 6703, alt_source: null, alt_lat: null, alt_lon: null, speed: null })
    assert.ok(silent)
    assert.equal(silent.drawn, "Wialon: 2\u00a0мин")
    assert.equal(silent.other, "GTK GPS: 5\u00a0сут")
    assert.equal(silent.ghost, false)
    assert.equal(gpsPointLines({ ...base, gps_verdict: "wialon_only", alt_source: null })?.other, null)
    assert.equal(gpsPointLines({ ...base, gps_verdict: null }), null)
    assert.equal(gpsPointLines({ ...base, gps_verdict: "unknown_verdict" }), null)
  })
})
