"use client"

import { useState, useEffect, useCallback } from "react"
import { Users, Plus, X, Save, Pencil, ShieldCheck, Shield, HardHat, Eye, EyeOff } from "@/components/ui/icons"
import { api } from "@/lib/api"
import { useAuth, type Profile, type UserRole } from "@/lib/auth-context"
import { useSections, type SectionData } from "@/lib/use-sections"
import { useRealtime } from "@/lib/use-realtime"
import { Button } from "@/components/ui/button"

const ROLE_CFG: Record<"admin" | "operator" | "master" | "management", { label: string; cls: string; Icon: React.ElementType }> = {
  admin:      { label: "Администратор", cls: "bg-purple-100 text-purple-700 dark:bg-purple-900/60 dark:text-purple-300", Icon: ShieldCheck },
  operator:   { label: "Оператор",      cls: "bg-blue-100   text-blue-700   dark:bg-blue-900/60   dark:text-blue-300",   Icon: Shield      },
  master:     { label: "Мастер",        cls: "bg-amber-100  text-amber-700  dark:bg-amber-900/60  dark:text-amber-300",  Icon: HardHat     },
  management: { label: "Руководство",  cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300", Icon: ShieldCheck },
}

/* ─── Модал создания пользователя ─── */
function CreateUserModal({ onClose, onCreated, sections }: { onClose: () => void; onCreated: () => void; sections: SectionData[] }) {
  const [fullName, setFullName] = useState("")
  const [email,    setEmail]    = useState("")
  const [password, setPassword] = useState("")
  const [showPwd,  setShowPwd]  = useState(false)
  const [role,     setRole]     = useState<UserRole>("master")
  const [section,  setSection]  = useState("")
  const [busy,     setBusy]     = useState(false)
  const [error,    setError]    = useState("")

  const handleCreate = async () => {
    if (!fullName.trim() || !email.trim() || password.length < 6) {
      setError("Заполните все поля. Пароль — минимум 6 символов.")
      return
    }
    if (role === "master" && !section) {
      setError("Для мастера необходимо выбрать участок.")
      return
    }
    setBusy(true)
    setError("")
    try {
      await api.users.create({
        email: email.trim(),
        full_name: fullName.trim(),
        password,
        role,
        section_id: section || null,
      })
      onCreated()
      onClose()
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось создать пользователя.")
      setBusy(false)
    }
  }

  const inp = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const sel = "w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700">

        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-base font-bold text-gray-900 dark:text-white">Создать пользователя</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"><X className="w-4 h-4"/></button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">ФИО</label>
            <input value={fullName} onChange={e=>setFullName(e.target.value)} placeholder="Иванов Иван Иванович" className={inp}/>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Email</label>
            <input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="user@company.uz" className={inp}/>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Пароль</label>
            <div className="relative">
              <input type={showPwd?"text":"password"} value={password} onChange={e=>setPassword(e.target.value)} placeholder="Минимум 6 символов" className={inp + " pr-10"}/>
              <button type="button" onClick={()=>setShowPwd(v=>!v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showPwd ? <EyeOff className="w-4 h-4"/> : <Eye className="w-4 h-4"/>}
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Роль</label>
              <select value={role} onChange={e=>setRole(e.target.value as UserRole)} className={sel}>
                <option value="admin">Администратор</option>
                <option value="operator">Оператор</option>
                <option value="master">Мастер</option>
                <option value="management">Руководство</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Участок</label>
              <select value={section} onChange={e=>setSection(e.target.value)} className={sel}>
                <option value="">— не указан —</option>
                {sections.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          </div>

          {error && <p className="text-red-500 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-800">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={handleCreate} disabled={busy} className="gap-2 bg-blue-600 hover:bg-blue-700">
            {busy ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/> : <Plus className="w-4 h-4"/>}
            Создать
          </Button>
        </div>
      </div>
    </div>
  )
}

/* ─── Модал редактирования пользователя ─── */
function EditUserModal({ profile, onClose, onSaved, sections }: {
  profile: Profile
  onClose: () => void
  onSaved: () => void
  sections: SectionData[]
}) {
  const [fullName, setFullName] = useState(profile.full_name ?? "")
  const [role,     setRole]     = useState<UserRole>(profile.role)
  const [section,  setSection]  = useState(profile.section_id ?? "")
  const [isActive, setIsActive] = useState(profile.is_active)
  const [newPassword, setNewPassword] = useState("")
  const [busy,     setBusy]     = useState(false)
  const [resetBusy, setResetBusy] = useState(false)
  const [error,    setError]    = useState("")
  const [resetSuccess, setResetSuccess] = useState(false)

  const handleSave = async () => {
    if (role === "master" && !section) {
      setError("Для мастера необходимо выбрать участок.")
      return
    }
    if (isActive !== profile.is_active && !window.confirm(`Подтвердите ${isActive ? "активацию" : "блокировку"} пользователя «${profile.full_name}».`)) return
    setBusy(true)
    setError("")
    try {
      await api.users.update(profile.id, {
        full_name: fullName.trim(),
        role,
        section_id: section || null,
        is_active: isActive,
      })
      onSaved()
      onClose()
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось обновить пользователя.")
      setBusy(false)
    }
  }

  const handlePasswordReset = async () => {
    if (newPassword.length < 6) {
      setError("Пароль должен содержать не менее 6 символов.")
      return
    }
    setResetBusy(true)
    setError("")
    setResetSuccess(false)
    try {
      await api.users.resetPassword(profile.id, newPassword)
      setNewPassword("")
      setResetSuccess(true)
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось сбросить пароль.")
    } finally {
      setResetBusy(false)
    }
  }

  const inp = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const sel = "w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700">

        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-base font-bold text-gray-900 dark:text-white">Редактировать пользователя</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"><X className="w-4 h-4"/></button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">ФИО</label>
            <input value={fullName} onChange={e=>setFullName(e.target.value)} className={inp}/>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Email</label>
            <input value={profile.email} disabled className={inp + " opacity-50 cursor-not-allowed"}/>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Роль</label>
              <select value={role} onChange={e=>setRole(e.target.value as UserRole)} className={sel}>
                <option value="admin">Администратор</option>
                <option value="operator">Оператор</option>
                <option value="master">Мастер</option>
                <option value="management">Руководство</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Участок</label>
              <select value={section} onChange={e=>setSection(e.target.value)} className={sel}>
                <option value="">— не указан —</option>
                {sections.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={isActive}
              onChange={e=>setIsActive(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            Активная учетная запись
          </label>
          <div className="border-t border-gray-200 dark:border-gray-800 pt-4">
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Сбросить пароль</label>
            <div className="flex gap-2">
              <input
                type="password"
                value={newPassword}
                onChange={e=>setNewPassword(e.target.value)}
                placeholder="Новый пароль (минимум 6 символов)"
                className={inp}
                autoComplete="new-password"
              />
              <Button variant="outline" onClick={handlePasswordReset} disabled={resetBusy || !newPassword}>
                {resetBusy ? "..." : "Сбросить"}
              </Button>
            </div>
          </div>
          {resetSuccess && <p role="status" className="text-emerald-700 text-sm dark:text-emerald-400">Пароль успешно обновлён.</p>}
          {error && <p className="text-red-500 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-800">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={handleSave} disabled={busy} className="gap-2 bg-blue-600 hover:bg-blue-700">
            {busy ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/> : <Save className="w-4 h-4"/>}
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  )
}

/* ─── ГЛАВНАЯ СТРАНИЦА ─── */
export default function AdminUsersPage() {
  const { profile: myProfile } = useAuth()
  const { sectionsData } = useSections()
  const [users,     setUsers]     = useState<Profile[]>([])
  const [loading,   setLoading]   = useState(true)
  const [loadError, setLoadError] = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]   = useState<Profile | null>(null)
  const [search,     setSearch]    = useState("")
  const [activeFilter, setActiveFilter] = useState("all")
  const [statusError, setStatusError] = useState("")

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setLoadError("")
    try {
      const response = await api.users.list({
        limit: 1000,
        offset: 0,
        sort_by: "created_at",
        sort_order: "asc",
      })
      setUsers(response.items)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Не удалось загрузить пользователей.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchUsers() }, [fetchUsers])
  useRealtime(
    useCallback(() => { void fetchUsers() }, [fetchUsers]),
    ["users"]
  )

  if (myProfile?.role !== "admin") {
    return (
      <div className="flex items-center justify-center h-96 text-gray-400 text-sm">
        Доступ разрешён только администраторам
      </div>
    )
  }

  const filtered = users.filter(u => {
    const q = search.toLowerCase()
    const fullName = (u.full_name ?? "").toLowerCase()
    const section = (sectionsData.find(item => item.id === u.section_id)?.name ?? "").toLowerCase()
    const matchesSearch = !q || fullName.includes(q) || u.email.toLowerCase().includes(q) || section.includes(q)
    return matchesSearch && (activeFilter === "all" || String(u.is_active) === activeFilter)
  })

  const changeActive = async (user: Profile) => {
    const next = !user.is_active
    if (!window.confirm(`Вы уверены, что хотите ${next ? "активировать" : "заблокировать"} пользователя «${user.full_name}»?`)) return
    setStatusError("")
    try {
      await api.users.update(user.id, { is_active: next })
      await fetchUsers()
    } catch (error) {
      setStatusError(error instanceof Error ? error.message : "Не удалось изменить статус пользователя.")
    }
  }

  const counts = {
    total:    users.length,
    admin:    users.filter(u => u.role === "admin").length,
    operator: users.filter(u => u.role === "operator").length,
    master:   users.filter(u => u.role === "master").length,
  }

  return (
    <div className="p-8 space-y-6">
      {showCreate && <CreateUserModal onClose={()=>setShowCreate(false)} onCreated={fetchUsers} sections={sectionsData}/>}
      {editing    && <EditUserModal   profile={editing} onClose={()=>setEditing(null)} onSaved={fetchUsers} sections={sectionsData}/>}

      {/* Заголовок */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Пользователи</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Управление доступом и ролями</p>
        </div>
        <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={()=>setShowCreate(true)}>
          <Plus className="w-4 h-4"/> Создать пользователя
        </Button>
      </div>
      {loadError && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {loadError}
          <Button variant="outline" onClick={fetchUsers} className="ml-3">Повторить</Button>
        </div>
      )}
      {statusError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">{statusError}</div>}

      {/* KPI карточки */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Всего",           value: counts.total,    cls: "border-gray-200 dark:border-gray-700", Icon: Users       },
          { label: "Администраторы",  value: counts.admin,    cls: "border-purple-200 dark:border-purple-800", Icon: ShieldCheck },
          { label: "Операторы",       value: counts.operator, cls: "border-blue-200   dark:border-blue-800",   Icon: Shield      },
          { label: "Мастера",         value: counts.master,   cls: "border-amber-200  dark:border-amber-800",  Icon: HardHat     },
        ].map(card => (
          <div key={card.label} className={`bg-white dark:bg-gray-900 rounded-xl border ${card.cls} p-4`}>
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500 dark:text-gray-400">{card.label}</p>
              <card.Icon className="w-4 h-4 text-gray-400"/>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{card.value}</p>
          </div>
        ))}
      </div>

      {/* Поиск */}
      <div className="flex items-center gap-3 flex-wrap">
        <input
          value={search}
          onChange={e=>setSearch(e.target.value)}
          placeholder="Поиск по имени, email, участку..."
          className="flex-1 max-w-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select aria-label="Фильтр по статусу" value={activeFilter} onChange={e=>setActiveFilter(e.target.value)} className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
          <option value="all">Все статусы</option><option value="true">Активные</option><option value="false">Неактивные</option>
        </select>
        {search && <button onClick={()=>setSearch("")} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4"/></button>}
      </div>

      {/* Таблица */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-gray-400 text-sm gap-3">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
            Загрузка...
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">ФИО</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Email</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Роль</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Участок</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Статус</th>
                <th className="text-right px-4 py-3 font-semibold text-gray-600 dark:text-gray-300">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center text-gray-400 py-10">Нет пользователей</td>
                </tr>
              ) : filtered.map(u => {
                const cfg = ROLE_CFG[u.role]
                const isMe = u.id === myProfile?.id
                return (
                  <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center text-blue-700 dark:text-blue-300 font-semibold text-sm flex-shrink-0">
                          {(u.full_name || u.email).charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900 dark:text-white">
                            {u.full_name || "—"}
                            {isMe && <span className="ml-1.5 text-xs text-blue-500">(вы)</span>}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{u.email || "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.cls}`}>
                        <cfg.Icon className="w-3 h-3"/>
                        {cfg.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {sectionsData.find(section => section.id === u.section_id)?.name || "—"}
                    </td>
                    <td className="px-4 py-3"><span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${u.is_active ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300" : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"}`}>{u.is_active ? "Активен" : "Неактивен"}</span></td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={()=>setEditing(u)}
                        className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors"
                      >
                        <Pencil className="w-3.5 h-3.5"/> Изменить
                      </button>
                      {!isMe && <button onClick={()=>void changeActive(u)} className="ml-2 text-xs font-medium text-red-600 hover:underline dark:text-red-400">{u.is_active ? "Заблокировать" : "Активировать"}</button>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-600">
        Управление учетными записями выполняется через локальный API.
      </p>
    </div>
  )
}
