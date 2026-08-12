"use client"

import { createContext, useContext, useEffect, useState, ReactNode } from "react"
import { api, CurrentUser } from "./api"

export type UserRole = "admin" | "operator" | "master"

export type Profile = {
  id: string
  full_name: string
  email: string
  role: UserRole
  section: string
}

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
    const restoreSession = async () => {
      try {
        // Attempt to get a new access token using the refresh token cookie
        const { user: refreshedUser } = await api.auth.refresh();
        if (refreshedUser) {
          setUser(refreshedUser);
        }
      } catch (error) {
        // If refresh fails, it's okay, the user is not logged in.
        console.log("No active session to restore.");
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    restoreSession();
  }, [])

  const signIn = async (email: string, password: string) => {
    try {
      const { user: loggedInUser } = await api.auth.login({ email, password });
      setUser(loggedInUser);
      return { error: null, user: loggedInUser };
    } catch (error) {
      return { error: error instanceof Error ? error.message : "Login failed", user: null };
    }
  }

  const signOut = async () => {
    try {
      await api.auth.logout();
    } catch (error) {
      console.error("Logout failed, clearing client-side state anyway.", error);
    } finally {
      setUser(null);
    }
  }

  return (
    <AuthContext.Provider value={{ user, profile: user, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
