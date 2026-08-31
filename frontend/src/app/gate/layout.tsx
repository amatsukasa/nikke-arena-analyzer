import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('閲覧認証');

export default function GateLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
