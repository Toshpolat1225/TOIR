import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  buildTrains, fleetStats, historyBounds, historyHref, historyNote, hoursText, isLocomotive, kmText, movementText, pointAt, segmentAt,
  segmentHours, segmentSentence, type HistoryPoint, type HistorySegment,
} from "./map-history.ts"
import type { MapPoint } from "./map-view.ts"

const NOW = Date.parse("2026-11-17T12:00:00Z")
const point = (over: Partial<MapPoint>): MapPoint => ({
  asset_id: "a", inv_number: "100", name: "Вагон 100", asset_type: "wagon", status: "operational", lat: 41.3, lon: 69.2, source: "train", online: null, ...over,
}) as MapPoint
const seg = (over: Partial<HistorySegment>): HistorySegment => ({
  from_at: "2026-11-17T08:00:00Z", to_at: "2026-11-17T10:00:00Z", is_open: false, train_gtk_id: 1, train_title: null, loco_asset_id: "L", loco_inv_number: "37091",
  loco_label: "ТА 291", cars: 13, km: 6.2, max_speed: 32, points: 12, activity: "moving", trips: 1, tonnes: 1400, wagons: [], ...over,
})
const track = (...items: [string, number, number][]): HistoryPoint[] => items.map(([at, lat, lon]) => ({ at, lat, lon, speed: null, source: "loco", label: null }))

describe("history text", () => {
  it("writes durations and distances", () => {
    assert.equal(hoursText(0.2), "12 мин")
    assert.equal(hoursText(5.5).replace(/\s/g, " "), "5,5 ч")
    assert.equal(hoursText(72).replace(/\s/g, " "), "3 сут")
    assert.equal(kmText(null), "—")
    assert.equal(kmText(6.24).replace(/\s/g, " "), "6,2 км")
    assert.equal(segmentHours(seg({})), 2)
    assert.ok(segmentHours(seg({ to_at: null, from_at: "2026-11-17T10:00:00Z" }), NOW) === 2)
  })

  it("says in one sentence with whom and what it did", () => {
    assert.match(segmentSentence("wagon", seg({})), /Был в составе \(13 ваг\.\) за локомотивом ТА 291, 2 ч: за это время прошёл 6,2 км, максимум 32 км\/ч\./)
    assert.match(segmentSentence("wagon", seg({ activity: "standing", is_open: true, to_at: null, from_at: "2026-11-17T09:00:00Z" }), NOW), /^Сейчас в составе .*стоял на месте/)
    assert.match(segmentSentence("wagon", seg({ activity: "unknown", loco_label: null })), /локомотив не определён.*не записано/)
    assert.match(segmentSentence("locomotive", seg({})), /Тянул состав из 13 вагонов/)
  })

  it("explains the limits of the stored history", () => {
    const notes = historyNote({ gtk_history_from: "2026-11-04T00:00:00Z", track_from: null, days: 7 })
    assert.equal(notes.length, 2)
    assert.match(notes[0], /известен с 04\.11\.2026/)
    assert.match(notes[1], /Позиции пока не записывались/)
  })
})

describe("history geometry", () => {
  const t = track(["2026-11-17T08:00:00Z", 41.0, 69.0], ["2026-11-17T09:00:00Z", 41.1, 69.1], ["2026-11-17T10:00:00Z", 41.2, 69.2])
  it("finds the position at a moment and the segment around it", () => {
    assert.equal(pointAt(t, Date.parse("2026-11-17T09:30:00Z"))?.lat, 41.1)
    assert.equal(pointAt(t, Date.parse("2026-11-17T07:00:00Z"))?.lat, 41.0)
    assert.equal(pointAt(t, Date.parse("2026-11-17T11:00:00Z"))?.lat, 41.2)
    assert.equal(pointAt([], 0), null)
    assert.ok(segmentAt([seg({})], Date.parse("2026-11-17T09:00:00Z")))
    assert.equal(segmentAt([seg({})], Date.parse("2026-11-17T11:00:00Z")), null)
  })
  it("computes bounds and links", () => {
    assert.deepEqual(historyBounds(t), [[41.0, 69.0], [41.2, 69.2]])
    assert.equal(historyBounds([]), null)
    assert.equal(historyHref({ asset_id: null, carriage_gtk_id: 9 }), "/dashboard/map/history/gtk-9")
    assert.equal(historyHref({ asset_id: "abc" }), "/dashboard/map/history/abc")
    assert.ok(isLocomotive("diesel") && !isLocomotive("wagon"))
  })
})

describe("the map: trains on the line", () => {
  const loco = point({ asset_id: "L1", asset_type: "locomotive", inv_number: "37091", name: "ПЭ2М 37091", source: "wialon", online: true, speed: 24, position_at: "2026-11-17T11:59:00Z" })
  const wagons = [point({ asset_id: "w2", inv_number: "200", locomotive_asset_id: "L1" }), point({ asset_id: "w1", inv_number: "100", locomotive_asset_id: "L1" })]
  const parked = point({ asset_id: "L2", asset_type: "diesel", source: "wialon", online: true, speed: 0, position_at: "2026-11-15T10:00:00Z" })
  const lone = point({ asset_id: "g1", source: "gtk" })

  it("groups the wagons by their locomotive and takes speed from it", () => {
    const trains = buildTrains([loco, ...wagons, parked, lone])
    assert.equal(trains.length, 1)
    assert.deepEqual(trains[0].wagons.map((w) => w.inv_number), ["100", "200"])
    assert.equal(trains[0].moving, true)
    assert.equal(trains[0].locoInv, "37091")
  })
  it("counts the fleet: online, moving, silent, trains", () => {
    const s = fleetStats([loco, ...wagons, parked, lone], NOW)
    assert.deepEqual([s.placed, s.online, s.moving, s.silent24h, s.trains, s.wagonsInTrains], [5, 2, 1, 1, 1, 2])
    assert.equal(s.byType[0].key, "wagon")
  })
  it("says whether a unit is moving", () => {
    assert.equal(movementText(loco), "едет, 24 км/ч")
    assert.equal(movementText(parked), "стоит")
    assert.equal(movementText({ source: "wialon", speed: 0, online: false }), "нет связи")
    assert.equal(movementText(lone), "положение по GTK")
  })
})
