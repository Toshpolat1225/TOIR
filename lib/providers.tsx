"use client"

import { AuthProvider } from "./auth-context"
import { ReactNode } from "react"
import { ThemeProvider } from "next-themes"
import { ThemeClassSync } from "@/components/theme-class-sync"

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider
      attribute="data-theme"
      defaultTheme="light"
      enableSystem={false}
      themes={["light", "dark", "ocean", "emerald", "violet", "graphite"]}
      storageKey="toir-theme"
    >
      <ThemeClassSync />
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  )
}
