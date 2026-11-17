"use client"

import { useEffect, useRef, useState } from "react"
import type * as Leaflet from "leaflet"
import "leaflet/dist/leaflet.css"
import { boundsOfLists } from "@/lib/gps-view"

export type GpsMarker = {
  id: string; lat: number; lon: number; color: string; label: string
  /** A stale fix: drawn hollow so a silent tracker is visible at a glance. */
  hollow?: boolean
  /** The OTHER tracker's fix of the same locomotive: a small dashed ring (clicking it selects `selectId`). */
  ghost?: boolean
  selectId?: string
}
export type GpsLine = { id: string; points: [number, number][]; color: string; weight?: number; dashed?: boolean; label?: string; ends?: boolean }

type Props = {
  markers?: GpsMarker[]
  lines?: GpsLine[]
  selectedId?: string | null
  onSelect?: (id: string) => void
  onError: (message: string) => void
  testId: string
  ariaLabel: string
  /** The view is fitted to the data when this key changes (and once at the start). */
  fitKey?: string | number
  className?: string
}

/** A small OpenStreetMap pane: coloured fix markers and/or polylines. Used by the GPS comparison page and the detail page. */
export function GpsMap({ markers = [], lines = [], selectedId = null, onSelect, onError, testId, ariaLabel, fitKey = "", className = "" }: Props) {
  const container = useRef<HTMLDivElement | null>(null)
  const lib = useRef<typeof Leaflet | null>(null)
  const map = useRef<Leaflet.Map | null>(null)
  const layer = useRef<Leaflet.LayerGroup | null>(null)
  const fitted = useRef<string | number | null>(null)
  const pick = useRef(onSelect)
  const selectedRef = useRef(selectedId)
  const [ready, setReady] = useState(false)
  pick.current = onSelect
  selectedRef.current = selectedId

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const L = (await import("leaflet")).default as typeof Leaflet
        if (cancelled || !container.current) return
        lib.current = L
        const m = L.map(container.current, { center: [40.85, 69.57], zoom: 9, maxZoom: 19 })
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
        }).addTo(m)
        layer.current = L.layerGroup().addTo(m)
        map.current = m
        setReady(true)
      } catch (error) {
        if (!cancelled) onError(error instanceof Error ? error.message : "Не удалось загрузить карту")
      }
    })()
    return () => { cancelled = true; map.current?.remove(); map.current = null; layer.current = null; fitted.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // everything on the map is drawn from the props
  useEffect(() => {
    const L = lib.current, group = layer.current, m = map.current
    if (!ready || !L || !group || !m) return
    group.clearLayers()
    for (const line of lines) {
      if (line.points.length < 2) continue
      const poly = L.polyline(line.points, { color: line.color, weight: line.weight ?? 4, opacity: 0.85, dashArray: line.dashed ? "6 6" : undefined, lineJoin: "round" }).addTo(group)
      if (line.label) poly.bindTooltip(line.label, { sticky: true })
      if (line.ends) {
        const first = line.points[0], last = line.points[line.points.length - 1]
        L.circleMarker(first, { radius: 6, color: "#fff", weight: 2, fillColor: "#10b981", fillOpacity: 1 }).bindTooltip("начало").addTo(group)
        L.circleMarker(last, { radius: 7, color: "#fff", weight: 2, fillColor: line.color, fillOpacity: 1 }).bindTooltip("последняя точка").addTo(group)
      }
    }
    for (const mk of markers) {
      if (mk.ghost) {
        L.circleMarker([mk.lat, mk.lon], { radius: 6, color: mk.color, weight: 2, dashArray: "3 3", fillColor: "#fff", fillOpacity: 0.6 }).bindTooltip(mk.label).on("click", () => pick.current?.(mk.selectId ?? mk.id)).addTo(group)
        continue
      }
      const selected = mk.id === selectedId
      if (selected) L.circleMarker([mk.lat, mk.lon], { radius: 15, color: "#ef4444", weight: 3, fill: false, interactive: false }).addTo(group)
      const dot = L.circleMarker([mk.lat, mk.lon], { radius: selected ? 9 : 7, color: mk.color, weight: 2.5, fillColor: mk.color, fillOpacity: mk.hollow ? 0.12 : 0.9 }).addTo(group)
      dot.bindTooltip(mk.label)
      dot.on("click", () => pick.current?.(mk.selectId ?? mk.id))
    }
    const key = `${fitKey}`
    if (fitted.current !== key) {
      const b = boundsOfLists([markers, lines.flatMap((l) => l.points.map(([lat, lon]) => ({ lat, lon })))])
      if (b) { m.fitBounds(b, { padding: [30, 30], maxZoom: 14 }); fitted.current = key }
    }
  }, [ready, markers, lines, selectedId, fitKey])

  // choosing a locomotive elsewhere (the table, the other map) brings it to the middle here
  useEffect(() => {
    const m = map.current
    if (!ready || !m || !selectedId) return
    const mk = markers.find((x) => x.id === selectedId && !x.ghost)
    if (mk) m.setView([mk.lat, mk.lon], Math.max(m.getZoom(), 12), { animate: true })
    // only when the choice changes, not on every refresh of the points
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, selectedId])

  return <div ref={container} className={`relative z-0 h-full min-h-[300px] w-full rounded-xl ${className}`} aria-label={ariaLabel} data-testid={testId} data-count={markers.length + lines.length} />
}
