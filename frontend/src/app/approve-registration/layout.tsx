import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('スタッフ登録承認');

export default function RegistrationApprovalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
