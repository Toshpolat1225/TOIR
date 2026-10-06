"use client"

import { createContext, useContext, useEffect, useState, ReactNode } from "react"
import { supabase } from "./supabase"

export type UserRole = "admin" | "operator" | "master"

export type Profile = {
  id: string
  full_name: string
  email: string
  role: UserRole
  section: string
}

type CurrentUser = Profile

type AuthContextType = {
  user: CurrentUser | null
  profile: CurrentUser | null // Merging profile into user for simplicity
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: string | null; user: CurrentUser | null }>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  profile: null,
  loading: true,
  signIn: async () => ({ error: null, user: null }),
  signOut: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user,    setUser]    = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    const loadUser = async (userId: string) => {
      const { data, error } = await supabase
        .from("profiles")
        .select("id, full_name, email, role, section")
        .eq("id", userId)
        .maybeSingle()

      if (error) throw error
      if (!data) throw new Error("User profile was not found.")
      return data as Profile
    }

    const restoreSession = async () => {
      try {
        const { data, error } = await supabase.auth.getSession()
        if (error) throw error

        if (data.session) {
          const currentUser = await loadUser(data.session.user.id)
          if (mounted) setUser(currentUser)
        }
      } catch (error) {
        console.error("Failed to restore Supabase session.", error)
        if (mounted) setUser(null)
      } finally {
        if (mounted) setLoading(false)
      }
    }

    void restoreSession()
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        if (mounted) {
          setUser(null)
          setLoading(false)
        }
        return
      }

      setTimeout(() => {
        void loadUser(session.user.id)
          .then(currentUser => {
            if (mounted) setUser(currentUser)
          })
          .catch(error => {
            console.error("Failed to load Supabase user profile.", error)
            if (mounted) setUser(null)
          })
          .finally(() => {
            if (mounted) setLoading(false)
          })
      }, 0)
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
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

      const { error } = await supabase.auth.setSession({
        access_token: result.access_token,
        refresh_token: result.refresh_token,
      })
      if (error) throw error

      const loggedInUser = result.user as CurrentUser
      setUser(loggedInUser)
      return { error: null, user: loggedInUser }
    } catch (error) {
      return { error: error instanceof Error ? error.message : "Login failed", user: null }
    }
  }

  const signOut = async () => {
    try {
      const { error } = await supabase.auth.signOut()
      if (error) throw error
    } catch (error) {
      console.error("Supabase sign-out failed.", error)
    } finally {
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
