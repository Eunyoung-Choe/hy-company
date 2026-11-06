import PiiHeader from '../PiiHeader';
import Viewer from './Viewer';

export const metadata = { title: '원격 화면' };

export default function ViewerPage() {
  return (
    <main className="desk wide">
      <PiiHeader lead="수리기사가 원격으로 보고 있는 고객 PC 화면입니다.">
        수리 중 개인정보가 담긴 문서가 화면에 나타나면 고객 PC에서 바로 가린 뒤 전송되어, 수리기사에게는 원본이 보이지 않습니다.
      </PiiHeader>
      <Viewer />
    </main>
  );
}
