// Run with: npm run test:unit
import assert from "node:assert/strict"
import { describe, it } from "node:test"
import { realtimeSocketUrl, resolveApiBase } from "./api-base.ts"

describe("resolveApiBase", () => {
  it("falls back to the development address when nothing is configured", () => {
    assert.equal(resolveApiBase(undefined, undefined), "http://localhost:8010/api/v1")
    assert.equal(resolveApiBase("  ", "https://x"), "http://localhost:8010/api/v1")
  })

  it("keeps an absolute address, without a trailing slash", () => {
    assert.equal(resolveApiBase("http://192.168.28.104/api/v1/", "https://192.168.28.104"), "http://192.168.28.104/api/v1")
  })

  it("resolves a relative address against the page origin, so http and https both work", () => {
    assert.equal(resolveApiBase("/api/v1", "http://192.168.28.104"), "http://192.168.28.104/api/v1")
    assert.equal(resolveApiBase("/api/v1/", "https://192.168.28.104/"), "https://192.168.28.104/api/v1")
  })

  it("refuses a relative address when there is no page (server side)", () => {
    assert.throws(() => resolveApiBase("/api/v1", undefined))
  })
})

describe("realtimeSocketUrl", () => {
  it("uses ws:// for http and wss:// for https, always at /ws", () => {
    assert.equal(realtimeSocketUrl("http://192.168.28.104/api/v1"), "ws://192.168.28.104/ws")
    assert.equal(realtimeSocketUrl("https://192.168.28.104/api/v1"), "wss://192.168.28.104/ws")
    assert.equal(realtimeSocketUrl("http://localhost:8010/api/v1"), "ws://localhost:8010/ws")
  })
})
