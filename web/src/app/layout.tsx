import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Hivemind Dashboard',
  description: 'Manage your Mac fleet',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
