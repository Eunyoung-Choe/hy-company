import Viewer from './Viewer';

export const metadata = { title: '원격 화면' };

export default function ViewerPage() {
  return (
    <main className="page wide">
      <h1>원격 상대방 화면</h1>
      <p className="lead">
        수리기사가 원격으로 보고 있는 고객 PC 화면입니다.<br />
        수리 중 개인정보가 담긴 문서가 화면에 나타나면 고객 PC에서 바로 가린 뒤 전송되어,수리기사에게는 원본이 보이지 않습니다.
      </p>
      <Viewer />
    </main>
  );
}