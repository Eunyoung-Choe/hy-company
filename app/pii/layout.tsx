import type { Metadata } from 'next';
import './pii.css';

export const metadata: Metadata = {
  title: { default: 'PII Guard · 실시간 화면 마스킹', template: '%s · PII Guard' },
  robots: { index: false, follow: false },
};

export default function PiiLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className="pii">{children}</div>;
}
