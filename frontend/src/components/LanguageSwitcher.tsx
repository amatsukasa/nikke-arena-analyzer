'use client';

import { Globe } from 'lucide-react';
import { usePathname, useSearchParams } from 'next/navigation';
import { localeCookie, localeNames, locales, localizePath, type Locale } from '@/i18n/config';
import { useI18n } from '@/i18n/I18nProvider';

export default function LanguageSwitcher() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { locale, t } = useI18n();

  const changeLocale = (nextLocale: Locale) => {
    document.cookie = `${localeCookie}=${nextLocale}; path=/; max-age=31536000; SameSite=Lax`;
    const query = searchParams.toString();
    window.location.assign(`${localizePath(pathname, nextLocale)}${query ? `?${query}` : ''}`);
  };

  return (
    <label className="flex min-w-0 items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 ring-1 ring-white/10">
      <Globe aria-hidden="true" className="h-4 w-4 shrink-0 text-blue-300" />
      <span className="sr-only">{t('language.label')}</span>
      <select
        aria-label={t('language.label')}
        value={locale}
        onChange={(event) => changeLocale(event.target.value as Locale)}
        className="min-w-0 flex-1 bg-transparent text-sm font-bold text-slate-200 outline-none"
      >
        {locales.map((item) => <option key={item} value={item} className="bg-slate-900">{localeNames[item]}</option>)}
      </select>
    </label>
  );
}
