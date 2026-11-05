import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'PII Guard · 실시간 화면 마스킹',
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">PII Guard</Link>
          <nav>
            <Link href="/demo">① 데모 자료</Link>
            <Link href="/viewer">② 원격 화면</Link>
            <Link href="/audit">③ 감사 로그</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
