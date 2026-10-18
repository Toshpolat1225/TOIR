"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import {
  Wrench, ClipboardList, LayoutDashboard, PanelLeftIcon,
  ChevronRight, Package, Landmark, LogOut, Users, FileText, ChevronDown, FolderOpen,
  BarChart3,
} from "@/components/ui/icons"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { SectionViewProvider, useSectionView } from "@/lib/section-view-context"
import { useSections, type SectionData } from "@/lib/use-sections"
import { ThemeSwitcher } from "@/components/theme-switcher"
import { useLocale } from "@/lib/i18n"

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
  { href: "/dashboard/admin/translations", label: "Переводы", icon: Package, roles: ["admin"] },
  { href: "/dashboard/admin/asset-catalogs", label: "Справочники ОС", icon: Package, roles: ["admin"] },
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
  sections,
  sectionsData,
  sectionsLoading,
  onSignOut,
}: {
  profile: { full_name?: string | null; section?: string | null; section_id?: string | null } | null
  user: { email?: string } | null
  role: string
  badge: { label: string; cls: string }
  sections: string[]
  sectionsData: SectionData[]
  sectionsLoading: boolean
  onSignOut: () => void
}) {
  const { t } = useLocale()
  const isAdmin = role === "admin"
  const { viewSection, setViewSection } = useSectionView()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const sectionName = sectionsData.find((section) => section.id === profile?.section_id)?.localized_name
    ?? profile?.section
    ?? sectionsData.find((section) => section.id === profile?.section_id)?.name
    ?? null

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
        ) : sectionName ? (
          <div className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-100 dark:bg-gray-700/50 text-gray-700 dark:text-gray-300">
            <span className="truncate">{sectionName}</span>
          </div>
        ) : null}
        <span className={cn("inline-block text-xs px-2 py-0.5 rounded-full font-medium mt-2", badge.cls)}>
          {t(badge.label)}
        </span>
      </div>

      <button
        onClick={onSignOut}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-950/50 hover:text-red-600 dark:hover:text-red-400 transition-colors"
      >
        <LogOut className="w-4 h-4" />
        {t("Выйти")}
      </button>
    </div>
  )
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router   = useRouter()
  const { user, profile, loading, signOut } = useAuth()
  const { t } = useLocale()
  const { sections, sectionsData, loading: sectionsLoading } = useSections()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

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
  const sectionName = sectionsData.find((section) => section.id === profile?.section_id)?.localized_name
    ?? profile?.section
    ?? sectionsData.find((section) => section.id === profile?.section_id)?.name
    ?? null
  const currentPage = navItems.find((item) =>
    item.exact ? pathname === item.href : pathname.startsWith(item.href)
  )

  const handleSignOut = async () => {
    await signOut()
    router.replace("/auth/login")
  }

  return (
    <SectionViewProvider
      effectiveSectionFromProfile={sectionName}
      isAdmin={isAdmin}
    >
      <div className="min-h-screen bg-slate-50 dark:bg-gray-950">
        {mobileNavOpen && (
          <button type="button" aria-label="Закрыть навигацию" className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-[2px] md:hidden" onClick={() => setMobileNavOpen(false)} />
        )}
        <aside className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col border-r border-slate-200 bg-white transition-transform duration-200 dark:border-gray-800 dark:bg-gray-900 md:translate-x-0 md:shadow-none",
          mobileNavOpen ? "translate-x-0 shadow-xl" : "-translate-x-full"
        )}>
          <div className="flex h-16 shrink-0 items-center gap-3 border-b border-slate-200 px-5 dark:border-gray-800">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-700 text-white"><Wrench className="h-4 w-4" /></div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold leading-tight tracking-wide text-slate-900 dark:text-white">STTB</p>
              <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-gray-400">Техническое обслуживание</p>
            </div>
            <button type="button" aria-label="Закрыть навигацию" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 md:hidden dark:text-gray-400 dark:hover:bg-gray-800" onClick={() => setMobileNavOpen(false)}>
              <ChevronRight className="h-4 w-4 rotate-180" />
            </button>
          </div>
          <div className="px-5 pb-2 pt-6 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-gray-500">РАБОЧЕЕ ПРОСТРАНСТВО</div>
          <nav aria-label="Основная навигация" className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
            {navItems.map((item) => {
              const active = item.exact ? pathname === item.href : pathname.startsWith(item.href)
              return (
                <Link key={item.href} href={item.href} onClick={() => setMobileNavOpen(false)} aria-current={active ? "page" : undefined}
                  className={cn(
                    "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    active ? "bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white"
                  )}>
                  <item.icon className={cn("h-4 w-4 shrink-0", active ? "text-blue-700 dark:text-blue-300" : "text-slate-400 group-hover:text-slate-600 dark:text-gray-500")} />
                  <span className="min-w-0 flex-1 truncate">{t(item.label)}</span>
                  {active && <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />}
                </Link>
              )
            })}
          </nav>
          <UserBlockWithSection
            profile={profile}
            user={user}
            role={role}
            badge={badge}
            sections={sections}
            sectionsData={sectionsData}
            sectionsLoading={sectionsLoading}
            onSignOut={handleSignOut}
          />
        </aside>
        <div className="min-h-screen md:ml-[272px]">
          <header className="navbar navbar-expand-lg sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur md:px-8 dark:border-gray-800 dark:bg-gray-900/95">
            <div className="flex min-w-0 items-center gap-3">
              <button type="button" aria-label="Открыть навигацию" aria-expanded={mobileNavOpen} className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden dark:text-gray-300 dark:hover:bg-gray-800" onClick={() => setMobileNavOpen(true)}>
                <PanelLeftIcon className="h-5 w-5" />
              </button>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{t(currentPage?.label ?? "Рабочее пространство")}</p>
                <p className="hidden text-xs text-slate-500 sm:block dark:text-gray-400">Система управления техническим обслуживанием</p>
              </div>
            </div>
            <div className="ml-3 flex shrink-0 items-center gap-3">
              <ThemeSwitcher />
              <span className={cn("hidden rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex", badge.cls)}>{t(badge.label)}</span>
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-700 dark:bg-gray-800 dark:text-gray-200">
                {(profile?.full_name || user.email || "U").slice(0, 1).toUpperCase()}
              </div>
            </div>
          </header>
          <main className="min-w-0" key={pathname}>{children}</main>
        </div>
      </div>
    </SectionViewProvider>
  )
}
