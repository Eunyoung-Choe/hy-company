import DemoDocs from './DemoDocs';

export const metadata = { title: '데모 자료' };

// 에이전트가 캡처하는 시연용 고객 화면이라 머리말·이전 버튼을 두지 않는다
export default function DemoPage() {
  return (
    <main className="desk narrow">
      <DemoDocs />
    </main>
  );
}
