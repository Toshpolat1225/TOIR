"use client"

import Link from "next/link"
import { Users, Package, ChevronRight, FolderOpen, Building2, Wrench, Gauge, Settings } from "lucide-react"

const DIRECTORIES = [
  {
    href: "/dashboard/directories/employees",
    label: "Работники",
    description: "Справочник сотрудников предприятия",
    icon: Users,
    color: "bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400",
  },
  {
    href: "/dashboard/directories/sections",
    label: "Участки",
    description: "Справочник участков для нарядов и пользователей",
    icon: Building2,
    color: "bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400",
  },
  {
    href: "/dashboard/directories/work-types",
    label: "Виды работ и ТМЦ",
    description: "Шаблоны видов работ с подзадачами и списками ТМЦ",
    icon: Wrench,
    color: "bg-amber-100 text-amber-600 dark:bg-amber-900/50 dark:text-amber-400",
  },
  {
    href: "/dashboard/directories/maintenance-intervals",
    label: "Интервалы ТО",
    description: "Настройка пробегов для каждого типа ремонта (ТО-1, ТО-2 и т.д.)",
    icon: Gauge,
    color: "bg-orange-100 text-orange-600 dark:bg-orange-900/50 dark:text-orange-400",
  },
  {
    href: "/dashboard/tmc",
    label: "Номенклатура ТМЦ",
    description: "Справочник товарно-материальных ценностей",
    icon: Package,
    color: "bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-400",
  },
]

export default function DirectoriesPage() {
  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
          <FolderOpen className="w-7 h-7 text-gray-400" />
          Справочники
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Управление справочными данными системы
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {DIRECTORIES.map((dir) => (
          <Link
            key={dir.href}
            href={dir.href}
            className="group bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-5 hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-lg transition-all"
          >
            <div className="flex items-start gap-4">
              <div className={`p-3 rounded-xl ${dir.color}`}>
                <dir.icon className="w-6 h-6" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                  {dir.label}
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {dir.description}
                </p>
              </div>
              <ChevronRight className="w-5 h-5 text-gray-300 dark:text-gray-600 group-hover:text-blue-500 group-hover:translate-x-1 transition-all" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
