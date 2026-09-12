import type { Locale } from './config';

export type Messages = Record<string, string>;

export async function getMessages(locale: Locale): Promise<Messages> {
  return (await import(`../../locales/${locale}.json`)).default;
}
