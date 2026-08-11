import { supabase } from "./supabase"
import type { PostgrestFilterBuilder } from "@supabase/postgrest-js"

/**
 * Выполняет Supabase запрос с таймаутом
 * @param query - Supabase query builder
 * @param timeoutMs - Таймаут в миллисекундах (по умолчанию 10 секунд)
 * @returns Результат запроса или ошибка таймаута
 */
export async function withTimeout<T>(
  queryFn: () => Promise<{ data: T | null; error: unknown }>,
  timeoutMs: number = 10000
): Promise<{ data: T | null; error: unknown }> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const result = await Promise.race([
      queryFn(),
      new Promise<{ data: null; error: Error }>((_, reject) => {
        controller.signal.addEventListener("abort", () => {
          reject({ data: null, error: new Error(`Query timeout after ${timeoutMs}ms`) })
        })
      })
    ])
    return result
  } catch (error) {
    return { data: null, error }
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Безопасный fetch с таймаутом и обработкой ошибок
 */
export async function safeFetch<T>(
  queryFn: () => Promise<{ data: T | null; error: unknown }>,
  options: {
    timeout?: number
    fallback?: T
    onError?: (error: unknown) => void
  } = {}
): Promise<T | null> {
  const { timeout = 10000, fallback = null, onError } = options
  
  try {
    const result = await withTimeout(queryFn, timeout)
    
    if (result.error) {
      onError?.(result.error)
      console.warn("Supabase query error:", result.error)
      return fallback
    }
    
    return result.data
  } catch (error) {
    onError?.(error)
    console.error("Supabase query failed:", error)
    return fallback
  }
}

/**
 * Параллельная загрузка нескольких запросов с таймаутом
 */
export async function parallelFetch<T extends Record<string, unknown>>(
  queries: { [K in keyof T]: () => Promise<{ data: T[K] | null; error: unknown }> },
  timeout: number = 15000
): Promise<{ [K in keyof T]: T[K] | null }> {
  const keys = Object.keys(queries) as (keyof T)[]
  
  const results = await Promise.all(
    keys.map(key => 
      withTimeout(queries[key], timeout)
        .then(r => ({ key, data: r.data, error: r.error }))
        .catch(e => ({ key, data: null, error: e }))
    )
  )
  
  const output = {} as { [K in keyof T]: T[K] | null }
  for (const { key, data, error } of results) {
    if (error) {
      console.warn(`Query "${String(key)}" failed:`, error)
    }
    output[key] = data as T[keyof T] | null
  }
  
  return output
}

/**
 * Хук для отмены запросов при размонтировании компонента
 */
export function createQueryController() {
  const controller = new AbortController()
  
  return {
    signal: controller.signal,
    abort: () => controller.abort(),
    isAborted: () => controller.signal.aborted,
  }
}

/**
 * Утилита для batch загрузки связанных данных (избегаем N+1)
 */
export async function batchLoadRelated<T, R>(
  items: T[],
  getIds: (item: T) => string | null,
  loadRelated: (ids: string[]) => Promise<{ data: R[] | null; error: unknown }>,
  getRelatedId: (related: R) => string
): Promise<Map<string, R>> {
  const ids = [...new Set(items.map(getIds).filter((id): id is string => id !== null))]
  
  if (ids.length === 0) {
    return new Map()
  }
  
  const { data, error } = await loadRelated(ids)
  
  if (error || !data) {
    console.warn("Failed to load related data:", error)
    return new Map()
  }
  
  return new Map(data.map(item => [getRelatedId(item), item]))
}
