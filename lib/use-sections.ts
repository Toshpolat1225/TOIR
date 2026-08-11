"use client"

import { useState, useEffect, useCallback } from "react"
import { api } from "@/lib/api"

export type SectionData = {
  id: string
  name: string
}

export function useSections() {
  const [sections, setSections] = useState<string[]>([])
  const [sectionsData, setSectionsData] = useState<SectionData[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.sections.list({ limit: 1000, sort_by: "name", sort_order: "asc" });
      setSections(response.items.map((r) => r.name));
      setSectionsData(response.items);
    } catch (error) {
      console.error("Failed to fetch sections:", error);
      setSections([])
      setSectionsData([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // Получить ID участка по имени
  const getSectionId = useCallback((name: string): string | undefined => {
    return sectionsData.find(s => s.name === name)?.id
  }, [sectionsData])

  return { sections, sectionsData, loading, refresh, getSectionId }
}
