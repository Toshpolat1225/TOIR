"use client"

import { useEffect } from "react"
import { useTheme } from "next-themes"

export function ThemeClassSync() {
  const { resolvedTheme } = useTheme()

  useEffect(() => {
    document.documentElement.classList.toggle(
      "dark",
      resolvedTheme === "dark" || resolvedTheme === "graphite",
    )
  }, [resolvedTheme])

  return null
}
