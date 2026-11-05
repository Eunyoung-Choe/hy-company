'use client';

import { launchPiiDemo } from '@/lib/piiWindows';

/** 임시: 첫 화면의 PII Guard 바로가기. 누르면 데모 창(왼쪽 절반)과 원격 화면(현재 탭)이 함께 열린다. */
export default function PiiLaunchButton() {
  return (
    <button
      type="button"
      onClick={launchPiiDemo}
      title="데모 창(왼쪽 절반)과 원격 화면이 함께 열립니다"
      style={{
        position: 'fixed', top: 16, right: 16, zIndex: 50, cursor: 'pointer', border: 0,
        padding: '10px 16px', borderRadius: 999, background: '#111827', color: '#fff',
        fontSize: 14, fontWeight: 600, boxShadow: '0 4px 14px rgba(0,0,0,.18)',
      }}
    >
      🛡️ PII Guard 바로가기 →
    </button>
  );
}
