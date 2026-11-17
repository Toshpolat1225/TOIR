import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  ageText, boundsOf, filterPoints, googleEmbedUrl, googleMapsLink, markerColor, typeOptions, type MapPoint,
} from "./map-view.ts"

const point = (over: Partial<MapPoint>): MapPoint => ({
  asset_id: "a", inv_number: "38700", name: "Тепловоз ТЭМ2-38700", asset_type: "diesel", asset_type_name: "Тепловоз",
  status: "operational", section_name: "ПТОЛ", lat: 41.3, lon: 69.2, source: "wialon", online: true, ...over,
})

describe("map helpers", () => {
  it("colours Wialon by online state and GTK blue", () => {
    assert.equal(markerColor({ source: "wialon", online: true }), "#16a34a")
    assert.equal(markerColor({ source: "wialon", online: false }), "#6b7280")
    assert.equal(markerColor({ source: "wialon", online: null }), "#6b7280")
    assert.equal(markerColor({ source: "gtk", online: null }), "#2563eb")
  })

  it("builds keyless Google links", () => {
    assert.equal(googleMapsLink(41.3111, 69.2797), "https://www.google.com/maps?q=41.311100,69.279700")
    assert.equal(googleEmbedUrl(41.3, 69.2, 10), "https://www.google.com/maps?q=41.300000,69.200000&z=10&output=embed")
  })

  it("filters by text, type and source", () => {
    const list = [point({}), point({ asset_id: "b", inv_number: "5001", name: "Вагон 5001", asset_type: "wagon", source: "gtk", section_name: "ВРП" })]
    assert.equal(filterPoints(list, {}).length, 2)
    assert.deepEqual(filterPoints(list, { source: "gtk" }).map((p) => p.asset_id), ["b"])
    assert.deepEqual(filterPoints(list, { type: "diesel" }).map((p) => p.asset_id), ["a"])
    assert.deepEqual(filterPoints(list, { q: " врп " }).map((p) => p.asset_id), ["b"])
    assert.deepEqual(filterPoints(list, { q: "38700", type: "wagon" }), [])
  })

  it("computes bounds and none for an empty list", () => {
    assert.equal(boundsOf([]), null)
    assert.deepEqual(boundsOf([{ lat: 41, lon: 69 }, { lat: 40, lon: 71 }, { lat: 43, lon: 64 }]), { south: 40, west: 64, north: 43, east: 71 })
  })

  it("describes the age of a position", () => {
    const now = new Date("2026-11-16T12:00:00Z")
    assert.equal(ageText(null, now), "время неизвестно")
    assert.equal(ageText("garbage", now), "время неизвестно")
    assert.equal(ageText("2026-11-16T11:59:40Z", now), "только что")
    assert.equal(ageText("2026-11-16T11:30:00Z", now), "30 мин назад")
    assert.equal(ageText("2026-11-16T09:00:00Z", now), "3 ч назад")
    assert.equal(ageText("2026-11-10T12:00:00Z", now), "6 дн назад")
  })

  it("lists asset types with counts, biggest first", () => {
    const list = [point({}), point({ asset_id: "b", asset_type: "wagon", asset_type_name: "Вагон" }), point({ asset_id: "c", asset_type: "wagon", asset_type_name: "Вагон" })]
    assert.deepEqual(typeOptions(list), [
      { value: "wagon", label: "Вагон", count: 2 },
      { value: "diesel", label: "Тепловоз", count: 1 },
    ])
  })
})
