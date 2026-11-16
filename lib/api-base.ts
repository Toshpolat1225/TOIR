/**
 * Where the browser finds the backend.
 *
 * `NEXT_PUBLIC_API_URL` is baked into the bundle at build time. It may be an absolute URL
 * ("http://localhost:8010/api/v1", the development default) or a RELATIVE path ("/api/v1"): a relative path is
 * resolved against the address the page itself was opened from, so one build works over both http:// and https://
 * and under any host name or IP (no rebuild when the address or the protocol changes).
 */

const DEV_DEFAULT = "http://localhost:8010/api/v1"

/** `configured` is NEXT_PUBLIC_API_URL; `origin` is the page's origin (e.g. "https://192.168.28.104"). */
export function resolveApiBase(configured: string | undefined, origin: string | undefined): string {
  const value = (configured ?? "").trim()
  if (!value) return DEV_DEFAULT
  if (value.startsWith("/")) {
    if (!origin) throw new Error("A relative API address needs the page origin (browser only)")
    return `${origin.replace(/\/+$/, "")}${value.replace(/\/+$/, "")}`
  }
  return value.replace(/\/+$/, "")
}

/** The WebSocket address of the realtime channel: same host as the API, `/ws`, wss:// when the API is https://. */
export function realtimeSocketUrl(apiBase: string): string {
  const api = new URL(apiBase)
  const socket = new URL("/ws", api)
  socket.protocol = api.protocol === "https:" ? "wss:" : "ws:"
  return socket.toString()
}

/** Reads the build-time setting; the literal `process.env.NEXT_PUBLIC_API_URL` is what Next.js inlines. */
export function apiBaseUrl(): string {
  const origin = typeof window !== "undefined" ? window.location.origin : undefined
  return resolveApiBase(process.env.NEXT_PUBLIC_API_URL, origin)
}
