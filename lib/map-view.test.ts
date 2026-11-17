import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  ageText, boundsOf, filterPoints, googleEmbedUrl, googleMapsLink, markerColor, trainText, typeOptions, candidateText, dateText, durationText, reasonExplanation, sinceText, sourceText, DETAIL_LABEL, DETAIL_ORDER, type MapPoint, type UnplacedItem,
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

  it("draws a wagon at its locomotive: orange marker, a train caption, and the locomotive number finds its wagons", () => {
    assert.equal(markerColor({ source: "train", online: true }), "#d97706")
    const wagon = point({
      asset_id: "w", inv_number: "9001", name: "Вагон 9001", asset_type: "wagon", source: "train", train_number: "T-7",
      locomotive_inv_number: "37017", locomotive_name: "Тепловоз 2313",
    })
    assert.equal(trainText(wagon), "В составе № T-7 · локомотив 37017 (Тепловоз 2313)")
    assert.equal(trainText({ source: "train" }), "В составе")
    assert.equal(trainText(point({})), null)
    assert.deepEqual(filterPoints([point({}), wagon], { q: "37017" }).map((p) => p.asset_id), ["w"])
    assert.deepEqual(filterPoints([point({}), wagon], { source: "train" }).map((p) => p.asset_id), ["w"])
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

const NOW = new Date("2026-11-17T12:00:00Z")
const item = (over: Partial<UnplacedItem>): UnplacedItem => ({
  asset_id: "x", inv_number: "38742", name: "Вагон 38742", asset_type: "wagon", status: "operational", group: "no_link", reason: "no_link", ...over,
})

describe("unplaced explanations", () => {
  it("formats dates and durations", () => {
    assert.equal(dateText("2026-11-04T08:00:00Z"), "04.11.2026")
    assert.equal(dateText(null), "")
    assert.equal(dateText("not a date"), "")
    assert.equal(durationText("2026-11-17T08:00:00Z", NOW), "сегодня")
    assert.equal(durationText("2026-11-09T12:00:00Z", NOW), "8 дн.")
    assert.equal(durationText("2026-06-17T12:00:00Z", NOW), "5 мес.")
    assert.equal(durationText("2024-11-17T12:00:00Z", NOW), "2 г.")
    assert.equal(durationText(undefined, NOW), "")
  })

  it("has a short label for every reason", () => {
    for (const code of DETAIL_ORDER) assert.ok(DETAIL_LABEL[code].length > 0)
    assert.equal(new Set(DETAIL_ORDER).size, 7)
  })

  it("explains an unlinked wagon, with and without a GTK candidate, and an unlinked locomotive", () => {
    assert.match(reasonExplanation(item({})), /нет вагона с таким инвентарным или регистрационным номером/)
    const withCandidate = item({ candidate: { gtk_id: 1, name: "2ВС-115 00019427", reg_number: "00019427", inventory_number: "38742", is_active: true, has_coordinates: true, match: "inv_and_reg" } })
    assert.match(reasonExplanation(withCandidate), /есть похожий вагон/)
    assert.equal(candidateText(withCandidate.candidate), "Возможно, это вагон GTK «2ВС-115 00019427» (инв. 38742, рег. 00019427): совпали инв. и рег. номер; в GTK у него есть координаты.")
    assert.match(reasonExplanation(item({ asset_type: "diesel" })), /юниту Wialon/)
  })

  it("flags a candidate that is already linked to another asset", () => {
    const text = candidateText({ gtk_id: 2, is_active: true, has_coordinates: false, match: "reg", taken_by_inv_number: "OTHER" })
    assert.match(text ?? "", /уже привязан к активу OTHER: возможно, дубликат/)
    assert.equal(candidateText(null), null)
  })

  it("says since when and from where for each linked reason", () => {
    const gtk = item({
      group: "no_position", reason: "gtk_no_coords", gtk_external_id: "7", gtk_carriage_id: 7, gtk_carriage_name: "NOCOORDS",
      gtk_first_seen_at: "2026-11-04T08:00:00Z", gtk_last_synced_at: "2026-11-17T11:00:00Z",
    })
    assert.equal(sinceText(gtk, NOW), "GTK видит вагон с 04.11.2026 (13 дн.); последняя синхронизация 1 ч назад")
    assert.equal(sourceText(gtk), "GTK: «NOCOORDS» (7)")
    const nofix = item({
      group: "no_position", reason: "wialon_no_fix", wialon_external_id: "u1", wialon_unit_id: "u1", wialon_unit_name: "Unit 1",
      wialon_first_seen_at: "2026-11-10T00:00:00Z", wialon_last_message_at: null,
    })
    assert.match(sinceText(nofix, NOW), /Юнит в Wialon виден с 10\.11\.2026 \(7 дн\.\); сообщений от юнита не было/)
    assert.equal(sourceText(nofix), "Wialon: «Unit 1» (u1)")
    const missing = item({ group: "no_position", reason: "wialon_unit_missing", wialon_external_id: "u9", wialon_linked_at: "2026-11-01T00:00:00Z" })
    assert.equal(sourceText(missing), "Wialon: (u9, не найден)")
    assert.match(reasonExplanation(missing), /юнита нет в данных последней синхронизации Wialon/)
    assert.equal(sourceText(item({})), "нет привязок")
    assert.match(sinceText(item({ asset_created_at: "2026-11-09T12:00:00Z" }), NOW), /^В системе с 09\.11\.2026 \(8 дн\.\); привязки не было$/)
  })

  it("explains a wagon in a train whose locomotive has no GPS, and a train without a locomotive", () => {
    const base = { group: "no_position" as const, reason: "train_no_gps" as const, train_number: "T-9" }
    assert.match(reasonExplanation(item({ ...base, train_has_locomotive: true })), /№ T-9, но у локомотива состава нет GPS/)
    assert.match(reasonExplanation(item({ ...base, train_has_locomotive: false })), /№ T-9, в котором нет локомотива/)
  })
})
