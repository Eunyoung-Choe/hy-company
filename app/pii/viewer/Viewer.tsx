'use client';

import { useEffect, useRef, useState } from 'react';
import { piiLabel } from '@/lib/pii';

const AGENT = (process.env.NEXT_PUBLIC_AGENT_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');

type Status = {
  sharing: boolean;
  capture_fps: number;
  output_fps: number;
  ocr_fps: number;
  ocr_latency_ms: number;
  ocr_ready: boolean;
  masked_boxes: number;
  pending_regions: number;
  last_kinds: string[];
  last_detect_at: number | null;
  audit_enabled: boolean;
  audit_uploaded: number;
  audit_failed: number;
  recording: boolean;
  recording_sec: number;
  last_recording: string | null;
  recording_error: string | null;
  masking: boolean;
};

// 크롬·엣지의 '다른 이름으로 저장' 창 (File System Access API). TS 기본 타입에 없어 직접 선언
type SavePicker = (opts: {
  suggestedName?: string;
  types?: { description: string; accept: Record<string, string[]> }[];
}) => Promise<{ createWritable: () => Promise<WritableStream<Uint8Array>> }>;

/** 녹화 파일을 '다른 이름으로 저장' 창으로 저장. 창을 지원하지 않으면 일반 다운로드. */
async function saveRecording(name: string): Promise<'saved' | 'cancel' | 'download'> {
  const url = `${AGENT}/recordings/${name}`;
  const picker = (window as unknown as { showSaveFilePicker?: SavePicker }).showSaveFilePicker;
  if (picker) {
    try {
      // 저장 창은 버튼 클릭 직후에만 열 수 있어서, 파일을 받기 전에 먼저 띄운다
      const handle = await picker({
        suggestedName: name,
        types: [{ description: 'MP4 동영상', accept: { 'video/mp4': ['.mp4'] } }],
      });
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok || !res.body) throw new Error(`녹화 파일을 받지 못했습니다 (HTTP ${res.status})`);
      await res.body.pipeTo(await handle.createWritable()); // 다 쓰면 파일이 자동으로 닫힘
      return 'saved';
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return 'cancel'; // 사용자가 취소
      if (!(e instanceof DOMException && e.name === 'SecurityError')) throw e;
      // 클릭 후 시간이 지나 창을 못 연 경우 → 일반 다운로드로
    }
  }
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  return 'download';
}

const mmss = (sec: number) => `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`;

export default function Viewer() {
  const [status, setStatus] = useState<Status | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [streamKey, setStreamKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [recBusy, setRecBusy] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [recNote, setRecNote] = useState<string | null>(null);

  // 토스트: 화면 아래쪽에 잠깐 떴다가 사라지는 알림
  const [toast, setToast] = useState<{ text: string; kind: 'info' | 'rec' | 'ok' | 'error'; id: number } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = (text: string, kind: 'info' | 'rec' | 'ok' | 'error' = 'info') => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ text, kind, id: Date.now() });
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };
  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current); }, []);
  // 첫 화면 바로가기에서 팝업이 막혀 데모 창을 못 연 경우 (?demo=blocked) 알림으로 안내
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('demo') === 'blocked') {
      showToast('팝업이 차단돼 데모 창을 열지 못했어요. 주소창의 팝업 차단을 허용해 주세요', 'error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async (name: string) => {
    try {
      const r = await saveRecording(name);
      setRecNote(r === 'saved' ? `저장했습니다: ${name}` : r === 'cancel' ? '저장을 취소했습니다. 아래 버튼으로 다시 저장할 수 있어요.' : null);
      if (r === 'saved') showToast('녹화 파일을 저장했습니다', 'ok');
      else if (r === 'cancel') showToast('저장을 취소했습니다', 'info');
      else showToast('녹화 파일을 내려받습니다', 'ok');
    } catch (e) {
      setRecError(e instanceof Error ? e.message : '저장 실패');
      showToast('녹화 파일 저장에 실패했습니다', 'error');
    }
  };

  // 녹화 시작/종료. 종료하면 에이전트가 MP4 파일을 마무리한 뒤 응답한다
  const setRecording = async (on: boolean) => {
    setRecBusy(true);
    setRecError(null);
    setRecNote(null);
    let saved: string | null = null;
    try {
      const r = await fetch(`${AGENT}/record?action=${on ? 'start' : 'stop'}`, { method: 'POST', cache: 'no-store' });
      if (!r.ok) throw new Error(r.status === 403 ? '허용되지 않은 주소입니다 (ALLOWED_ORIGINS 확인)' : `HTTP ${r.status}`);
      const s = (await r.json()) as Status;
      setStatus(s);
      if (s.recording_error) {
        setRecError(s.recording_error);
        showToast(on ? '녹화를 시작하지 못했습니다' : s.recording_error, 'error');
      } else if (on) {
        showToast('● 녹화가 시작됐습니다', 'rec');
      } else {
        showToast('■ 녹화가 종료됐습니다', 'ok');
        if (s.last_recording) saved = s.last_recording;
      }
    } catch (e) {
      setRecError(e instanceof Error ? e.message : '녹화 전환 실패');
      showToast(on ? '녹화를 시작하지 못했습니다' : '녹화를 종료하지 못했습니다', 'error');
    } finally {
      setRecBusy(false);
    }
    if (saved) await save(saved); // 녹화 종료 → 바로 '다른 이름으로 저장' 창
  };

  // 마스킹 켜기/끄기 (끄면 원본을 그대로 송출 — 비교 시연용)
  const setMasking = async (on: boolean) => {
    setBusy(true);
    setToggleError(null);
    try {
      const r = await fetch(`${AGENT}/control?masking=${on ? 'on' : 'off'}`, { method: 'POST', cache: 'no-store' });
      if (!r.ok) throw new Error(r.status === 403 ? '허용되지 않은 주소입니다 (ALLOWED_ORIGINS 확인)' : `HTTP ${r.status}`);
      setStatus((await r.json()) as Status);
    } catch (e) {
      setToggleError(e instanceof Error ? e.message : '전환 실패');
    } finally {
      setBusy(false);
    }
  };

  const setSharing = async (on: boolean) => {
    setBusy(true);
    setToggleError(null);
    try {
      const r = await fetch(`${AGENT}/control?sharing=${on ? 'on' : 'off'}`, { method: 'POST', cache: 'no-store' });
      if (!r.ok) throw new Error(r.status === 403 ? '허용되지 않은 주소입니다 (ALLOWED_ORIGINS 확인)' : `HTTP ${r.status}`);
      setStatus((await r.json()) as Status);
      if (on) setStreamKey((k) => k + 1); // 다시 켜면 스트림 재연결
    } catch (e) {
      setToggleError(e instanceof Error ? e.message : '전환 실패');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    let alive = true;
    let wasOnline = false;
    const poll = async () => {
      try {
        const r = await fetch(`${AGENT}/status`, { cache: 'no-store' });
        const s = (await r.json()) as Status;
        if (!alive) return;
        setStatus(s);
        setOnline(true);
        if (!wasOnline) setStreamKey((k) => k + 1); // 에이전트 재시작 시 스트림 다시 연결
        wasOnline = true;
      } catch {
        if (!alive) return;
        setOnline(false);
        wasOnline = false;
      }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const sharing = status?.sharing ?? true;
  const verifying = status && (!status.ocr_ready || status.pending_regions > 0);
  const recording = !!status?.recording;
  const masking = status?.masking ?? true;

  return (
    <div className="viewer">

      <section className="win viewer-screen">
        <div className="win-title">📺 수리기사 화면 <small>· 마스킹 결과</small></div>
        <div className="screen">
          {online && !sharing ? (
            <div className="screen-empty">
              <strong>원격이 꺼져 있습니다</strong>
              <span>화면 캡처와 송출이 멈춘 상태입니다.</span>
            </div>
          ) : online ? (
            // MJPEG 스트림은 next/image 최적화 대상이 아니므로 img 사용
            // eslint-disable-next-line @next/next/no-img-element
            <img key={streamKey} src={`${AGENT}/stream.mjpg?k=${streamKey}`} alt="마스킹된 원격 화면" />
          ) : (
            <div className="screen-empty">
              {online === null ? '에이전트 연결 중…' : (
                <>
                  <strong>에이전트에 연결할 수 없습니다</strong>
                  <span>{AGENT} 에서 마스킹 에이전트를 실행해 주세요.</span>
                </>
              )}
            </div>
          )}
          {online && recording && <span className="rec-badge">● REC {mmss(status?.recording_sec ?? 0)}</span>}
          {online && sharing && (masking ? (
            <span className={`badge ${verifying ? 'warn' : 'ok'}`}>
              {verifying ? '화면 갱신 중 (검증 대기)' : '✔ 검증 완료'}
            </span>
          ) : (
            <span className="badge danger">⚠ 마스킹 꺼짐 · 원본 송출 중</span>
          ))}
        </div>
      </section>

      <div className="panel-col">
        {/* 토스트: 조작 패널 바로 위 가운데 (녹화 시작·종료·저장, 팝업 차단 알림) */}
        <div className="panel-toast">
          {toast && (
            <div key={toast.id} className={`toast ${toast.kind}`} role="status" aria-live="polite">
              {toast.text}
            </div>
          )}
        </div>
      <aside className="win viewer-panel">
        <div className="win-title">🔧 조작 패널</div>
        <div className="win-body">
          <div className="ctl">
            <span className={`dot ${online && sharing ? 'on' : 'off'}`} />
            <strong>원격 {online ? (sharing ? 'ON' : 'OFF') : '연결 안 됨'}</strong>
            <button
              type="button"
              className={`btn small ${sharing ? 'danger' : 'go'}`}
              disabled={!online || busy}
              onClick={() => setSharing(!sharing)}
            >
              {busy ? '전환 중…' : sharing ? '원격 끄기' : '원격 켜기'}
            </button>
          </div>
          <div className="ctl">
            <span className={`dot ${online && masking ? 'on' : 'off'}`} />
            <strong>마스킹 {online ? (masking ? 'ON' : 'OFF') : '-'}</strong>
            <button
              type="button"
              className={`btn small ${masking ? 'danger' : 'go'}`}
              disabled={!online || busy}
              onClick={() => setMasking(!masking)}
            >
              {busy ? '전환 중…' : masking ? '마스킹 끄기' : '마스킹 켜기'}
            </button>
          </div>
          {toggleError && <p className="pii-error">{toggleError}</p>}

          <div className="ctl-block">
            <button
              type="button"
              className={`btn block ${recording ? 'danger' : ''}`}
              disabled={!online || recBusy}
              onClick={() => setRecording(!recording)}
            >
              {recBusy
                ? recording ? '저장 중…' : '시작 중…'
                : recording ? `■ 녹화 종료 (${mmss(status?.recording_sec ?? 0)})` : <><span className="rec-dot">●</span> 녹화 시작</>}
            </button>
            {!recording && status?.last_recording && (
              <button type="button" className="btn small block" onClick={() => save(status.last_recording!)}>
                💾 다른 이름으로 저장
              </button>
            )}
            <small className="pii-note">마스킹된 화면만 MP4로 녹화됩니다. 종료하면 저장 창이 열립니다.</small>
            {recNote && <small className="rec-note">{recNote}</small>}
            {recError && <p className="pii-error">{recError}</p>}
          </div>

          <h3 className="pii-sub">처리 상태</h3>
          <dl className="metrics">
            <dt>캡처</dt><dd>{status ? `${status.capture_fps} FPS` : '-'}</dd>
            <dt>송출</dt><dd>{status ? `${status.output_fps} FPS` : '-'}</dd>
            <dt>OCR 검증</dt><dd>{status ? `${status.ocr_fps} 회/초 · ${status.ocr_latency_ms}ms` : '-'}</dd>
            <dt>마스킹 박스</dt><dd>{status?.masked_boxes ?? '-'}</dd>
            <dt>검증 대기 영역</dt><dd>{status ? (status.ocr_ready ? status.pending_regions : '전체') : '-'}</dd>
          </dl>

          <h3 className="pii-sub">최근 감지</h3>
          {status?.last_kinds.length ? (
            <>
              <div className="chips">
                {status.last_kinds.map((k) => <span key={k} className="chip">{piiLabel(k)}</span>)}
              </div>
              {status.last_detect_at && (
                <small className="muted">{new Date(status.last_detect_at * 1000).toLocaleTimeString('ko-KR')}</small>
              )}
            </>
          ) : (
            <p className="muted">아직 없음</p>
          )}

          <h3 className="pii-sub">표시 규칙</h3>
          <ul className="legend">
            <li><span className="sw black" /> 검은 박스: 감지된 개인정보</li>
            <li><span className="sw mosaic" /> 모자이크: 새로 나타나 아직 검증 전인 영역 (보통 0.1~0.5초)</li>
            <li>검증 중인 영역은 직전 검증 화면을 스크롤에 맞춰 옮겨 보여줍니다</li>
          </ul>
        </div>
      </aside>
      </div>
    </div>
  );
}
