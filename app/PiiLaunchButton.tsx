'use client';

import { launchPiiDemo } from '@/lib/piiWindows';

/** 첫 화면의 PII Guard 바로가기. 누르면 데모 창(왼쪽 절반)과 원격 화면(현재 탭)이 함께 열린다.
 *  위치·모양은 첫 화면 디자인(globals.css의 .btn, .pii-launch)을 따른다. */
export default function PiiLaunchButton() {
  return (
    <button
      type="button"
      className="btn pii-launch"
      onClick={launchPiiDemo}
      title="데모 창(왼쪽 절반)과 원격 화면이 함께 열립니다"
    >
      🛡️ PII Guard 바로가기 →
    </button>
  );
}
