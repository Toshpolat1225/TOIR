"use client"

import { useState, useEffect, useCallback } from "react"
import { supabase } from "@/lib/supabase"

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
    const { data, error } = await supabase
      .from("sections")
      .select("id, name")
      .order("name", { ascending: true })
    if (!error && data) {
      setSections(data.map((r: { name: string }) => r.name))
      setSectionsData(data as SectionData[])
    } else {
      setSections([])
      setSectionsData([])
    }
    setLoading(false)
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // Получить ID участка по имени
  const getSectionId = useCallback((name: string): string | undefined => {
    return sectionsData.find(s => s.name === name)?.id
  }, [sectionsData])

  return { sections, sectionsData, loading, refresh, getSectionId }
}
