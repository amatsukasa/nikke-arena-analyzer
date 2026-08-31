import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('アカウント情報');

export default function AccountLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
