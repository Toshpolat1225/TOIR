"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import {
  Wrench, ClipboardList, LayoutDashboard,
  ChevronRight, Package, Landmark, LogOut, Users, FileText, ChevronDown, FolderOpen,
  BarChart3, } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { SectionViewProvider, useSectionView } from "@/lib/section-view-context"
import { useSections } from "@/lib/use-sections"

const ALL_NAV = [
  { href: "/dashboard",             label: "Дашборд",        icon: LayoutDashboard, roles: ["admin","operator"],         exact: true },
  { href: "/dashboard/analytics",   label: "Аналитика",      icon: BarChart3,       roles: ["admin","operator"]                    },
  { href: "/dashboard/os",          label: "Осн. средства",  icon: Landmark,        roles: ["admin","operator"]                    },
  { href: "/dashboard/maintenance", label: "ТО и ремонты",   icon: Wrench,          roles: ["admin","operator"]                    },
  { href: "/dashboard/work-orders", label: "Наряд-заказы",   icon: ClipboardList,   roles: ["admin","operator","master"]            },
  { href: "/dashboard/tmc",         label: "ТМЦ",            icon: Package,         roles: ["admin","operator"]                    },
  { href: "/dashboard/reports",     label: "Отчёты",        icon: FileText,       roles: ["admin","operator"]                    },
  { href: "/dashboard/directories", label: "Справочники",    icon: FolderOpen,      roles: ["admin","operator"]                    },
  { href: "/dashboard/admin/users",    label: "Пользователи", icon: Users,      roles: ["admin"] },
]

const ROLE_BADGE: Record<string, { label: string; cls: string }> = {
  admin:    { label: "Администратор", cls: "bg-purple-100 text-purple-700 dark:bg-purple-900/60 dark:text-purple-300" },
  operator: { label: "Оператор",      cls: "bg-blue-100   text-blue-700   dark:bg-blue-900/60   dark:text-blue-300"   },
  master:   { label: "Мастер",        cls: "bg-amber-100  text-amber-700  dark:bg-amber-900/60  dark:text-amber-300"  },
}

function UserBlockWithSection({
  profile,
  user,
  role,
  badge,
  onSignOut,
}: {
  profile: { full_name?: string; section?: string } | null
  user: { email?: string } | null
  role: string
  badge: { label: string; cls: string }
  onSignOut: () => void
}) {
  const isAdmin = role === "admin"
  const { viewSection, setViewSection } = useSectionView()
  const { sections, loading: sectionsLoading } = useSections()
  const [dropdownOpen, setDropdownOpen] = useState(false)

  return (
    <div className="px-3 py-4 border-t border-gray-200 dark:border-gray-800 flex-shrink-0">
      <div className="px-3 py-3 rounded-xl bg-gray-50 dark:bg-gray-800 mb-2">
        <p className="text-sm font-semibold text-gray-900 dark:text-white truncate leading-tight">
          {profile?.full_name || user?.email}
        </p>
        {isAdmin ? (
          <div className="mt-2 relative">
            <button
              type="button"
              onClick={() => setDropdownOpen((v) => !v)}
              className={cn(
                "w-full flex items-center justify-between gap-2 text-left text-xs font-medium rounded-lg px-2.5 py-1.5 border transition-colors",
                "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300",
                "hover:border-gray-300 dark:hover:border-gray-600"
              )}
            >
              <span className="truncate">
                {viewSection === null ? "Все участки" : viewSection}
              </span>
              <ChevronDown className={cn("w-3.5 h-3.5 flex-shrink-0 transition-transform", dropdownOpen && "rotate-180")} />
            </button>
            {dropdownOpen && (
              <>
                <div className="fixed inset-0 z-10" aria-hidden onClick={() => setDropdownOpen(false)} />
                <div className="absolute left-0 right-0 top-full mt-1 z-20 py-1 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 shadow-lg max-h-48 overflow-y-auto">
                  <button
                    type="button"
                    onClick={() => { setViewSection(null); setDropdownOpen(false) }}
                    className={cn(
                      "w-full text-left px-3 py-2 text-xs font-medium",
                      viewSection === null ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300" : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
                    )}
                  >
                    Все участки
                  </button>
                  {!sectionsLoading && sections.map((name) => (
                    <button
                      key={name}
                      type="button"
                      onClick={() => { setViewSection(name); setDropdownOpen(false) }}
                      className={cn(
                        "w-full text-left px-3 py-2 text-xs font-medium",
                        viewSection === name ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300" : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
                      )}
                    >
                      <span className="truncate">{name}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        ) : profile?.section ? (
          <div className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-100 dark:bg-gray-700/50 text-gray-700 dark:text-gray-300">
            <span className="truncate">{profile.section}</span>
          </div>
        ) : null}
        <span className={cn("inline-block text-xs px-2 py-0.5 rounded-full font-medium mt-2", badge.cls)}>
          {badge.label}
        </span>
      </div>

      <button
        onClick={onSignOut}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-950/50 hover:text-red-600 dark:hover:text-red-400 transition-colors"
      >
        <LogOut className="w-4 h-4" />
        Выйти
      </button>
    </div>
  )
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router   = useRouter()
  const { user, profile, loading, signOut } = useAuth()

  useEffect(() => {
    if (!loading && !user) router.replace("/auth/login")
  }, [loading, user, router])

  if (loading || !user) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <div className="flex items-center gap-3 text-slate-400 text-sm">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          Загрузка...
        </div>
      </div>
    )
  }

  const role     = profile?.role ?? "master"
  const navItems = ALL_NAV.filter(n => n.roles.includes(role))
  const badge    = ROLE_BADGE[role]
  const isAdmin  = role === "admin"

  const handleSignOut = async () => {
    await signOut()
    router.replace("/auth/login")
  }

  return (
    <SectionViewProvider
      effectiveSectionFromProfile={profile?.section ?? null}
      isAdmin={isAdmin}
    >
      <div className="flex h-screen bg-gray-50 dark:bg-gray-950">
        <aside className="w-64 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col">

          {/* Шапка сайдбара */}
          <div className="h-16 flex items-center px-5 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
            <div>
              <p className="text-sm font-bold text-gray-900 dark:text-white leading-none tracking-widest">STTB</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Система обслуживания</p>
            </div>
          </div>

          {/* Навигация */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
            {navItems.map((item) => {
              const active = item.exact ? pathname === item.href : pathname.startsWith(item.href)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                    active
                      ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-400"
                      : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white"
                  )}
                >
                  <item.icon className="w-4 h-4 flex-shrink-0" />
                  <span className="flex-1">{item.label}</span>
                  {active && <ChevronRight className="w-3.5 h-3.5" />}
                </Link>
              )
            })}
          </nav>

          <UserBlockWithSection
            profile={profile}
            user={user}
            role={role}
            badge={badge}
            onSignOut={handleSignOut}
          />
        </aside>

        <main className="flex-1 overflow-auto" key={pathname}>
          {children}
        </main>
      </div>
    </SectionViewProvider>
  )
}
