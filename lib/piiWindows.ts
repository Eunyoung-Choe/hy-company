/**
 * PII Guard 시연 창 열기.
 * 데모 창은 화면 왼쪽 절반에 띄운다 (에이전트가 기본으로 캡처하는 영역).
 * 브라우저는 클릭 한 번에 팝업을 하나만 허용하므로, 데모는 새 창으로 열고 원격 화면은 현재 탭으로 연다.
 */
export function openDemoWindow(): boolean {
  const w = Math.round(window.screen.availWidth / 2);
  const h = window.screen.availHeight;
  const win = window.open('/pii/demo', 'pii-demo', `popup=yes,left=0,top=0,width=${w},height=${h}`);
  if (!win) return false; // 팝업 차단
  win.focus();
  return true;
}

/** 데모 창을 띄우고 현재 탭은 원격 화면으로 이동. 팝업이 막히면 원격 화면에서 안내한다. */
export function launchPiiDemo(): void {
  const opened = openDemoWindow();
  window.location.href = opened ? '/pii/viewer' : '/pii/viewer?demo=blocked';
}
