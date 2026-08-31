'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';

type DrawerUser = {
  email: string;
  role: string;
} | null;

type DrawerMenuProps = {
  user: DrawerUser;
  onLogout: () => void | Promise<void>;
};

const mainItems = [
  { href: '/', label: 'TOP' },
  { href: '/about', label: 'ABOUT' },
  { href: '/guide', label: 'GUIDE' },
  { href: '/links', label: 'LINK' },
  { href: '/updates', label: 'UPDATE' },
  { href: '/contact', label: 'CONTACT' },
  { href: '/privacy', label: 'PRIVACY' },
] as const;

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export default function DrawerMenu({ user, onLogout }: DrawerMenuProps) {
  const pathname = usePathname();
  const drawerId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const wasOpenRef = useRef(false);

  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (!isOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab' || !drawerRef.current) return;

      const focusable = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(focusableSelector),
      ).filter((element) => !element.hasAttribute('disabled'));
      if (focusable.length === 0) {
        event.preventDefault();
        drawerRef.current.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [close, isOpen]);

  useEffect(() => {
    if (wasOpenRef.current && !isOpen) triggerRef.current?.focus();
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  useEffect(() => {
    close();
  }, [close, pathname]);

  const isCurrent = (href: string) =>
    href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={isOpen ? 'メニューを閉じる' : 'メニューを開く'}
        aria-expanded={isOpen}
        aria-controls={drawerId}
        onClick={() => setIsOpen((current) => !current)}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-200 ring-1 ring-white/15 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 motion-reduce:transition-none"
      >
        <Menu aria-hidden="true" size={24} />
      </button>

      <div
        data-testid="drawer-overlay"
        aria-hidden="true"
        onClick={close}
        className={`fixed inset-0 z-[60] bg-black/65 backdrop-blur-sm transition-opacity duration-200 motion-reduce:transition-none ${
          isOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />

      <aside
        ref={drawerRef}
        id={drawerId}
        role="dialog"
        aria-modal="true"
        aria-label="サイトメニュー"
        aria-hidden={!isOpen}
        inert={!isOpen}
        tabIndex={-1}
        className={`fixed right-0 top-0 z-[70] flex h-dvh w-[min(88vw,24rem)] flex-col border-l border-white/10 bg-slate-950 shadow-2xl transition-transform duration-200 ease-out motion-reduce:transition-none ${
          isOpen ? 'translate-x-0' : 'pointer-events-none translate-x-full'
        }`}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/10 px-5">
          <span className="text-sm font-black tracking-[0.18em] text-slate-300">MENU</span>
          <button
            ref={closeButtonRef}
            type="button"
            aria-label="メニューを閉じる"
            onClick={close}
            className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-300 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 motion-reduce:transition-none"
          >
            <X aria-hidden="true" size={24} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-6">
          <nav aria-label="メインメニュー">
            <ul className="space-y-2">
              {mainItems.map((item) => {
                const current = isCurrent(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={close}
                      aria-current={current ? 'page' : undefined}
                      className={`flex items-center justify-between rounded-xl px-4 py-3 text-base font-bold tracking-wide transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 motion-reduce:transition-none ${
                        current
                          ? 'bg-blue-500/15 text-blue-300 ring-1 ring-blue-400/30'
                          : 'text-slate-300 hover:bg-white/5 hover:text-white'
                      }`}
                    >
                      {item.label}
                      {current && <span className="h-2 w-2 rounded-full bg-blue-400" aria-hidden="true" />}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

        </div>
      </aside>
    </>
  );
}
