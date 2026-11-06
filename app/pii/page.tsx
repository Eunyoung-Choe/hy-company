import Link from 'next/link';
import PiiHeader from './PiiHeader';

const steps = [
  { n: '1', title: '연속 캡처', who: 'CPU · mss / dxcam', body: '화면을 60FPS로 캡처해 RAM의 Ring Buffer A에 덮어씁니다. 파일로 저장하지 않습니다.' },
  { n: '2', title: 'PII 좌표 추출', who: 'Windows OCR(없으면 EasyOCR) + Regex', body: '주민번호·카드·계좌·CVC/OTP·주소·휴대폰 번호의 좌표(BBOX)만 뽑고, 인식된 텍스트는 바로 버립니다.' },
  { n: '3', title: '즉시 마스킹', who: 'CPU · OpenCV', body: '좌표에 검은 박스를 덮어 그립니다. 스크롤하면 박스도 함께 옮기고, 새로 드러난 영역만 확인할 때까지 모자이크로 가립니다.' },
  { n: '4', title: '송출 · 감사 로그', who: '비동기 스레드', body: '마스킹 완성본만 송출하고, 개인정보가 감지되면 마스킹된 결과물만 감사 로그로 남깁니다.' },
];

export default function PiiHome() {
  return (
    <main className="desk">
      <PiiHeader lead="실시간 화면 개인정보 마스킹">
        원격 수리 중 고객 화면의 개인정보를 가린 뒤 수리기사에게 보냅니다.
      </PiiHeader>

      <section className="win">
        <div className="win-title">🔎 처리 흐름</div>
        <div className="win-body">
          <ol className="pii-flow">
            {steps.map((s) => (
              <li key={s.n}>
                <span className="n">{s.n}단계</span>
                <b>{s.title}</b>
                <small>{s.who}</small>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="win">
        <div className="win-title">▶ 시연 방법</div>
        <div className="win-body">
          <ol className="howto">
            <li><code>agent</code> 폴더에서 마스킹 에이전트를 실행합니다 (<code>README.md</code> 참고).</li>
            <li>한 창에서 데모 자료를 엽니다. 에이전트는 이 창이 있는 영역을 캡처합니다.</li>
            <li>다른 창(또는 다른 모니터)에서 원격 화면을 열어 마스킹 결과를 확인합니다.</li>
            <li>개인정보가 감지되면 감사 로그에 마스킹된 결과물이 쌓입니다.</li>
          </ol>
          <div className="howto-actions">
            <Link href="/pii/demo" className="btn small">데모 자료 열기</Link>
            <Link href="/pii/viewer" className="btn small go">원격 화면 열기</Link>
            <Link href="/pii/audit" className="btn small">감사 로그 보기</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
