"use client"

import { createContext, useContext, useEffect, useState, ReactNode } from "react"
import { User } from "@supabase/supabase-js"
import { supabase } from "./supabase"

export type UserRole = "admin" | "operator" | "master"

export type Profile = {
  id: string
  full_name: string
  email: string
  role: UserRole
  section: string
}

type AuthContextType = {
  user: User | null
  profile: Profile | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: string | null }>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  profile: null,
  loading: true,
  signIn: async () => ({ error: null }),
  signOut: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user,    setUser]    = useState<User | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  async function loadProfile(uid: string) {
    const { data } = await supabase
      .from("profiles")
      .select("*")
      .eq("id", uid)
      .single()
    setProfile((data as Profile) ?? null)
  }

  useEffect(() => {
    let cancelled = false
    const timeoutId = setTimeout(() => {
      if (cancelled) return
      setLoading((prev) => {
        if (prev) return false
        return prev
      })
    }, 5000)

    supabase.auth.getSession().then(async ({ data: { session }, error }) => {
      if (cancelled) return
      if (error) {
        console.warn("Session error:", error.message)
        await supabase.auth.signOut()
        setUser(null)
        setProfile(null)
        setLoading(false)
        return
      }
      setUser(session?.user ?? null)
      if (session?.user) {
        await loadProfile(session.user.id)
      }
      setLoading(false)
    }).catch(async (err) => {
      if (cancelled) return
      console.warn("Auth error:", err)
      setUser(null)
      setProfile(null)
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        // Обработка ошибки токена
        if (event === "TOKEN_REFRESHED" && !session) {
          console.warn("Token refresh failed, signing out")
          await supabase.auth.signOut()
          setUser(null)
          setProfile(null)
          setLoading(false)
          return
        }
        
        if (event === "SIGNED_OUT") {
          setUser(null)
          setProfile(null)
          setLoading(false)
          return
        }

        setUser(session?.user ?? null)
        if (session?.user) {
          await loadProfile(session.user.id)
        } else {
          setProfile(null)
        }
        setLoading(false)
      }
    )

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
      subscription.unsubscribe()
    }
  }, [])

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error?.message ?? null }
  }

  const signOut = async () => {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider value={{ user, profile, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
