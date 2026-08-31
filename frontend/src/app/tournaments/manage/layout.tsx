import { privatePageMetadata } from '@/lib/privatePageMetadata';

export const metadata = privatePageMetadata('大会管理');

export default function TournamentManagementLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
