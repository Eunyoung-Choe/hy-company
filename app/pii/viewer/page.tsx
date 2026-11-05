import Viewer from './Viewer';

export const metadata = { title: '원격 화면' };

export default function ViewerPage() {
  return (
    <main className="page wide">
      <h1>원격 상대방 화면</h1>
      <p className="lead">에이전트가 보낸 마스킹 완성본만 표시합니다. 원본 픽셀은 이 화면으로 전달되지 않습니다.</p>
      <Viewer />
    </main>
  );
}
