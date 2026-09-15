'use client';

import { createContext, useCallback, useContext, useMemo } from 'react';
import type { Locale } from './config';
import { localizePath } from './config';
import type { Messages } from './messages';

type Values = Record<string, string | number>;
type I18nValue = {
  locale: Locale;
  t: (key: string, values?: Values) => string;
  href: (path: string) => string;
};

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ locale, messages, children }: { locale: Locale; messages: Messages; children: React.ReactNode }) {
  const t = useCallback((key: string, values?: Values) => {
    let text = messages[key] ?? key;
    if (values) {
      for (const [name, value] of Object.entries(values)) text = text.replaceAll(`{${name}}`, String(value));
    }
    return text;
  }, [messages]);
  const href = useCallback((path: string) => localizePath(path, locale), [locale]);
  const value = useMemo(() => ({ locale, t, href }), [locale, t, href]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error('useI18n must be used inside I18nProvider');
  return value;
}
