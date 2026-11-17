"use client"

import { useEffect, useRef, useState } from "react"
import type * as Leaflet from "leaflet"
import "leaflet/dist/leaflet.css"
import "leaflet.markercluster/dist/MarkerCluster.css"
import "leaflet.markercluster/dist/MarkerCluster.Default.css"
import {
  SOURCE_LABEL, trainText, ageText, boundsOf, googleMapsLink, markerColor, type MapPoint,
} from "@/lib/map-view"

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string))
}

function popupHtml(p: MapPoint): string {
  const lines = [
    `<div style="font-weight:600;margin-bottom:2px">${escapeHtml(p.name)}</div>`,
    `<div>Инв. № ${escapeHtml(p.inv_number)}${p.section_name ? ` · ${escapeHtml(p.section_name)}` : ""}</div>`,
    p.status_name ? `<div>${escapeHtml(p.status_name)}</div>` : "",
    trainText(p) ? `<div>${escapeHtml(trainText(p) as string)}</div>` : "",
    `<div>Источник: ${SOURCE_LABEL[p.source]}${p.source !== "gtk" ? (p.online ? " · на связи" : " · нет связи") : ""}</div>`,
    `<div>Позиция: ${escapeHtml(ageText(p.position_at))}${p.speed != null && Number(p.speed) > 0 ? ` · ${Math.round(Number(p.speed))} км/ч` : ""}</div>`,
    `<div style="margin-top:4px"><a href="${googleMapsLink(p.lat, p.lon)}" target="_blank" rel="noopener noreferrer">Открыть в Google Maps</a> · ` +
      `<a href="/dashboard/directories/assets?q=${encodeURIComponent(p.inv_number)}">Карточка ОС</a></div>`,
  ]
  return `<div style="font-size:13px;line-height:1.35;color:#111827">${lines.join("")}</div>`
}

type Props = {
  points: MapPoint[]
  selectedId: string | null
  onSelect: (assetId: string | null) => void
  onError: (message: string) => void
}

type LeafletModule = typeof Leaflet
type ClusterGroup = Leaflet.MarkerClusterGroup

/** Keyless map: OpenStreetMap tiles + Leaflet. Same behaviour as the Google map (colours, clusters, popup). */
export function OsmAssetMap({ points, selectedId, onSelect, onError }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const libRef = useRef<LeafletModule | null>(null)
  const mapRef = useRef<Leaflet.Map | null>(null)
  const clusterRef = useRef<ClusterGroup | null>(null)
  const markersRef = useRef<Map<string, Leaflet.CircleMarker>>(new Map())
  const pointsRef = useRef<MapPoint[]>(points)
  const fittedRef = useRef(false)
  const onSelectRef = useRef(onSelect)
  const [ready, setReady] = useState(false)
  pointsRef.current = points
  onSelectRef.current = onSelect

  // A standalone popup (circle markers inside a cluster cannot always host their own popup).
  function showPopup(point: MapPoint) {
    const L = libRef.current
    const map = mapRef.current
    if (!L || !map) return
    map.setView([point.lat, point.lon], Math.max(map.getZoom(), 15))
    L.popup({ offset: [0, -4] }).setLatLng([point.lat, point.lon]).setContent(popupHtml(point)).openOn(map)
  }

  // 1) load Leaflet (browser only) and create the map once
  useEffect(() => {
    let cancelled = false
    const markers = markersRef.current
    ;(async () => {
      try {
        const leaflet = (await import("leaflet")).default as LeafletModule
        ;(window as unknown as { L: LeafletModule }).L = leaflet // markercluster plugin expects the global L
        await import("leaflet.markercluster")
        if (cancelled || !containerRef.current) return
        libRef.current = leaflet
        const map = leaflet.map(containerRef.current, { center: [41.3, 64.5], zoom: 6, worldCopyJump: true })
        leaflet
          .tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
          })
          .addTo(map)
        const cluster = leaflet.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50 })
        map.addLayer(cluster)
        mapRef.current = map
        clusterRef.current = cluster
        setReady(true)
      } catch (error) {
        if (!cancelled) onError(error instanceof Error ? error.message : "Не удалось загрузить карту OpenStreetMap")
      }
    })()
    return () => {
      cancelled = true
      mapRef.current?.remove()
      mapRef.current = null
      clusterRef.current = null
      markers.clear()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 2) (re)draw the markers when the points change
  useEffect(() => {
    const L = libRef.current
    const cluster = clusterRef.current
    const map = mapRef.current
    if (!ready || !L || !cluster || !map) return
    cluster.clearLayers()
    markersRef.current.clear()
    const created: Leaflet.CircleMarker[] = []
    for (const p of points) {
      const color = markerColor(p)
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: 7, color: "#ffffff", weight: 2, fillColor: color, fillOpacity: 0.95,
      })
      marker.bindTooltip(`${p.name} (${p.inv_number})`)
      marker.on("click", () => {
        onSelectRef.current(p.asset_id)
        showPopup(p)
      })
      markersRef.current.set(p.asset_id, marker)
      created.push(marker)
    }
    cluster.addLayers(created)
    if (!fittedRef.current && points.length > 0) {
      const b = boundsOf(points)
      if (b) {
        map.fitBounds([[b.south, b.west], [b.north, b.east]], { padding: [40, 40] })
        fittedRef.current = true
      }
    }
  }, [ready, points])

  // 3) the selected asset: centre on it and open its card
  useEffect(() => {
    const map = mapRef.current
    const cluster = clusterRef.current
    if (!ready || !map || !cluster) return
    if (!selectedId) {
      map.closePopup()
      return
    }
    const point = pointsRef.current.find((p) => p.asset_id === selectedId)
    if (!point) return
    showPopup(point)
    // re-open only when the selection changes, not on every 60 s refresh
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, selectedId])

  return <div ref={containerRef} className="relative z-0 h-full min-h-[420px] w-full rounded-xl" aria-label="Карта основных средств (OpenStreetMap)" />
}
