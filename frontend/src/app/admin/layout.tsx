import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('管理者画面');

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
