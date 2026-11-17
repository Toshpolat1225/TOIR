"use client"

import { useEffect, useRef, useState } from "react"
import type * as Leaflet from "leaflet"
import "leaflet/dist/leaflet.css"
import { historyBounds, pointAt, segmentColor, type HistoryPoint, type HistorySegment } from "@/lib/map-history"

type Props = {
  track: HistoryPoint[]
  segments: HistorySegment[]
  activeIndex: number | null
  /** The moment chosen with the time scrubber (ms); the marker sits on the track point at or before it. */
  scrubAt: number | null
  onPick?: (index: number) => void
  onError: (message: string) => void
}

const pulse = `<span style="position:relative;display:block;width:18px;height:18px"><span style="position:absolute;inset:0;border-radius:9999px;background:#ef4444;opacity:.35;animation:trackPulse 1.6s ease-out infinite"></span><span style="position:absolute;inset:4px;border-radius:9999px;background:#ef4444;border:2px solid #fff"></span></span><style>@keyframes trackPulse{0%{transform:scale(.6);opacity:.6}100%{transform:scale(1.9);opacity:0}}</style>`

/** The track of one asset on OpenStreetMap: a coloured line per train segment, the start, the last position and a time scrubber marker. */
export function TrackMap({ track, segments, activeIndex, scrubAt, onPick, onError }: Props) {
  const container = useRef<HTMLDivElement | null>(null)
  const lib = useRef<typeof Leaflet | null>(null)
  const map = useRef<Leaflet.Map | null>(null)
  const layer = useRef<Leaflet.LayerGroup | null>(null)
  const scrub = useRef<Leaflet.Marker | null>(null)
  const lines = useRef<Leaflet.Polyline[]>([])
  const fitted = useRef(false)
  const pick = useRef(onPick)
  const [ready, setReady] = useState(false)
  pick.current = onPick

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const L = (await import("leaflet")).default as typeof Leaflet
        if (cancelled || !container.current) return
        lib.current = L
        const m = L.map(container.current, { center: [41.3, 64.5], zoom: 7 })
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
    return () => { cancelled = true; map.current?.remove(); map.current = null; layer.current = null; scrub.current = null; lines.current = []; fitted.current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // the lines, the start and the end
  useEffect(() => {
    const L = lib.current, group = layer.current, m = map.current
    if (!ready || !L || !group || !m) return
    group.clearLayers()
    lines.current = []
    const claimed = new Set<number>()
    segments.forEach((s, i) => {
      const from = new Date(s.from_at).getTime(), to = s.to_at ? new Date(s.to_at).getTime() : Date.now()
      const pts = track.map((p, idx) => ({ p, idx })).filter(({ p }) => { const t = new Date(p.at).getTime(); return t >= from && t <= to })
      pts.forEach(({ idx }) => claimed.add(idx))
      if (pts.length === 0) return
      const line = L.polyline(pts.map(({ p }) => [p.lat, p.lon] as [number, number]), { color: segmentColor(i), weight: 4, opacity: 0.85 })
        .bindTooltip(`${s.loco_label ?? "локомотив не определён"} · ${new Date(s.from_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`, { sticky: true })
        .on("click", () => pick.current?.(i))
        .addTo(group)
      lines.current[i] = line
    })
    const loose = track.filter((_, idx) => !claimed.has(idx))
    if (loose.length > 1) L.polyline(loose.map((p) => [p.lat, p.lon] as [number, number]), { color: "#64748b", weight: 3, opacity: 0.7, dashArray: "6 6" }).addTo(group)
    if (track.length > 0) {
      L.circleMarker([track[0].lat, track[0].lon], { radius: 7, color: "#fff", weight: 2, fillColor: "#10b981", fillOpacity: 1 }).bindTooltip("начало периода").addTo(group)
      const last = track[track.length - 1]
      L.marker([last.lat, last.lon], { icon: L.divIcon({ html: pulse, className: "", iconSize: [18, 18], iconAnchor: [9, 9] }) }).bindTooltip("последняя известная позиция").addTo(group)
      if (!fitted.current) {
        const b = historyBounds(track)
        if (b) { m.fitBounds(b, { padding: [40, 40], maxZoom: 15 }); fitted.current = true }
      }
    }
  }, [ready, track, segments])

  // the chosen segment: thicker line and fit to it
  useEffect(() => {
    const m = map.current
    if (!ready || !m) return
    lines.current.forEach((line, i) => line?.setStyle({ weight: i === activeIndex ? 8 : 4, opacity: activeIndex === null || i === activeIndex ? 0.95 : 0.35 }))
    if (activeIndex !== null && lines.current[activeIndex]) {
      lines.current[activeIndex].bringToFront()
      m.fitBounds(lines.current[activeIndex].getBounds(), { padding: [50, 50], maxZoom: 16 })
    }
  }, [ready, activeIndex])

  // the time scrubber
  useEffect(() => {
    const L = lib.current, group = layer.current
    if (!ready || !L || !group) return
    if (scrubAt === null) { if (scrub.current) { group.removeLayer(scrub.current); scrub.current = null } return }
    const p = pointAt(track, scrubAt)
    if (!p) return
    if (!scrub.current) {
      scrub.current = L.marker([p.lat, p.lon], { zIndexOffset: 1000, icon: L.divIcon({ html: '<span style="display:block;width:20px;height:20px;border-radius:9999px;background:#facc15;border:3px solid #111827;box-shadow:0 0 0 3px rgba(250,204,21,.4)"></span>', className: "", iconSize: [20, 20], iconAnchor: [10, 10] }) }).addTo(group)
    } else scrub.current.setLatLng([p.lat, p.lon])
  }, [ready, scrubAt, track])

  return <div ref={container} className="relative z-0 h-full min-h-[360px] w-full rounded-xl" aria-label="Трек на карте (OpenStreetMap)" data-testid="track-map" />
}
