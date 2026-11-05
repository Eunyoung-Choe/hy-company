import Link from 'next/link';

const steps = [
  { n: '1', title: '연속 캡처', who: 'CPU · mss', body: '화면을 60FPS로 캡처해 RAM의 Ring Buffer A에 덮어씁니다. 파일로 저장하지 않습니다.' },
  { n: '2', title: 'PII 좌표 추출', who: 'GPU · EasyOCR + Regex', body: '주민번호·카드·계좌·CVC/OTP·주소·휴대폰 번호의 좌표(BBOX)만 뽑고, 인식된 텍스트는 바로 버립니다.' },
  { n: '3', title: '즉시 마스킹', who: 'CPU · OpenCV', body: '좌표에 검은 박스를 덮어 그립니다. 아직 OCR 검증을 받지 않은 변경 영역은 직전 검증 화면으로 잠시 보류합니다(Fail-closed).' },
  { n: '4', title: '송출 · 감사 로그', who: '비동기 스레드', body: '마스킹 완성본만 송출하고, 개인정보가 감지되면 마스킹된 결과물만 Supabase Storage에 올립니다.' },
];

export default function PiiHome() {
  return (
    <main className="page">
      <h1>실시간 화면 개인정보 마스킹</h1>
      <p className="lead">
        상대방에게는 개인정보가 가려진 화면만 전달됩니다. 아래 순서대로 직접 확인해 보세요.
      </p>
      <ol className="flow">
        {steps.map((s) => (
          <li key={s.n} className="card">
            <span className="step-n">{s.n}단계</span>
            <h3>{s.title}</h3>
            <small>{s.who}</small>
            <p>{s.body}</p>
          </li>
        ))}
      </ol>

      <h2>시연 방법</h2>
      <ol className="howto">
        <li><code>agent</code> 폴더에서 마스킹 에이전트를 실행합니다 (<code>README.md</code> 참고).</li>
        <li>한 창에서 <Link href="/pii/demo">데모 자료</Link>를 엽니다. 에이전트는 이 창이 있는 영역을 캡처합니다.</li>
        <li>다른 창(또는 다른 모니터)에서 <Link href="/pii/viewer">원격 화면</Link>을 열어 마스킹 결과를 확인합니다.</li>
        <li>개인정보가 감지되면 <Link href="/pii/audit">감사 로그</Link>에 마스킹된 결과물이 쌓입니다.</li>
      </ol>
    </main>
  );
}
