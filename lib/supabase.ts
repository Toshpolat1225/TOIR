import { createClient } from "@supabase/supabase-js"

const url  = process.env.NEXT_PUBLIC_SUPABASE_URL!
const key  = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

// Кастомный lock без Web Locks API — избегаем таймаута "Navigator LockManager lock ... timed out".
// В одной вкладке блокировка не нужна; при нескольких вкладках возможны редкие гонки при обновлении сессии.
const noopLock = <R>(_name: string, _acquireTimeout: number, fn: () => Promise<R>): Promise<R> => fn()

export const supabase = createClient(url, key, {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true,
    lock: noopLock,
  },
})
