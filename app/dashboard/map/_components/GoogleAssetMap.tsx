"use client"

import { withBase } from "@/lib/base-path"
import { useEffect, useRef, useState } from "react"
import { MarkerClusterer } from "@googlemaps/markerclusterer"
import {
  SOURCE_LABEL, trainText, ageText, boundsOf, googleMapsLink, markerColor, type MapPoint,
} from "@/lib/map-view"

const SCRIPT_ID = "toir-google-maps-script"
let loader: Promise<void> | null = null
// Google reports a refused key (InvalidKeyMapError, referrer, billing...) AFTER the script has loaded, so it needs its own channel.
let authFailed = false
const authListeners = new Set<() => void>()
const AUTH_MESSAGE = "Google Maps отклонил ключ API"

/** Loads the Google Maps JavaScript API once. Rejects when the key is refused or the network is blocked. */
function loadGoogleMaps(apiKey: string): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"))
  if (typeof window.google?.maps?.importLibrary === "function") return Promise.resolve()
  if (loader) return loader
  loader = new Promise<void>((resolve, reject) => {
    const callbackName = "__toirGoogleMapsReady"
    ;(window as unknown as Record<string, unknown>)[callbackName] = () => resolve()
    // Google calls this when the key is invalid / the referrer is not allowed.
    ;(window as unknown as Record<string, unknown>).gm_authFailure = () => {
      authFailed = true
      authListeners.forEach((listener) => listener())
      reject(new Error(AUTH_MESSAGE))
    }
    const script = document.createElement("script")
    script.id = SCRIPT_ID
    script.async = true
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&loading=async&libraries=marker&v=weekly&language=ru&callback=${callbackName}`
    script.onerror = () => reject(new Error("Не удалось загрузить Google Maps (нет доступа к интернету?)"))
    document.head.appendChild(script)
  }).catch((error) => {
    loader = null
    document.getElementById(SCRIPT_ID)?.remove()
    throw error
  })
  return loader
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string))
}

function infoHtml(p: MapPoint): string {
  const lines = [
    `<div style="font-weight:600;margin-bottom:2px">${escapeHtml(p.name)}</div>`,
    `<div>Инв. № ${escapeHtml(p.inv_number)}${p.section_name ? ` · ${escapeHtml(p.section_name)}` : ""}</div>`,
    p.status_name ? `<div>${escapeHtml(p.status_name)}</div>` : "",
    trainText(p) ? `<div>${escapeHtml(trainText(p) as string)}</div>` : "",
    `<div>Источник: ${SOURCE_LABEL[p.source]}${p.source !== "gtk" ? (p.online ? " · на связи" : " · нет связи") : ""}</div>`,
    `<div>Позиция: ${escapeHtml(ageText(p.position_at))}${p.speed != null && Number(p.speed) > 0 ? ` · ${Math.round(Number(p.speed))} км/ч` : ""}</div>`,
    `<div style="margin-top:4px"><a href="${googleMapsLink(p.lat, p.lon)}" target="_blank" rel="noopener noreferrer">Открыть в Google Maps</a> · ` +
      `<a href="${withBase('')}/dashboard/directories/assets?q=${encodeURIComponent(p.inv_number)}">Карточка ОС</a></div>`,
  ]
  return `<div style="font-size:13px;line-height:1.35;color:#111827">${lines.join("")}</div>`
}

type Props = {
  apiKey: string
  points: MapPoint[]
  selectedId: string | null
  onSelect: (assetId: string | null) => void
  onError: (message: string) => void
}

export function GoogleAssetMap({ apiKey, points, selectedId, onSelect, onError }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<google.maps.Map | null>(null)
  const clustererRef = useRef<MarkerClusterer | null>(null)
  const infoRef = useRef<google.maps.InfoWindow | null>(null)
  const markersRef = useRef<Map<string, google.maps.marker.AdvancedMarkerElement>>(new Map())
  const pointsRef = useRef<MapPoint[]>(points)
  const fittedRef = useRef(false)
  const [ready, setReady] = useState(false)
  pointsRef.current = points

  // 1) load the API and create the map once
  useEffect(() => {
    let cancelled = false
    const onAuthFailure = () => !cancelled && onError(AUTH_MESSAGE)
    authListeners.add(onAuthFailure)
    if (authFailed) onAuthFailure()
    loadGoogleMaps(apiKey)
      .then(async () => {
        if (cancelled || !containerRef.current) return
        await google.maps.importLibrary("maps")
        await google.maps.importLibrary("marker")
        // DEMO_MAP_ID lets advanced markers work without creating a Cloud map style
        mapRef.current = new google.maps.Map(containerRef.current, {
          center: { lat: 41.3, lng: 64.5 }, zoom: 6, mapId: "DEMO_MAP_ID", mapTypeControl: true, streetViewControl: false,
          fullscreenControl: true,
        })
        infoRef.current = new google.maps.InfoWindow()
        clustererRef.current = new MarkerClusterer({ map: mapRef.current, markers: [] })
        setReady(true)
      })
      .catch((error: Error) => !cancelled && onError(error.message))
    return () => {
      cancelled = true
      authListeners.delete(onAuthFailure)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey])

  // 2) (re)draw the markers when the points change
  useEffect(() => {
    if (!ready || !mapRef.current || !clustererRef.current) return
    const clusterer = clustererRef.current
    clusterer.clearMarkers()
    markersRef.current.clear()
    const created: google.maps.marker.AdvancedMarkerElement[] = []
    for (const p of points) {
      const pin = new google.maps.marker.PinElement({
        background: markerColor(p), borderColor: "#ffffff", glyphColor: "#ffffff", scale: 0.8,
      })
      const marker = new google.maps.marker.AdvancedMarkerElement({
        position: { lat: p.lat, lng: p.lon }, title: `${p.name} (${p.inv_number})`, content: pin.element,
      })
      marker.addListener("click", () => onSelect(p.asset_id))
      markersRef.current.set(p.asset_id, marker)
      created.push(marker)
    }
    clusterer.addMarkers(created)
    if (!fittedRef.current && points.length > 0) {
      const b = boundsOf(points)
      if (b) {
        mapRef.current.fitBounds({ south: b.south, west: b.west, north: b.north, east: b.east }, 40)
        fittedRef.current = true
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, points])

  // 3) the selected asset: centre on it and open its card
  useEffect(() => {
    if (!ready || !mapRef.current || !infoRef.current) return
    if (!selectedId) {
      infoRef.current.close()
      return
    }
    const point = pointsRef.current.find((p) => p.asset_id === selectedId)
    const marker = markersRef.current.get(selectedId)
    if (!point || !marker) return
    mapRef.current.panTo({ lat: point.lat, lng: point.lon })
    if ((mapRef.current.getZoom() ?? 0) < 12) mapRef.current.setZoom(12)
    infoRef.current.setContent(infoHtml(point))
    infoRef.current.open({ map: mapRef.current, anchor: marker })
  }, [ready, selectedId, points])

  return <div ref={containerRef} className="h-full min-h-[420px] w-full rounded-xl" aria-label="Карта основных средств" />
}
