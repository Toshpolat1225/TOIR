"use client"

import { useState } from "react"
import { useTheme } from "next-themes"
import { CheckIcon, ChevronDown, Palette } from "@/components/ui/icons"
import { cn } from "@/lib/utils"

const themes = [
  { id: "light", label: "Арктика", detail: "Светлая · Синяя", color: "#2563eb" },
  { id: "dark", label: "Полночь", detail: "Тёмная · Синяя", color: "#60a5fa" },
  { id: "ocean", label: "Океан", detail: "Светлая · Бирюзовая", color: "#0f766e" },
  { id: "emerald", label: "Изумруд", detail: "Светлая · Зелёная", color: "#15803d" },
  { id: "violet", label: "Аметист", detail: "Светлая · Фиолетовая", color: "#6d28d9" },
  { id: "graphite", label: "Графит", detail: "Тёмная · Серая", color: "#94a3b8" },
] as const

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)
  const selected = themes.find((item) => item.id === theme) ?? themes[0]

  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Выбрать тему оформления"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
      >
        <Palette className="h-4 w-4" style={{ color: selected.color }} />
        <span className="hidden sm:inline">{selected.label}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 text-slate-400 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-label="Закрыть меню тем"
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div
            role="listbox"
            aria-label="Темы оформления"
            className="absolute right-0 z-50 mt-2 w-60 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-900/10 dark:border-gray-700 dark:bg-gray-900 dark:shadow-black/30"
          >
            <p className="px-2.5 pb-1.5 pt-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">
              Тема оформления
            </p>
            {themes.map((option) => (
              <button
                key={option.id}
                type="button"
                role="option"
                aria-selected={theme === option.id}
                onClick={() => {
                  setTheme(option.id)
                  setOpen(false)
                }}
                className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-slate-50 dark:hover:bg-gray-800"
              >
                <span
                  aria-hidden="true"
                  className="h-4 w-4 shrink-0 rounded-full ring-2 ring-white ring-offset-1 ring-offset-slate-200 dark:ring-offset-gray-700"
                  style={{ backgroundColor: option.color }}
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-slate-800 dark:text-gray-100">{option.label}</span>
                  <span className="block text-[11px] text-slate-500 dark:text-gray-400">{option.detail}</span>
                </span>
                {theme === option.id && <CheckIcon className="h-4 w-4 text-blue-600 dark:text-blue-400" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
