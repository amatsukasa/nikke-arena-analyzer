import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('大会データ登録');

export default function TournamentRegistrationLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
