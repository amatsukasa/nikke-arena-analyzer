import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('スタッフログイン');

export default function StaffLoginLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
