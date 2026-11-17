"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import type * as Leaflet from "leaflet"
import "leaflet/dist/leaflet.css"
import "leaflet.markercluster/dist/MarkerCluster.css"
import "leaflet.markercluster/dist/MarkerCluster.Default.css"
import { SOURCE_LABEL, trainText, ageText, boundsOf, googleMapsLink, type MapPoint } from "@/lib/map-view"
import { gpsPointLines, positionColor } from "@/lib/gps-view"
import {
  TRUE_SCALE_ZOOM, iconKind, iconSvg, iconWidth, locoOutline, statusOf, strip, trainBounds, trainCaption, vehicleCorners, vehicleFill, KIND_LABEL,
  type FormationVehicle, type LiveTrain,
} from "@/lib/map-icons"

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string))
}

function popupHtml(p: MapPoint): string {
  const gps = gpsPointLines(p)
  const lines = [
    `<div style="font-weight:600;margin-bottom:2px">${escapeHtml(p.name)}</div>`,
    `<div>${escapeHtml(KIND_LABEL[iconKind(p)])} · Инв. № ${escapeHtml(p.inv_number)}${p.section_name ? ` · ${escapeHtml(p.section_name)}` : ""}</div>`,
    p.status_name ? `<div>${escapeHtml(p.status_name)}</div>` : "",
    trainText(p) ? `<div>${escapeHtml(trainText(p) as string)}</div>` : "",
    `<div>Источник: ${SOURCE_LABEL[p.source]}${p.source !== "gtk" ? (p.online ? " · на связи" : " · нет связи") : ""}</div>`,
    `<div>Позиция: ${escapeHtml(ageText(p.position_at))}${p.speed != null && Number(p.speed) > 0 ? ` · ${Math.round(Number(p.speed))} км/ч` : ""}</div>`,
    gps
      ? `<div style="margin-top:4px;padding:4px 6px;border-radius:6px;background:#f3f4f6"><div style="font-weight:600"><span style="display:inline-block;width:9px;height:9px;border-radius:9999px;background:${positionColor(gps.verdict)};margin-right:5px"></span>${escapeHtml(gps.verdictLabel)}</div>` +
        `<div>Рисуется: ${escapeHtml(gps.drawn)}</div>${gps.other ? `<div>Второй трекер: ${escapeHtml(gps.other)}</div>` : ""}${gps.diff ? `<div>Между точками: ${escapeHtml(gps.diff)}</div>` : ""}</div>`
      : "",
    `<div style="margin-top:4px"><a href="/dashboard/map/history/${p.asset_id}">Где был и с кем</a>${gps ? ` · <a href="/dashboard/gps/${p.asset_id}">Сравнение GPS</a>` : ""} · <a href="${googleMapsLink(p.lat, p.lon)}" target="_blank" rel="noopener noreferrer">Google Maps</a> · ` +
      `<a href="/dashboard/directories/assets?q=${encodeURIComponent(p.inv_number)}">Карточка ОС</a></div>`,
  ]
  return `<div style="font-size:13px;line-height:1.35;color:#111827">${lines.join("")}</div>`
}

function trainPopupHtml(t: LiveTrain, focus?: FormationVehicle): string {
  const link = (id: string | null, label: string) => (id ? `<a href="/dashboard/map/history/${id}">${escapeHtml(label)}</a>` : `<span style="color:#6b7280">${escapeHtml(label)}</span>`)
  const wagons = t.vehicles.filter((v) => v.role === "wagon")
  const rows = [
    `<div style="font-weight:600">⚡ ${escapeHtml(trainCaption(t))}</div>`,
    focus ? `<div style="margin-top:2px">Выбран: <b>${escapeHtml(focus.label ?? "вагон другого участка")}</b>${focus.role === "wagon" ? ` · ${focus.ord}-й от локомотива` : ""}</div>` : "",
    `<div style="margin-top:4px">${t.loco_asset_id ? link(t.loco_asset_id, `Локомотив ${t.loco_inv_number ?? ""}`) : ""}</div>`,
    `<div style="margin-top:4px;width:300px;display:flex;flex-wrap:wrap;gap:2px 8px">${wagons.slice(0, 18).map((v) => link(v.asset_id, `${v.ord}. ${v.label ?? "?"}`)).join("")}${wagons.length > 18 ? `<span style="color:#6b7280">и ещё ${wagons.length - 18}</span>` : ""}</div>`,
    t.heading_known ? "" : `<div style="margin-top:4px;color:#92400e">Направление не записано: состав нарисован условно.</div>`,
  ]
  return `<div style="font-size:13px;line-height:1.35;color:#111827">${rows.join("")}</div>`
}

type Props = {
  points: MapPoint[]
  trains: LiveTrain[]
  selectedId: string | null
  onSelect: (assetId: string | null) => void
  onError: (message: string) => void
}

type LeafletModule = typeof Leaflet

const STYLE = ".veh-label{background:transparent!important;border:0!important;box-shadow:none!important;color:#fff;font:600 10px/1 sans-serif;padding:0!important}.veh-label:before{display:none!important}.pt-icon{background:transparent!important;border:0!important}"

/** Keyless map: OpenStreetMap + Leaflet. Units are pictograms by type; a train is a pictogram with a car count and, from zoom 16, a true-scale formation. */
export function OsmAssetMap({ points, trains, selectedId, onSelect, onError }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const libRef = useRef<LeafletModule | null>(null)
  const mapRef = useRef<Leaflet.Map | null>(null)
  const clusterRef = useRef<Leaflet.MarkerClusterGroup | null>(null)
  const trainLayerRef = useRef<Leaflet.LayerGroup | null>(null)
  const altLayerRef = useRef<Leaflet.LayerGroup | null>(null)
  const markersRef = useRef<Map<string, Leaflet.Marker>>(new Map())
  const fittedRef = useRef(false)
  const onSelectRef = useRef(onSelect)
  const [ready, setReady] = useState(false)
  const [zoom, setZoom] = useState(6)
  const [view, setView] = useState(0)
  onSelectRef.current = onSelect

  // units drawn as pictograms: everything except the wagons that ride in a drawn train and the locomotives that head one
  const loose = useMemo(() => {
    const heads = new Set(trains.map((t) => t.loco_asset_id).filter((id): id is string => !!id))
    return points.filter((p) => p.source !== "train" && !heads.has(p.asset_id))
  }, [points, trains])
  const looseRef = useRef(loose)
  looseRef.current = loose
  const trainsRef = useRef(trains)
  trainsRef.current = trains
  const sizeBucket = zoom <= 7 ? 0 : zoom <= 11 ? 1 : 2
  const selectedRef = useRef<string | null>(selectedId)
  selectedRef.current = selectedId
  const pointIcon = (p: MapPoint, selected: boolean) => {
    const L = libRef.current as LeafletModule
    const kind = iconKind(p)
    const w = iconWidth(mapRef.current?.getZoom() ?? 6, kind)
    return L.divIcon({ className: "pt-icon", html: iconSvg(kind, statusOf(p), w, selected, p.gps_verdict ? positionColor(p.gps_verdict) : null), iconSize: [w, Math.round((w * 24) / 40)], iconAnchor: [w / 2, Math.round((w * 12) / 40)] })
  }

  function showPopup(lat: number, lon: number, html: string, minZoom = 15) {
    const L = libRef.current, map = mapRef.current
    if (!L || !map) return
    try {
      map.setView([lat, lon], Math.max(map.getZoom(), minZoom))
      L.popup({ offset: [0, -4], maxWidth: 340 }).setLatLng([lat, lon]).setContent(html).openOn(map)
    } catch {
      // the map was re-drawn under the popup (a refresh at the same moment): the next click opens it again
    }
  }

  // 1) the map, created once
  useEffect(() => {
    let cancelled = false
    const markers = markersRef.current
    ;(async () => {
      try {
        const leaflet = (await import("leaflet")).default as LeafletModule
        ;(window as unknown as { L: LeafletModule }).L = leaflet
        await import("leaflet.markercluster")
        if (cancelled || !containerRef.current) return
        libRef.current = leaflet
        const map = leaflet.map(containerRef.current, { center: [41.3, 64.5], zoom: 6, worldCopyJump: true, maxZoom: 20 })
        leaflet.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 20, maxNativeZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
        }).addTo(map)
        const cluster = leaflet.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45, disableClusteringAtZoom: 15 })
        map.addLayer(cluster)
        altLayerRef.current = leaflet.layerGroup().addTo(map)
        trainLayerRef.current = leaflet.layerGroup().addTo(map)
        map.on("zoomend", () => setZoom(map.getZoom()))
        map.on("moveend", () => setView((v) => v + 1))
        mapRef.current = map
        clusterRef.current = cluster
        setZoom(map.getZoom())
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
      trainLayerRef.current = null
      altLayerRef.current = null
      markers.clear()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 2) pictograms of the loose units (re-drawn when the points change or the icon size bucket changes)
  useEffect(() => {
    const L = libRef.current, cluster = clusterRef.current, map = mapRef.current
    if (!ready || !L || !cluster || !map) return
    cluster.clearLayers()
    markersRef.current.clear()
    const created: Leaflet.Marker[] = []
    for (const p of loose) {
      const marker = L.marker([p.lat, p.lon], { icon: pointIcon(p, p.asset_id === selectedRef.current), title: `${p.name} (${p.inv_number})` })
      marker.on("click", () => { onSelectRef.current(p.asset_id); showPopup(p.lat, p.lon, popupHtml(p)) })
      markersRef.current.set(p.asset_id, marker)
      created.push(marker)
    }
    cluster.addLayers(created)
    if (!fittedRef.current && points.length > 0) {
      const b = boundsOf(points)
      if (b) { map.fitBounds([[b.south, b.west], [b.north, b.east]], { padding: [40, 40] }); fittedRef.current = true }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, loose, sizeBucket])

  // 2b) the red frame moves with the selection without re-drawing every marker
  const framed = useRef<string | null>(null)
  useEffect(() => {
    if (!ready || !libRef.current) return
    for (const id of [framed.current, selectedId]) {
      const marker = id ? markersRef.current.get(id) : null
      const p = id ? looseRef.current.find((x) => x.asset_id === id) : null
      if (marker && p) marker.setIcon(pointIcon(p, id === selectedId))
    }
    framed.current = selectedId
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, selectedId])

  // 2c) the OTHER tracker of a locomotive: a dashed line and a ghost ring when the two disagree or one is silent
  useEffect(() => {
    const L = libRef.current, layer = altLayerRef.current
    if (!ready || !L || !layer) return
    layer.clearLayers()
    for (const p of loose) {
      if (p.alt_lat == null || p.alt_lon == null || !p.gps_verdict || p.gps_verdict === "confirmed" || p.gps_verdict === "both_stale_agree") continue
      const color = positionColor(p.gps_verdict)
      L.polyline([[p.lat, p.lon], [p.alt_lat, p.alt_lon]], { color, weight: 2, dashArray: "5 6", opacity: 0.9, interactive: false }).addTo(layer)
      const gps = gpsPointLines(p)
      L.circleMarker([p.alt_lat, p.alt_lon], { radius: 7, color, weight: 2.5, dashArray: "3 3", fillColor: "#fff", fillOpacity: 0.7 })
        .bindTooltip(`${p.inv_number}: ${p.alt_source === "gtk_gps" ? "GTK GPS" : "Wialon"} (второй трекер)${gps?.other ? ` · ${gps.other.split(": ")[1] ?? ""}` : ""}`)
        .on("click", () => { onSelectRef.current(p.asset_id); showPopup(p.lat, p.lon, popupHtml(p), 14) })
        .addTo(layer)
    }
  }, [ready, loose])

  // 3) trains: a pictogram with a car count far away, the formation to scale up close
  useEffect(() => {
    const L = libRef.current, layer = trainLayerRef.current, map = mapRef.current
    if (!ready || !L || !layer || !map) return
    layer.clearLayers()
    if (zoom < TRUE_SCALE_ZOOM) {
      for (const t of trains) {
        const kind = t.loco_kind
        const w = iconWidth(zoom, kind) + 8
        const selected = t.loco_asset_id !== null && t.loco_asset_id === selectedId
        const arrow = t.moving ? `<span style="position:absolute;left:-13px;top:50%;margin-top:-8px;transform:rotate(${t.heading}deg);font-size:13px;line-height:16px;color:#16a34a;text-shadow:0 0 2px #fff">▲</span>` : ""
        const html = `<div style="position:relative;width:${w}px">${iconSvg(kind, t.moving ? "online" : "train", w, selected)}<span style="position:absolute;right:-8px;bottom:-9px;background:#111827;color:#fff;border-radius:9999px;font:600 11px/16px sans-serif;padding:0 6px;border:1.5px solid #fff">${t.wagons_count}</span>${arrow}</div>`
        const marker = L.marker([t.lat, t.lon], { icon: L.divIcon({ className: "pt-icon", html, iconSize: [w, Math.round((w * 24) / 40)], iconAnchor: [w / 2, Math.round((w * 12) / 40)] }), zIndexOffset: 500, title: trainCaption(t) })
        marker.on("click", () => { if (t.loco_asset_id) onSelectRef.current(t.loco_asset_id); showPopup(t.lat, t.lon, trainPopupHtml(t), 15) })
        marker.addTo(layer)
      }
      return
    }
    const bounds = map.getBounds().pad(0.4)
    for (const t of trains) {
      if (!bounds.contains([t.lat, t.lon]) && !t.vehicles.some((v) => bounds.contains([v.lat, v.lon]))) continue
      for (const v of t.vehicles) {
        const hot = v.asset_id !== null && v.asset_id === selectedId
        const fill = v.hidden ? "#94a3b8" : vehicleFill(v.kind, v.is_loaded)
        const shape = v.role === "loco" ? locoOutline(v.lat, v.lon, v.heading, v.length_m, v.width_m) : vehicleCorners(v.lat, v.lon, v.heading, v.length_m, v.width_m)
        const poly = L.polygon(shape, { color: hot ? "#ef4444" : "#0f172a", weight: hot ? 3 : 1, fillColor: fill, fillOpacity: 0.95 }).addTo(layer)
        const title = v.hidden ? "вагон другого участка" : `${v.label ?? "вагон"}${v.role === "wagon" ? ` · ${v.ord}-й от локомотива` : v.role === "motor" ? " · моторный вагон" : ""}`
        poly.bindTooltip(title, { sticky: true })
        poly.on("click", () => { if (v.asset_id) onSelectRef.current(v.asset_id); showPopup(v.lat, v.lon, trainPopupHtml(t, v), zoom) })
        const mark = (coords: [number, number][], color: string, opacity = 1) => L.polygon(coords, { stroke: false, fillColor: color, fillOpacity: opacity, interactive: false }).addTo(layer)
        const half = v.length_m / 2
        if (v.role === "loco") mark(strip(v.lat, v.lon, v.heading, half - 4.4, half - 2.3, v.width_m * 0.32), "#bfdbfe")
        if (v.role === "loco" && v.kind === "electric") {
          const x = strip(v.lat, v.lon, v.heading, -1.6, 1.6, v.width_m * 0.3) // the pantograph seen from above: an X
          for (const [i, j] of [[0, 2], [1, 3]]) L.polyline([x[i], x[j]], { color: "#0f172a", weight: 2, interactive: false }).addTo(layer)
        }
        if (v.role === "wagon" && v.kind === "dump") for (const a of [-v.length_m / 5, 0, v.length_m / 5]) mark(strip(v.lat, v.lon, v.heading, a - 0.18, a + 0.18, v.width_m * 0.42), "#fde68a", 0.75)
        if (v.role === "wagon" && v.kind === "tank") mark(strip(v.lat, v.lon, v.heading, -1, 1, v.width_m * 0.28), "#cffafe", 0.8)
        if (zoom >= 19 && !v.hidden && v.label) poly.bindTooltip(v.label, { permanent: true, direction: "center", className: "veh-label" })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, trains, zoom, view, selectedId])

  // 4) the selection: pictogram popup, or the whole train / the chosen car when it rides in a formation
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    if (!selectedId) { map.closePopup(); return }
    const point = looseRef.current.find((p) => p.asset_id === selectedId)
    if (point) { showPopup(point.lat, point.lon, popupHtml(point)); return }
    for (const t of trainsRef.current) {
      const v = t.vehicles.find((x) => x.asset_id === selectedId)
      if (!v && t.loco_asset_id !== selectedId) continue
      if (v && v.role === "wagon") {
        map.setView([v.lat, v.lon], Math.max(map.getZoom(), 18))
        libRef.current?.popup({ offset: [0, -4], maxWidth: 340 }).setLatLng([v.lat, v.lon]).setContent(trainPopupHtml(t, v)).openOn(map)
      } else {
        map.fitBounds(trainBounds(t), { maxZoom: 18, padding: [60, 60] })
        libRef.current?.popup({ offset: [0, -4], maxWidth: 340 }).setLatLng([t.lat, t.lon]).setContent(trainPopupHtml(t)).openOn(map)
      }
      return
    }
    // re-open only when the selection changes, not on every refresh
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, selectedId])

  return (
    <>
      <style>{STYLE}</style>
      <div ref={containerRef} className="relative z-0 h-full min-h-[420px] w-full rounded-xl" aria-label="Карта основных средств (OpenStreetMap)" data-zoom={zoom} data-testid="osm-map" />
    </>
  )
}
