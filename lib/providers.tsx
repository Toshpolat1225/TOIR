"use client"

import { AuthProvider } from "./auth-context"
import { ReactNode } from "react"

export function Providers({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}
