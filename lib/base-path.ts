/**
 * The sub-path the site is served under ("" for the main site, "/demo" for the demo copy). It is baked in at build time
 * (NEXT_PUBLIC_BASE_PATH, also used as Next.js `basePath`). Next's <Link> and router add it by themselves; raw <a href>,
 * hand-built HTML and cookie paths do not, so they go through withBase().
 */
export const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").replace(/\/+$/, "")

export function withBase(path: string): string {
  return `${BASE_PATH}${path}`
}
