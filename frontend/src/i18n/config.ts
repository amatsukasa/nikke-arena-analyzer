export const locales = ['ja', 'en', 'fr', 'ko', 'zh-CN'] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = 'ja';
export const localeCookie = 'nikke_locale';

export const localeNames: Record<Locale, string> = {
  ja: '日本語',
  en: 'English',
  fr: 'Français',
  ko: '한국어',
  'zh-CN': '中文',
};

export function isLocale(value: string | undefined | null): value is Locale {
  return locales.includes(value as Locale);
}

export function localeFromPathname(pathname: string): Locale {
  const segment = pathname.split('/')[1];
  return isLocale(segment) ? segment : defaultLocale;
}

export function stripLocale(pathname: string): string {
  const locale = localeFromPathname(pathname);
  if (locale === defaultLocale) return pathname || '/';
  const stripped = pathname.slice(locale.length + 1);
  return stripped || '/';
}

export function localizePath(pathname: string, locale: Locale): string {
  if (!pathname.startsWith('/') || pathname.startsWith('/api/')) return pathname;
  const base = stripLocale(pathname);
  return locale === defaultLocale ? base : `/${locale}${base === '/' ? '' : base}`;
}
