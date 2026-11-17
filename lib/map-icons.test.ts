import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  iconKind, iconSvg, iconWidth, locoOutline, metersPerPixel, offset, statusOf, strip, trainBounds, trainCaption, vehicleCorners, vehicleFill,
  type LiveTrain,
} from "./map-icons.ts"

const dist = (a: [number, number], b: [number, number]): number => {
  const R = 6_371_000
  const dLat = ((b[0] - a[0]) * Math.PI) / 180, dLon = ((b[1] - a[1]) * Math.PI) / 180
  const x = Math.sin(dLat / 2) ** 2 + Math.cos((a[0] * Math.PI) / 180) * Math.cos((b[0] * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(x))
}

describe("icons", () => {
  it("picks the pictogram from the asset type and model", () => {
    assert.equal(iconKind({ asset_type: "locomotive", model_name: "ПЭ-2у" }), "electric")
    assert.equal(iconKind({ asset_type: "diesel", model_name: "ТЭМ2" }), "diesel")
    assert.equal(iconKind({ asset_type: "special_self_propelled", model_name: "АС-7М" }), "loco")
    assert.equal(iconKind({ asset_type: "special_self_propelled", model_name: "МПЭ-2у" }), "electric")
    assert.deepEqual(["wagon", "tank_car", "platform", "x"].map((t) => iconKind({ asset_type: t, model_name: null })), ["dump", "tank", "platform", "other"])
  })
  it("draws a status dot and a selection frame", () => {
    const plain = iconSvg("electric", "online", 40)
    assert.match(plain, /^<svg[^>]*width="40" height="24"/)
    assert.ok(plain.includes("#16a34a") && !plain.includes("#ef4444"))
    assert.ok(iconSvg("dump", "train", 30, true).includes("#ef4444"))
    for (const k of ["electric", "diesel", "loco", "dump", "tank", "platform", "other"] as const) assert.ok(iconSvg(k, "gtk").includes("<svg"))
    assert.equal(statusOf({ source: "wialon", online: false }), "offline")
    assert.equal(statusOf({ source: "train", online: null }), "train")
  })
  it("grows the icon with the zoom and makes locomotives larger", () => {
    assert.ok(iconWidth(5, "dump") < iconWidth(9, "dump") && iconWidth(9, "dump") < iconWidth(14, "dump"))
    assert.ok(iconWidth(14, "electric") > iconWidth(14, "dump"))
  })
})

describe("true-scale geometry", () => {
  it("a vehicle polygon has the real length and width on the ground", () => {
    const [rl, rr, fr, fl] = vehicleCorners(41.3, 69.2, 37, 14.5, 3.2)
    assert.ok(Math.abs(dist(rl, rr) - 3.2) < 0.05 && Math.abs(dist(rl, fl) - 14.5) < 0.05 && Math.abs(dist(rr, fr) - 14.5) < 0.05)
  })
  it("the front points in the direction of travel", () => {
    const north = vehicleCorners(41.3, 69.2, 0, 20, 3)
    assert.ok(north[2][0] > north[1][0] && north[3][0] > north[0][0])
    const east = vehicleCorners(41.3, 69.2, 90, 20, 3)
    assert.ok(east[2][1] > east[1][1])
    const outline = locoOutline(41.3, 69.2, 0, 21, 3.1)
    assert.equal(outline.length, 5)
    assert.ok(outline[3][0] > outline[2][0] && Math.abs(outline[3][1] - 69.2) < 1e-7) // the nose is the foremost point, on the axis
  })
  it("a strip lies inside the vehicle between two distances along it", () => {
    const [a, , , d] = strip(41.3, 69.2, 0, 2, 5, 1)
    assert.ok(Math.abs(dist(a, d) - 3) < 0.05)
    assert.ok(Math.abs(dist(offset(41.3, 69.2, 0, 100), [41.3, 69.2]) - 100) < 0.2)
  })
  it("converts the zoom level to metres per pixel", () => {
    assert.ok(Math.abs(metersPerPixel(0, 18) - 0.597) < 0.01)
    assert.ok(metersPerPixel(41.3, 17) < metersPerPixel(41.3, 16))
    assert.ok(14.5 / metersPerPixel(41.3, 18) > 25) // a car is ~30 px long at zoom 18: visible as a vehicle
    assert.ok(14.5 / metersPerPixel(41.3, 14) < 5) // and a few pixels at zoom 14: that is why it becomes a pictogram
  })
  it("colours vehicles and describes trains", () => {
    assert.notEqual(vehicleFill("dump", true), vehicleFill("dump", false))
    assert.equal(vehicleFill("electric", null), "#2563eb")
    const t = { loco_inv_number: "37091", loco_name: "ПЭ2М", wagons_count: 13, length_m: 251.4, moving: true, speed: 24.2, vehicles: [{ lat: 41.30, lon: 69.20 }, { lat: 41.31, lon: 69.22 }] } as unknown as LiveTrain
    assert.equal(trainCaption(t), "37091 ПЭ2М · 13 вагонов · 251 м · едет 24 км/ч")
    assert.equal(trainCaption({ ...t, moving: false, loco_name: null }), "37091 · 13 вагонов · 251 м · стоит")
    const [[s, w], [n, e]] = trainBounds(t)
    assert.ok(s < 41.30 && n > 41.31 && w < 69.20 && e > 69.22)
  })
})
