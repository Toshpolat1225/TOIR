"use client"

import { useEffect } from "react"
import { api } from "@/lib/api"

export type RealtimeEvent = {
  resource: "work_orders" | "fixed_assets" | "users"
  action: "created" | "updated" | "deleted"
  id: string
}

type EventHandler = (event: RealtimeEvent) => void

const allowedTables = new Set<RealtimeEvent["resource"]>([
  "work_orders",
  "fixed_assets",
  "users",
])

type Listener = { handler: EventHandler; tables: Set<RealtimeEvent["resource"]> }

let socket: WebSocket | null = null
const listeners = new Set<Listener>()
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let isConnecting = false
let connectGeneration = 0

function subscribedTables() {
  return [...new Set([...listeners].flatMap((listener) => [...listener.tables]))]
}

function sendSubscription() {
  if (socket?.readyState !== WebSocket.OPEN) return
  socket.send(JSON.stringify({ type: "subscribe", tables: subscribedTables() }))
}

function scheduleReconnect() {
  if (reconnectTimer || listeners.size === 0) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    void connect()
  }, 5000)
}

async function connect() {
  if (socket || isConnecting || listeners.size === 0) return

  isConnecting = true
  const generation = ++connectGeneration
  try {
    const accessToken = await api.auth.getAccessToken()
    if (generation !== connectGeneration || listeners.size === 0) return

    const apiUrl = new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010/api/v1")
    const protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl = new URL("/ws", apiUrl)
    wsUrl.protocol = protocol

    const connection = new WebSocket(wsUrl.toString())
    socket = connection
    connection.onopen = () => {
      connection.send(JSON.stringify({
        type: "auth",
        access_token: accessToken,
        tables: subscribedTables(),
      }))
    }
    connection.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data) as RealtimeEvent
        if (
          !allowedTables.has(parsed.resource) ||
          !["created", "updated", "deleted"].includes(parsed.action) ||
          typeof parsed.id !== "string"
        ) return
        listeners.forEach((listener) => {
          if (listener.tables.has(parsed.resource)) listener.handler(parsed)
        })
      } catch (error) {
        console.error("Realtime: Error parsing message", error)
      }
    }
    connection.onclose = () => {
      if (socket === connection) socket = null
      scheduleReconnect()
    }
    connection.onerror = () => connection.close()
  } catch (error) {
    console.error("Realtime: Could not authenticate WebSocket", error)
    scheduleReconnect()
  } finally {
    isConnecting = false
  }
}

export function useRealtime(
  handler: EventHandler,
  tables: RealtimeEvent["resource"][] = ["work_orders", "fixed_assets", "users"],
) {
  const tableKey = [...new Set(tables.filter((table) => allowedTables.has(table)))].sort().join("|")
  useEffect(() => {
    const listener: Listener = {
      handler,
      tables: new Set(tableKey ? tableKey.split("|") as RealtimeEvent["resource"][] : []),
    }
    listeners.add(listener)
    void connect()
    sendSubscription()

    return () => {
      listeners.delete(listener)
      if (listeners.size === 0) {
        connectGeneration += 1
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
        socket?.close()
        socket = null
      } else {
        sendSubscription()
      }
    }
  }, [handler, tableKey])
}
