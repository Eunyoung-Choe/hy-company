import type { Metadata } from 'next';
import Link from 'next/link';
import './pii.css';

export const metadata: Metadata = {
  title: { default: 'PII Guard · 실시간 화면 마스킹', template: '%s · PII Guard' },
  robots: { index: false, follow: false },
};

export default function PiiLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="pii">
      <header className="topbar">
        <Link href="/pii" className="brand">PII Guard</Link>
        <nav>
          <Link href="/pii/demo">① 데모 자료</Link>
          <Link href="/pii/viewer">② 원격 화면</Link>
          <Link href="/pii/audit">③ 감사 로그</Link>
        </nav>
      </header>
      {children}
    </div>
  );
}
