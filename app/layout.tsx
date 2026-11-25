import type { Metadata } from 'next'
import { Providers } from '@/lib/providers'
import './globals.css'


export const metadata: Metadata = {
  title: 'НейроТОиР — Система ТО и ремонта',
  description: 'Система управления техническим обслуживанием и ремонтом НейроТОиР',
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
