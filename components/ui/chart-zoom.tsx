"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

/** Zoom / pan over a long time series: `view` is the visible slice, the buttons change its window. */
export function useChartZoom<T>(data: T[], minPoints = 6) {
  const total = data.length
  const [win, setWin] = useState<{ start: number; len: number } | null>(null)

  useEffect(() => setWin(null), [total])

  const len = win ? Math.min(win.len, total) : total
  const start = win ? Math.min(Math.max(0, win.start), Math.max(0, total - len)) : 0

  const set = useCallback((s: number, l: number) => {
    const nl = Math.max(Math.min(minPoints, total), Math.min(total, Math.round(l)))
    setWin(nl >= total ? null : { start: Math.min(Math.max(0, Math.round(s)), total - nl), len: nl })
  }, [minPoints, total])

  const zoomIn = useCallback(() => set(start + len / 4, len / 2), [set, start, len])
  const zoomOut = useCallback(() => set(start - len / 2, len * 2), [set, start, len])
  const pan = useCallback((dir: -1 | 1) => set(start + dir * Math.max(1, Math.round(len / 3)), len), [set, start, len])
  const reset = useCallback(() => setWin(null), [])
  const view = useMemo(() => data.slice(start, start + len), [data, start, len])

  return {
    view,
    isZoomed: len < total,
    canZoomIn: len > Math.min(minPoints, total),
    canPanLeft: start > 0,
    canPanRight: start + len < total,
    zoomIn, zoomOut, pan, reset,
  }
}

type Zoom = ReturnType<typeof useChartZoom>

export function ChartZoomControls({ zoom }: { zoom: Zoom }) {
  const btn = "h-7 min-w-7 px-2 rounded-md border border-gray-200 dark:border-gray-700 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
  return (
    <div className="inline-flex items-center gap-1" role="group" aria-label="Масштаб графика">
      <button type="button" className={btn} onClick={() => zoom.pan(-1)} disabled={!zoom.canPanLeft} title="Сдвинуть назад" aria-label="Сдвинуть назад">←</button>
      <button type="button" className={btn} onClick={() => zoom.pan(1)} disabled={!zoom.canPanRight} title="Сдвинуть вперёд" aria-label="Сдвинуть вперёд">→</button>
      <button type="button" className={btn} onClick={zoom.zoomOut} disabled={!zoom.isZoomed} title="Отдалить" aria-label="Отдалить">−</button>
      <button type="button" className={btn} onClick={zoom.zoomIn} disabled={!zoom.canZoomIn} title="Приблизить" aria-label="Приблизить">+</button>
      <button type="button" className={btn} onClick={zoom.reset} disabled={!zoom.isZoomed} title="Весь период" aria-label="Весь период">⟲</button>
    </div>
  )
}
