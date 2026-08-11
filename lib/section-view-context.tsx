"use client"

import { createContext, useContext, useState, useMemo, ReactNode } from "react"

type SectionViewContextType = {
  /** Выбранный участок для отображения (только для админа; null = все) */
  viewSection: string | null
  setViewSection: (s: string | null) => void
  /** Эффективный участок: для мастера — его участок, для админа — viewSection */
  effectiveSection: string | null
}

const defaultContext: SectionViewContextType = {
  viewSection: null,
  setViewSection: () => {},
  effectiveSection: null,
}

const SectionViewContext = createContext<SectionViewContextType>(defaultContext)

export function SectionViewProvider({
  children,
  effectiveSectionFromProfile,
  isAdmin,
}: {
  children: ReactNode
  effectiveSectionFromProfile: string | null
  isAdmin: boolean
}) {
  const [viewSection, setViewSection] = useState<string | null>(null)
  const effectiveSection = isAdmin ? (viewSection ?? null) : effectiveSectionFromProfile
  const value = useMemo(
    () => ({
      viewSection: isAdmin ? viewSection : null,
      setViewSection: isAdmin ? setViewSection : () => {},
      effectiveSection,
    }),
    [isAdmin, viewSection, effectiveSection]
  )
  return (
    <SectionViewContext.Provider value={value}>
      {children}
    </SectionViewContext.Provider>
  )
}

export function useSectionView() {
  const ctx = useContext(SectionViewContext)
  return ctx ?? defaultContext
}
