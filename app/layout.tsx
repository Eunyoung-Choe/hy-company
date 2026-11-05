import type { Metadata } from 'next';
import Header from '@/components/Header';
import './globals.css';
export const metadata: Metadata = { title: { default: 'HY컴퍼니 | 함께할 기회', template: '%s | HY컴퍼니' }, description: '한양여자대학교 해커톤 실습용 HY컴퍼니 채용 사이트', robots: { index: false, follow: false } };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
 return <html lang="ko"><body><a className="skip-link" href="#main">본문 바로가기</a><Header/>{children}<footer><div className="footer-brand">HY COMPANY<span>우리의 다음 장을, 함께.</span></div><p>한양여자대학교 AI 해커톤 실습용 가상 기업입니다.<br/>예시 공고는 실제 채용이 아닙니다.</p><a className="footer-year" href="/setup">실습 연결 안내 ↗</a></footer></body></html>;
}
