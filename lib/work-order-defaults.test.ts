import assert from "node:assert/strict"
import { describe, it } from "node:test"
import { addHoursLocal, defaultExecutorId, defaultSectionId, findMyEmployee, sameName, formatHours, lateHours, totalHours, unitTypeForAsset, workTypesForAsset } from "./work-order-defaults.ts"

const types = [
  { id: "a", unit_type: "locomotive" as const, duration_hours: 4 },
  { id: "b", unit_type: "locomotive" as const, duration_hours: "2.5" },
  { id: "c", unit_type: "wagon" as const, duration_hours: null },
]

describe("work order defaults", () => {
  it("adds hours to a local datetime", () => {
    assert.equal(addHoursLocal("2026-11-19T10:00", 4), "2026-11-19T14:00")
    assert.equal(addHoursLocal("2026-11-19T22:30", 2.5), "2026-11-20T01:00")
    assert.equal(addHoursLocal("nonsense", 1), "")
  })
  it("sums durations and reports the types that have none", () => {
    assert.deepEqual(totalHours(types, ["a", "b"]), { hours: 6.5, missing: [] })
    assert.deepEqual(totalHours(types, ["a", "c", "a"]), { hours: 4, missing: ["c"] })
  })
  it("filters work types by asset kind", () => {
    assert.equal(unitTypeForAsset("diesel"), "locomotive")
    assert.equal(unitTypeForAsset("wagon"), "wagon")
    assert.equal(unitTypeForAsset("crane"), null)
    assert.deepEqual(workTypesForAsset(types, "wagon").map((t) => t.id), ["c"])
    assert.equal(workTypesForAsset(types, "crane").length, 3)
    assert.equal(workTypesForAsset(types, undefined).length, 3)
  })
  it("formats hours", () => {
    assert.equal(formatHours(4), "4 ч")
    assert.equal(formatHours("2.5"), "2,5 ч")
    assert.equal(formatHours(30), "1 дн. 6 ч")
    assert.equal(formatHours(48), "2 дн.")
    assert.equal(formatHours(null), "—")
  })
  it("picks the signed-in person as executor only when unambiguous", () => {
    const people = [
      { id: "1", full_name: "Иванов Иван", section_id: "s1", is_active: true },
      { id: "2", full_name: "Иванов Иван", section_id: "s2", is_active: true },
      { id: "3", full_name: "Петров Пётр", section_id: "s1", is_active: false },
    ]
    assert.equal(defaultExecutorId(people, "иванов иван", "s1"), "1")
    assert.equal(defaultExecutorId(people, "Иванов Иван", ""), "")
    assert.equal(defaultExecutorId(people, "Петров Пётр", "s1"), "")
    assert.equal(defaultExecutorId(people, null, "s1"), "")
  })
  it("recognises the same person despite initials, dots and ё", () => {
    assert.ok(sameName("Иванов Иван Петрович", "Иванов И.П."))
    assert.ok(sameName("Иванов И. П.", "иванов иван петрович"))
    assert.ok(sameName("Фёдоров Пётр", "Федоров Петр"))
    assert.ok(sameName("Иванов Иван", "Иванов"))
    assert.ok(!sameName("Иванов Иван", "Иванов Игорь"))
    assert.ok(!sameName("Иванов Иван", "Петров Иван"))
  })
  it("finds the signed-in employee uniquely and derives the default section", () => {
    const staff = [
      { id: "1", full_name: "Иванов Иван Петрович", section_id: "s1", is_active: true },
      { id: "2", full_name: "Иванов Олег", section_id: "s2", is_active: true },
      { id: "3", full_name: "Сидоров С.С.", section_id: "s2", is_active: true },
      { id: "4", full_name: "Сидоров Сергей", section_id: "s3", is_active: true },
    ]
    assert.equal(findMyEmployee(staff, "Иванов И.П.", null)?.id, "1")
    assert.equal(findMyEmployee(staff, "Сидоров Сергей Сергеевич", null), null)
    assert.equal(findMyEmployee(staff, "Сидоров Сергей Сергеевич", "s3")?.id, "4")
    assert.equal(defaultSectionId(staff, "Иванов И.П.", null), "s1")
    assert.equal(defaultSectionId(staff, "Иванов И.П.", "s9"), "s9")
    assert.equal(defaultSectionId(staff, "Неизвестный", null), "")
  })
  it("measures lateness in hours", () => {
    assert.equal(lateHours("2026-11-19T10:00:00Z", "2026-11-19T12:30:00Z"), 2.5)
    assert.equal(lateHours(null, "2026-11-19T12:30:00Z"), null)
  })
})
