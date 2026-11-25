// Run with: npm run test:unit
import assert from "node:assert/strict"
import { describe, it } from "node:test"
import { fmtInt, fmtMoney, fmtNumber, fmtPercent } from "./format.ts"

const norm = (s: string) => s.replace(/[  ]/g, " ")

describe("format rules", () => {
  it("percent has 2 digits", () => {
    assert.equal(fmtPercent(12.3456), "12,35%")
    assert.equal(fmtPercent(5, true), "+5,00%")
    assert.equal(fmtPercent(-1.2), "-1,20%")
  })
  it("plain number has 1 digit", () => {
    assert.equal(fmtNumber(12.34), "12,3")
    assert.equal(fmtNumber(null), "—")
  })
  it("money has 3 digits and a unit", () => {
    assert.equal(norm(fmtMoney(2_794_916_150)), "2,795 млрд")
    assert.equal(norm(fmtMoney(1_234_567)), "1,235 млн")
    assert.equal(norm(fmtMoney(185_000)), "185,000 тыс")
    assert.equal(fmtMoney(undefined), "—")
  })
  it("integers have no fraction", () => {
    assert.equal(norm(fmtInt(1234)), "1 234")
  })
})
