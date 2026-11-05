import Link from 'next/link';
import DemoDocs from './DemoDocs';

export const metadata = { title: '데모 자료' };

export default function DemoPage() {
  return (
    <main className="page narrow">
      <p className="hint">
        이 창이 있는 영역을 에이전트가 캡처합니다. 여기는 원본 화면이고, 상대방은{' '}
        <Link href="/pii/viewer">원격 화면</Link>에서 마스킹된 결과만 봅니다.
      </p>
      <DemoDocs />
    </main>
  );
}
