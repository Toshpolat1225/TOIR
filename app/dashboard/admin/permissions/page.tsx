"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ShieldCheck, Save, RotateCcw } from "@/components/ui/icons"
import { api, type PermissionEntry, type RolePermissionMatrix } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"

const roles: Exclude<RolePermissionMatrix["role"], "admin">[] = ["operator", "master", "management"]
const roleLabel: Record<RolePermissionMatrix["role"], string> = { admin: "Администратор (защищённая роль)", operator: "Оператор", master: "Мастер", management: "Руководство" }
const actionLabel: Record<string, string> = { view: "Просмотр", create: "Создание", update: "Изменение", delete: "Удаление", export: "Экспорт", approve: "Подтверждение", manage_users: "Управление пользователями", manage_permissions: "Управление правами", manage_reference_data: "Управление справочниками" }

export default function PermissionsPage() {
  const { profile } = useAuth()
  const [role, setRole] = useState<RolePermissionMatrix["role"]>("operator")
  const [items, setItems] = useState<PermissionEntry[]>([])
  const [saved, setSaved] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const isAdmin = profile?.role === "admin"
  const dirty = useMemo(() => items.some((item) => item.granted !== saved.includes(item.code)), [items, saved])

  const load = useCallback(async (selected: RolePermissionMatrix["role"]) => {
    setLoading(true); setError("")
    try {
      const result = await api.permissions.getRole(selected)
      setItems(result.permissions)
      setSaved(result.permissions.filter((item) => item.granted).map((item) => item.code))
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось загрузить права") }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { if (isAdmin) void load(role) }, [isAdmin, role, load])
  const grouped = useMemo(() => Object.entries(items.reduce<Record<string, PermissionEntry[]>>((acc, item) => { (acc[item.module] ??= []).push(item); return acc }, {})), [items])

  if (!isAdmin) return <div className="p-8 text-sm text-red-600">Недостаточно прав для просмотра этой страницы.</div>

  const save = async () => {
    if (role === "admin") return
    setBusy(true); setError("")
    try {
      const result = await api.permissions.setRole(role, items.filter((item) => item.granted).map((item) => item.code))
      setItems(result.permissions); setSaved(result.permissions.filter((item) => item.granted).map((item) => item.code))
      setNotice(result.changed.length ? `Сохранено. Изменены права: ${result.changed.join(", ")}` : "Изменений нет.")
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось сохранить права") }
    finally { setBusy(false) }
  }

  return <section className="mx-auto max-w-5xl p-4 md:p-8">
    <div className="mb-6 flex items-center gap-3"><ShieldCheck className="h-6 w-6 text-blue-600"/><div><h1 className="text-xl font-semibold text-gray-900 dark:text-white">Права доступа по ролям</h1><p className="text-sm text-gray-500 dark:text-gray-400">Изменения вступают в силу при следующем API-запросе.</p></div></div>
    <label className="mb-5 block max-w-sm text-sm font-medium">Роль<select value={role} onChange={(e) => setRole(e.target.value as RolePermissionMatrix["role"])} className="mt-1 block w-full rounded-lg border border-gray-300 bg-white p-2.5 dark:border-gray-700 dark:bg-gray-900">{roles.map((item) => <option key={item} value={item}>{roleLabel[item]}</option>)}</select></label>
    {error && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
    {notice && <p role="status" className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-800 dark:bg-green-950 dark:text-green-300">{notice}</p>}
    {loading ? <p className="py-8 text-sm text-gray-500">Загрузка…</p> : <div className="space-y-4">{grouped.map(([module, permissions]) => <div key={module} className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"><h2 className="mb-3 font-semibold capitalize text-gray-900 dark:text-white">{permissions[0]?.label}</h2><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{permissions.map((permission) => <label key={permission.code} className="flex items-center gap-2 rounded-lg p-2 text-sm text-gray-700 hover:bg-gray-50 focus-within:ring-2 focus-within:ring-blue-500 dark:text-gray-200 dark:hover:bg-gray-800"><input type="checkbox" checked={permission.granted} onChange={(event) => setItems((current) => current.map((item) => item.code === permission.code ? { ...item, granted: event.target.checked } : item))}/>{actionLabel[permission.action] ?? permission.action}</label>)}</div></div>)}</div>}
    {!loading && <div className="sticky bottom-0 mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white/95 p-4 shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-900/95"><div className="max-h-28 overflow-auto text-sm text-gray-600 dark:text-gray-300">{dirty ? <><p className="font-medium">Сводка изменений перед сохранением:</p><ul className="mt-1 list-inside list-disc">{items.filter((item) => item.granted !== saved.includes(item.code)).map((item) => <li key={item.code}>{item.label}: {actionLabel[item.action] ?? item.action} — {item.granted ? "разрешить" : "запретить"}</li>)}</ul></> : "Изменений нет"}</div><div className="flex gap-2"><button type="button" disabled={!dirty || busy} onClick={() => setItems((current) => current.map((item) => ({ ...item, granted: saved.includes(item.code) })))} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm disabled:opacity-50"><RotateCcw className="h-4 w-4"/>Отменить</button><button type="button" disabled={!dirty || busy} onClick={() => { if (window.confirm(`Подтвердить изменение ${items.filter((item) => item.granted !== saved.includes(item.code)).length} прав?`)) void save() }} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50"><Save className="h-4 w-4"/>{busy ? "Сохранение…" : "Сохранить"}</button></div></div>}
  </section>
}
