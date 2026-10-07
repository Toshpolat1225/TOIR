"use client"

import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

export type UserRole = "admin" | "operator" | "master" | "management"

export type Profile = {
  id: string
  full_name: string | null
  email: string
  role: UserRole
  section?: string | null
  is_active?: boolean
}

type CurrentUser = Profile

type AuthContextType = {
  user: CurrentUser | null
  profile: CurrentUser | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: string | null; user: CurrentUser | null }>
  signOut: () => Promise<void>
}

const AUTH_TOKEN_KEY = "toir_access_token"
const AUTH_REFRESH_KEY = "toir_refresh_token"
const AUTH_USER_KEY = "toir_user"

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
        const storedToken = localStorage.getItem(AUTH_TOKEN_KEY)

        if (!storedToken) {
          if (active) setUser(null)
          return
        }

        const response = await fetch("/api/v1/auth/me", {
          headers: { Authorization: `Bearer ${storedToken}` },
        })

        if (!response.ok) {
          throw new Error("Session expired")
        }

        const profile = (await response.json()) as CurrentUser
        if (active) {
          setUser(profile)
          localStorage.setItem(AUTH_USER_KEY, JSON.stringify(profile))
        }
      } catch (error) {
        console.warn("Session restore failed:", error)
        if (active) {
          setUser(null)
          localStorage.removeItem(AUTH_TOKEN_KEY)
        localStorage.removeItem(AUTH_REFRESH_KEY)
        localStorage.removeItem(AUTH_USER_KEY)
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
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || "Login failed")

      const loggedInUser = result.user as CurrentUser
      const token = result.access_token as string
      const refreshToken = result.refresh_token as string | undefined

      if (!loggedInUser || !token) {
        throw new Error("Authentication response was incomplete.")
      }

      localStorage.setItem(AUTH_TOKEN_KEY, token)
      if (refreshToken) localStorage.setItem(AUTH_REFRESH_KEY, refreshToken)
      localStorage.setItem(AUTH_USER_KEY, JSON.stringify(loggedInUser))
      setUser(loggedInUser)
      return { error: null, user: loggedInUser }
    } catch (error) {
      return { error: error instanceof Error ? error.message : "Login failed", user: null }
    }
  }

  const signOut = async () => {
    try {
      const refreshToken = localStorage.getItem(AUTH_REFRESH_KEY)
      if (refreshToken) {
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
      }
    } catch (error) {
      console.warn("Backend sign-out failed.", error)
    } finally {
      localStorage.removeItem(AUTH_TOKEN_KEY)
      localStorage.removeItem(AUTH_REFRESH_KEY)
      localStorage.removeItem(AUTH_USER_KEY)
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
