export const LOCALES = ["uz-Latn", "uz-Cyrl", "ru"] as const
export type Locale = (typeof LOCALES)[number]
export const DEFAULT_LOCALE: Locale = "ru"
export const LOCALE_COOKIE = "toir-locale"

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value)
}