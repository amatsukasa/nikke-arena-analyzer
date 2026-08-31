import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('スタッフメニュー');

export default function StaffLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
