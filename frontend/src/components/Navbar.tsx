'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Trophy } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import DrawerMenu from './DrawerMenu';

const navigationHiddenRoutes = ['/secret-login', '/secret-register', '/approve-registration'];

export default function Navbar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  if (navigationHiddenRoutes.some((route) => pathname.startsWith(route))) {
    return null;
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b border-white/10 bg-slate-950/95">
      <nav
        aria-label="サイト共通ナビゲーション"
        className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-3 sm:px-6"
      >
        <Link
          href="/"
          aria-label="にけあり！｜NIKKE ARENA ANALYZER トップページ"
          className="flex min-w-0 items-center gap-2.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 sm:gap-3"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-600 shadow-lg shadow-blue-500/20 sm:h-10 sm:w-10">
            <Trophy aria-hidden="true" className="h-5 w-5 text-white sm:h-6 sm:w-6" />
          </span>
          <span className="min-w-0 truncate bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-[11px] font-black tracking-tight text-transparent min-[360px]:text-xs sm:text-lg sm:tracking-wide">
            にけあり！<span aria-hidden="true">｜</span>NIKKE ARENA ANALYZER
          </span>
        </Link>

        <DrawerMenu user={user} onLogout={logout} />
      </nav>
    </header>
  );
}
