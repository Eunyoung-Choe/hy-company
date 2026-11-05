import Link from 'next/link';
import VideoSummarizer from '@/components/VideoSummarizer';

export default function Home() {
  return (
    <>
      <VideoSummarizer />
      {/* 임시: PII Guard로 가는 버튼. 팀원 화면(VideoSummarizer·globals.css)을 건드리지 않게 여기에만 둠 */}
      <Link
        href="/pii"
        style={{
          position: 'fixed', top: 16, right: 16, zIndex: 50,
          padding: '10px 16px', borderRadius: 999, background: '#111827', color: '#fff',
          fontSize: 14, fontWeight: 600, textDecoration: 'none', boxShadow: '0 4px 14px rgba(0,0,0,.18)',
        }}
      >
        🛡️ PII Guard 바로가기 →
      </Link>
    </>
  );
}
