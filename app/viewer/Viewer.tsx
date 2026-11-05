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
};

export default function Viewer() {
  const [status, setStatus] = useState<Status | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [streamKey, setStreamKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toggleError, setToggleError] = useState<string | null>(null);

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
