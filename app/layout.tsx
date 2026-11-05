import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'VideoDigest · 토큰 최적화 영상 요약',
  description: 'OpenCV와 DINOv2로 핵심 장면만 골라 텍스트로 요약하는 영상 요약 서비스',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
