import assert from "node:assert/strict"
import { describe, it } from "node:test"
import {
  candidateText, collectorText, correctionText, flagLabel, healthText, isLinked, netText, ownShareText, percentText, silentText, tonnesText,
  tripTonnes, wagonLabel, wagonsText, type Correction, type ScaleTrain,
} from "./scales-view.ts"

describe("scales helpers", () => {
  it("says how long a scale has been silent", () => {
    assert.equal(silentText(null), "нет данных")
    assert.equal(silentText(0.25), "15 мин назад")
    assert.equal(silentText(5.6), "6 ч назад")
    assert.equal(silentText(72), "3 сут назад")
  })

  it("describes the post health in words", () => {
    assert.equal(healthText({ health: "unknown", silent_hours: null }), "Данных ещё нет")
    assert.match(healthText({ health: "ok", silent_hours: 0.5 }), /Работает/)
    assert.match(healthText({ health: "alert", silent_hours: 30 }), /Давно нет взвешиваний: 30 ч назад/)
    assert.equal(collectorText("stale"), "сборщик не отвечает более 10 мин")
  })

  it("formats tonnes and marks an estimate", () => {
    assert.equal(tonnesText(null), "—")
    assert.equal(tonnesText("1234.5").replace(/\s/g, " "), "1 235 т".replace(/\s/g, " "))
    assert.match(netText({ net_total_t: 300, net_source: "estimated" }), /^≈ 300/)
    assert.doesNotMatch(netText({ net_total_t: 300, net_source: "weighings" }), /≈/)
    assert.equal(percentText(0.876), "87,60%")
    assert.equal(percentText(null), "—")
  })

  it("explains flags, wagon counts and candidates", () => {
    assert.equal(flagLabel("count_mismatch"), "Число вагонов не совпало с GTK")
    assert.equal(flagLabel("something_new"), "something_new")
    const t = { dump_count: 13, carriages_total: 13, carriages_linked: 4, match_status: "ok" } as Pick<ScaleTrain, "dump_count" | "carriages_total" | "carriages_linked" | "match_status">
    assert.equal(wagonsText(t), "13 на весах, 13 в GTK, связано с ОС: 4")
    assert.equal(wagonsText({ ...t, match_status: "no_loco" }), "13 вагонов на весах")
    assert.equal(
      candidateText({ loco_gtk_id: 5, garage_number: "074", name: "ТА 074", asset_id: null, asset_inv_number: null, overlap_min: 9.6 }),
      "ТА 074 (не связан с ОС), совпадение 10 мин",
    )
  })

  it("describes corrections", () => {
    const base = { id: "1", train_id: null, asset_id: "a", gtk_train_id: null, note: null, is_active: true, created_at: "" } as const
    assert.equal(correctionText({ ...base, kind: "loco_alias", loco_number: "3202", asset_inv_number: "38701" } as Correction), "Номер «3202» = локомотив 38701")
    assert.equal(correctionText({ ...base, kind: "train_exclude", loco_number: null } as Correction), "Состав исключён из учёта")
    assert.equal(correctionText({ ...base, kind: "train_gtk", loco_number: null, gtk_train_id: 77 } as Correction), "Состав привязан к составу GTK 77")
  })
})

describe("wagon ledger helpers", () => {
  const id = { gtk_inventory_number: null, gtk_name: null, carriage_gtk_id: 77 }
  it("names a wagon by the TOIR number, else the GTK one", () => {
    assert.equal(wagonLabel({ ...id, inv_number: "18461-38637" }), "18461-38637")
    assert.equal(wagonLabel({ ...id, inv_number: null, gtk_name: "СВ2-115 00018461" }), "СВ2-115 00018461")
    assert.equal(wagonLabel({ ...id, inv_number: null }), "GTK 77")
    assert.equal(isLinked({ asset_id: null }), false)
  })
  it("shows tonnes, marking shares and hiding the unknown", () => {
    assert.equal(tripTonnes({ tonnes: 110, basis: "own" }).replace(/\s/g, " "), "110 т")
    assert.match(tripTonnes({ tonnes: "106.6", basis: "train_avg" }), /^≈ 106,6/)
    assert.equal(tripTonnes({ tonnes: null, basis: "unknown" }), "—")
  })
  it("tells how many trips were weighed individually", () => {
    assert.equal(ownShareText({ trips: 4, own_trips: 3 }), "75,00% по собственному взвешиванию")
    assert.equal(ownShareText({ trips: 0, own_trips: 0 }), "—")
  })
})
