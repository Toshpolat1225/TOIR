"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Eye, EyeOff, AlertCircle } from "lucide-react"
import { useAuth } from "@/lib/auth-context"

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
      setError("Неверный email или пароль")
      setBusy(false)
    } else {
      router.push("/dashboard")
    }
  }

  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 overflow-hidden">

      {/* ── Фоновая картинка ── */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/bg-railway.png"
        alt=""
        className="absolute inset-0 w-full h-full object-cover object-center"
      />

      {/* Затемняющий overlay для читаемости формы */}
      <div className="absolute inset-0 bg-gradient-to-br from-black/60 via-black/40 to-black/65 pointer-events-none" />
      {/* Дополнительный blur-размытый слой по краям */}
      <div className="absolute inset-0 bg-gradient-to-r from-black/30 via-transparent to-black/30 pointer-events-none" />

      <div className="relative w-full max-w-md">

        {/* Заголовок */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-black text-white tracking-widest drop-shadow-lg">STTB</h1>
          <p className="text-slate-300 text-sm mt-2">Система управления техническим обслуживанием</p>
        </div>

        {/* Карточка */}
        <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-lg font-semibold text-white mb-6">Вход в систему</h2>

          <form onSubmit={handleSubmit} className="space-y-4">

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="user@company.uz"
                required
                autoComplete="email"
                className="w-full px-4 py-2.5 rounded-xl bg-white/10 border border-white/20 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Пароль</label>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  className="w-full px-4 py-2.5 pr-11 rounded-xl bg-white/10 border border-white/20 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
                  tabIndex={-1}
                >
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white font-semibold rounded-xl transition-colors text-sm disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-2"
            >
              {busy ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Вход...
                </>
              ) : "Войти"}
            </button>
          </form>
        </div>

        <p className="text-center text-slate-500 text-xs mt-5">
          Обратитесь к администратору системы для получения доступа
        </p>
      </div>
    </div>
  )
}
