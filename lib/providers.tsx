"use client"

import { AuthProvider } from "./auth-context"
import { ReactNode } from "react"
import { ThemeProvider } from "next-themes"
import { ThemeClassSync } from "@/components/theme-class-sync"
import { LocaleProvider, LocaleSwitcher, type Locale } from "@/lib/i18n"

export function Providers({ children, initialLocale }: { children: ReactNode; initialLocale: Locale }) {
  return (
    <LocaleProvider initialLocale={initialLocale}>
      <ThemeProvider
        attribute="data-theme"
        defaultTheme="light"
        enableSystem={false}
        themes={["light", "dark", "ocean", "emerald", "violet", "graphite"]}
        storageKey="toir-theme"
      >
        <ThemeClassSync />
        <AuthProvider>
          {children}
          <LocaleSwitcher />
        </AuthProvider>
      </ThemeProvider>
    </LocaleProvider>
  )
}
