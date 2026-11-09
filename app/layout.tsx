import type { Metadata } from 'next'
import { Providers } from '@/lib/providers'
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
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
