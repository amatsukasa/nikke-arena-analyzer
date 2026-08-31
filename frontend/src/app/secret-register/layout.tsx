import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('スタッフ登録');

export default function StaffRegistrationLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
