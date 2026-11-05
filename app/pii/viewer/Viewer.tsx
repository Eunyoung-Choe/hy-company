'use client';

import { useEffect, useState } from 'react';
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

  const save = async (name: string) => {
    try {
      const r = await saveRecording(name);
      setRecNote(r === 'saved' ? `저장했습니다: ${name}` : r === 'cancel' ? '저장을 취소했습니다. 아래 버튼으로 다시 저장할 수 있어요.' : null);
    } catch (e) {
      setRecError(e instanceof Error ? e.message : '저장 실패');
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
      if (s.recording_error) setRecError(s.recording_error);
      else if (!on && s.last_recording) saved = s.last_recording;
    } catch (e) {
      setRecError(e instanceof Error ? e.message : '녹화 전환 실패');
    } finally {
      setRecBusy(false);
    }
    if (saved) await save(saved); // 녹화 종료 → 바로 '다른 이름으로 저장' 창
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

  return (
    <div className="viewer">
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
        {online && sharing && (
          <span className={`badge ${verifying ? 'warn' : 'ok'}`}>
            {verifying ? '화면 갱신 중 (검증 대기)' : '검증 완료'}
          </span>
        )}
      </div>

      <aside className="panel">
        <div className="remote-toggle">
          <span className={`dot ${online && sharing ? 'on' : 'off'}`} />
          <strong>원격 {online ? (sharing ? 'ON' : 'OFF') : '연결 안 됨'}</strong>
          <button
            type="button"
            className={sharing ? 'btn-off' : 'btn-on'}
            disabled={!online || busy}
            onClick={() => setSharing(!sharing)}
          >
            {busy ? '전환 중…' : sharing ? '원격 끄기' : '원격 켜기'}
          </button>
        </div>
        {toggleError && <p className="toggle-error">{toggleError}</p>}

        <div className="record">
          <button
            type="button"
            className={recording ? 'btn-rec-stop' : 'btn-rec'}
            disabled={!online || recBusy}
            onClick={() => setRecording(!recording)}
          >
            {recBusy
              ? recording ? '저장 중…' : '시작 중…'
              : recording ? `■ 녹화 종료 (${mmss(status?.recording_sec ?? 0)})` : '● 녹화 시작'}
          </button>
          {!recording && status?.last_recording && (
            <button type="button" className="btn-rec-save" onClick={() => save(status.last_recording!)}>
              💾 다른 이름으로 저장 ({status.last_recording})
            </button>
          )}
          <small className="muted">마스킹된 화면만 MP4로 녹화됩니다. 종료하면 저장 창이 열립니다.</small>
          {recNote && <small className="rec-note">{recNote}</small>}
          {recError && <p className="toggle-error">{recError}</p>}
        </div>

        <h3>처리 상태</h3>
        <dl className="metrics">
          <dt>캡처</dt><dd>{status ? `${status.capture_fps} FPS` : '-'}</dd>
          <dt>송출</dt><dd>{status ? `${status.output_fps} FPS` : '-'}</dd>
          <dt>OCR 검증</dt><dd>{status ? `${status.ocr_fps} 회/초 · ${status.ocr_latency_ms}ms` : '-'}</dd>
          <dt>마스킹 박스</dt><dd>{status?.masked_boxes ?? '-'}</dd>
          <dt>검증 대기 영역</dt><dd>{status ? (status.ocr_ready ? status.pending_regions : '전체') : '-'}</dd>
        </dl>

        <h3>최근 감지</h3>
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

        <h3>감사 로그</h3>
        <p className="muted">
          {status
            ? status.audit_enabled
              ? `업로드 ${status.audit_uploaded}건 · 실패 ${status.audit_failed}건`
              : 'Supabase 미설정 (업로드 꺼짐)'
            : '-'}
        </p>

        <h3>표시 규칙</h3>
        <ul className="legend">
          <li><span className="sw black" /> 검은 박스: 감지된 개인정보</li>
          <li><span className="sw mosaic" /> 모자이크: OCR 검증 전 변경 영역</li>
        </ul>
      </aside>
    </div>
  );
}
