"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback, useMemo, useRef } from "react"

/**
 * The filter state of a page lives in the URL query (shareable, the back button works).
 * `set` merges a patch; discrete choices push a history entry, typed text replaces the current one.
 */
export function useUrlState<F extends object>(parse: (search: URLSearchParams) => F, serialize: (state: F) => string) {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const key = params.toString()
  const state = useMemo(() => parse(new URLSearchParams(key)), [key, parse])
  const latest = useRef(state)
  latest.current = state

  const commit = useCallback(
    (next: F, replace: boolean) => {
      const query = serialize(next)
      const url = query ? `${pathname}?${query}` : pathname
      if (replace) router.replace(url, { scroll: false })
      else router.push(url, { scroll: false })
    },
    [pathname, router, serialize],
  )
  const set = useCallback(
    (patch: Partial<F>, options: { replace?: boolean } = {}) => commit({ ...latest.current, ...patch }, options.replace ?? false),
    [commit],
  )
  const reset = useCallback((next: F) => commit(next, false), [commit])
  return { state, set, reset, query: serialize(state) }
}
