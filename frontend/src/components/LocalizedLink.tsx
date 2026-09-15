'use client';

import Link, { type LinkProps } from 'next/link';
import type { AnchorHTMLAttributes } from 'react';
import { useI18n } from '@/i18n/I18nProvider';

type Props = LinkProps & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, keyof LinkProps>;

export default function LocalizedLink({ href, ...props }: Props) {
  const { href: localizedHref } = useI18n();
  const target = typeof href === 'string' ? localizedHref(href) : href;
  return <Link href={target} {...props} />;
}
