import type { Metadata } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { Providers } from '@/lib/providers'
import { cookies } from 'next/headers'
import { DEFAULT_LOCALE, isLocale, LOCALE_COOKIE } from '@/lib/locale'
import './globals.css'


export const metadata: Metadata = {
  title: 'STTB — Система ТО',
  description: 'Система управления техническим обслуживанием STTB',
  icons: {
    icon: [
      { url: '/icon.svg', type: 'image/svg+xml' },
    ],
  },
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get(LOCALE_COOKIE)?.value
  const locale = isLocale(cookieLocale) ? cookieLocale : DEFAULT_LOCALE

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <Providers initialLocale={locale}>{children}</Providers>
        <Analytics />
      </body>
    </html>
  )
}
