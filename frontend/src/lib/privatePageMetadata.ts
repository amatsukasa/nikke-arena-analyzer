import type { Metadata } from 'next';

export function privatePageMetadata(title: string): Metadata {
  return {
    title: { absolute: title },
    robots: {
      index: false,
      follow: false,
    },
  };
}
