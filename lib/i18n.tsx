export const LOCALES = ["ru"] as const
export type Locale = (typeof LOCALES)[number]
export const DEFAULT_LOCALE: Locale = "ru"

export function t(message: string): string {
  return message
}
