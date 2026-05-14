import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Ninja AI Proxy',
  description: 'AI Proxy Service for Ninja Telegram Userbot',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
