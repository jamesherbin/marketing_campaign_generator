import type { Metadata } from 'next'
import './globals.css'
import { themeInitializer } from '@/lib/theme'

export const metadata: Metadata = {
  title: 'Campaign Studio',
  description: 'Plan, develop, execute, and optimize measurable marketing campaigns with an AI agent team.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeInitializer }} /></head>
      <body>
        {children}
      </body>
    </html>
  )
}
