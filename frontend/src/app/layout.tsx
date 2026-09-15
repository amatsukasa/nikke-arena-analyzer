import type { Metadata } from 'next'
import { headers } from 'next/headers'
import { Inter } from 'next/font/google'
import './globals.css'
import { AuthProvider } from '../context/AuthContext'
import Navbar from '../components/Navbar'
import { I18nProvider } from '../i18n/I18nProvider'
import { defaultLocale, isLocale, locales, localizePath } from '../i18n/config'
import { getMessages } from '../i18n/messages'

const inter = Inter({ subsets: ['latin'] })
const defaultMetadata = {
  title: 'にけあり！ | NIKKE Arena Analyzer',
  description: 'チャンピオンアリーナがもっと楽しくなるファンサイト',
}

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers()
  const candidate = requestHeaders.get('x-nikke-locale')
  const locale = isLocale(candidate) ? candidate : defaultLocale
  const messages = await getMessages(locale)
  const pathname = requestHeaders.get('x-nikke-pathname') || '/'
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://nikkeari.cc'
  return {
    title: messages['site.title'] || defaultMetadata.title,
    description: messages['site.description'] || defaultMetadata.description,
    alternates: {
      canonical: `${siteUrl}${localizePath(pathname, locale)}`,
      languages: Object.fromEntries(locales.map((item) => [item, `${siteUrl}${localizePath(pathname, item)}`])),
    },
  }
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const requestHeaders = await headers()
  const candidate = requestHeaders.get('x-nikke-locale')
  const locale = isLocale(candidate) ? candidate : defaultLocale
  const messages = await getMessages(locale)

  return (
    <html lang={locale} className="dark">
      <head>
        <script
          async
          src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9340334743814122"
          crossOrigin="anonymous"
        />
      </head>

      <body className={`${inter.className} bg-slate-950 text-slate-100 min-h-screen antialiased`}>
        <I18nProvider locale={locale} messages={messages}>
          <AuthProvider>
            <Navbar />
            {children}
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  )
}
