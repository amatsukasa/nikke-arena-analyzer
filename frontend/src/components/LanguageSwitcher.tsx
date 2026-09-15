'use client';

import { Check, Globe } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { localeCookie, localeNames, locales, localizePath, type Locale } from '@/i18n/config';
import { useI18n } from '@/i18n/I18nProvider';

export default function LanguageSwitcher() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { locale, t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const changeLocale = (nextLocale: Locale) => {
    document.cookie = `${localeCookie}=${nextLocale}; path=/; max-age=31536000; SameSite=Lax`;
    const query = searchParams.toString();
    window.location.assign(`${localizePath(pathname, nextLocale)}${query ? `?${query}` : ''}`);
  };

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        aria-label={t('language.label')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex h-11 w-11 items-center justify-center rounded-xl text-slate-200 ring-1 ring-white/15 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
      >
        <Globe aria-hidden="true" className="h-5 w-5" />
      </button>
      {open && (
        <div role="menu" aria-label={t('language.label')} className="absolute right-0 top-[calc(100%+0.5rem)] z-50 w-44 overflow-hidden rounded-xl border border-white/10 bg-slate-900 p-1.5 shadow-2xl">
          {locales.map((item) => (
            <button key={item} type="button" role="menuitemradio" aria-checked={item === locale} onClick={() => changeLocale(item)} className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-bold transition-colors ${item === locale ? 'bg-blue-500/15 text-blue-300' : 'text-slate-300 hover:bg-white/5 hover:text-white'}`}>
              <span className="flex h-4 w-4 items-center justify-center">{item === locale && <Check aria-hidden="true" className="h-4 w-4" />}</span>
              {localeNames[item]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
