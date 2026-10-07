"use client"

import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { api, type CurrentUser } from "@/lib/api"

export type UserRole = CurrentUser["role"]
export type Profile = CurrentUser

type AuthContextType = {
  user: CurrentUser | null
  profile: CurrentUser | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: string | null; user: CurrentUser | null }>
  signOut: () => Promise<void>
}

const SESSION_HINT_COOKIE = "toir_session_hint"
const SESSION_HINT_MAX_AGE = 7 * 24 * 60 * 60

function setSessionHint(): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : ""
  document.cookie = `${SESSION_HINT_COOKIE}=1; Path=/dashboard; Max-Age=${SESSION_HINT_MAX_AGE}; SameSite=Lax${secure}`
}

function clearSessionHint(): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : ""
  document.cookie = `${SESSION_HINT_COOKIE}=; Path=/dashboard; Max-Age=0; SameSite=Lax${secure}`
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  profile: null,
  loading: true,
  signIn: async () => ({ error: null, user: null }),
  signOut: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true

    const restoreSession = async () => {
      try {
        await api.auth.refresh()
        const currentUser = await api.auth.me()
        if (active) {
          setUser(currentUser)
          setSessionHint()
        }
      } catch {
        if (active) {
          setUser(null)
          clearSessionHint()
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    void restoreSession()
    return () => {
      active = false
    }
  }, [])

  const signIn = async (email: string, password: string) => {
    try {
      const result = await api.auth.login({ email, password })
      setUser(result.user)
      setSessionHint()
      return { error: null, user: result.user }
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : "Login failed",
        user: null,
      }
    }
  }

  const signOut = async () => {
    try {
      await api.auth.logout()
    } finally {
      clearSessionHint()
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider value={{ user, profile: user, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
