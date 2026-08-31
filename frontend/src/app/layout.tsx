import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import Script from 'next/script'
import './globals.css'
import { AuthProvider } from '../context/AuthContext'
import Navbar from '../components/Navbar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'にけあり！ | NIKKE Arena Analyzer',
  description: 'チャンピオンアリーナがもっと楽しくなるファンサイト',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja" className="dark">
      <body className={`${inter.className} bg-slate-950 text-slate-100 min-h-screen antialiased`}>
        <AuthProvider>
          <Navbar />
          {children}
        </AuthProvider>

        <Script
          async
          src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9340334743814122"
          crossOrigin="anonymous"
          strategy="afterInteractive"
        />
      </body>
    </html>
  )
}
