"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Eye, EyeOff, AlertCircle, Wrench } from "@/components/ui/icons"
import { useAuth } from "@/lib/auth-context"
import { ThemeSwitcher } from "@/components/theme-switcher"

export default function LoginPage() {
  const router       = useRouter()
  const { signIn, user, loading } = useAuth()

  const [email,    setEmail]    = useState("")
  const [password, setPassword] = useState("")
  const [showPwd,  setShowPwd]  = useState(false)
  const [busy,     setBusy]     = useState(false)
  const [error,    setError]    = useState("")

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard")
  }, [loading, user, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError("")
    const { error } = await signIn(email, password)
    if (error) {
      setError(error)
      setBusy(false)
    } else {
      router.push("/dashboard")
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-100 p-4 dark:bg-gray-950">
      <div className="absolute right-4 top-4 z-10 sm:right-6 sm:top-6">
        <ThemeSwitcher />
      </div>
      <div aria-hidden="true" className="pointer-events-none absolute -right-40 -top-40 h-[32rem] w-[32rem] rounded-full bg-blue-200/50 blur-3xl dark:bg-blue-950/40" />
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-48 -left-40 h-[32rem] w-[32rem] rounded-full bg-slate-300/70 blur-3xl dark:bg-slate-900/70" />

      <div className="relative w-full max-w-md">
        <div className="mb-7 flex items-center justify-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-700 text-white shadow-sm">
            <Wrench className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wide text-slate-950 dark:text-white">STTB</h1>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-gray-400">Система технического обслуживания</p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-900/5 sm:p-8 dark:border-gray-800 dark:bg-gray-900 dark:shadow-black/20">
          <div className="mb-6">
            <h2 className="text-xl font-semibold tracking-tight text-slate-950 dark:text-white">Вход в систему</h2>
            <p className="mt-1.5 text-sm text-slate-500 dark:text-gray-400">Введите данные учетной записи, чтобы продолжить.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">

            <div>
              <label htmlFor="login-email" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-gray-300">Email</label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="user@company.uz"
                required
                autoComplete="email"
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 dark:border-gray-700 dark:bg-gray-950 dark:text-white dark:placeholder:text-gray-600"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-gray-300">Пароль</label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPwd ? "text" : "password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Введите пароль"
                  required
                  autoComplete="current-password"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 pr-11 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 dark:border-gray-700 dark:bg-gray-950 dark:text-white dark:placeholder:text-gray-600"
                />
                <button
                  type="button"
                  aria-label={showPwd ? "Скрыть пароль" : "Показать пароль"}
                  aria-pressed={showPwd}
                  onClick={() => setShowPwd(v => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white"
                >
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div role="alert" className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 focus-visible:outline-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Вход...
                </>
              ) : "Войти"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-xs text-slate-500 dark:text-gray-400">
          Обратитесь к администратору системы для получения доступа.
        </p>
      </div>
    </div>
  )
}
