'use client';

import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';
import { getHealth, getJob, uploadVideo, type Health, type Job, type JobResult } from '@/lib/api';
import { saveDigest } from '@/lib/digests';
import Archive from './Archive';

type Tab = 'upload' | 'archive';
type SaveState = { status: 'idle' | 'saving' | 'saved' | 'error'; message?: string };

const STEPS = ['OpenCV 필터링', 'DINO 분석', '캡션 생성', '최종 요약'] as const;
const nf = new Intl.NumberFormat('ko-KR');
const usd = (v: number) => '$' + (Math.abs(v) < 0.01 ? v.toFixed(4) : v.toFixed(2));

type Phase = 'idle' | 'uploading' | 'processing' | 'done' | 'error';

export default function VideoSummarizer() {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState('');
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState('');
  const [tab, setTab] = useState<Tab>('upload');
  const [save, setSave] = useState<SaveState>({ status: 'idle' });
  const [archiveVersion, setArchiveVersion] = useState(0);   // 저장되면 보관함 목록 새로고침
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  useEffect(() => {
    getHealth()   // 연결 상태 안내용. 실패해도 업로드는 시도할 수 있음
      .then(setHealth)
      .catch((err: Error) => setHealthError(err.message));
  }, []);

  function pick(f: File | undefined) {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.mp4')) { setError('MP4 파일만 업로드할 수 있습니다.'); return; }
    setFile(f);
    setError('');
  }

  function fail(msg: string) {
    if (timer.current) clearInterval(timer.current);
    setError(msg);
    setPhase('error');
  }

  async function autoSave(title: string, r: JobResult) {
    setSave({ status: 'saving' });
    try {
      await saveDigest(title, r);
      setSave({ status: 'saved' });
      setArchiveVersion((v) => v + 1);
    } catch (err) {
      setSave({ status: 'error', message: (err as Error).message });   // 숨기지 않고 화면에 표시
    }
  }

  async function start(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const title = file.name;
    setError('');
    setResult(null);
    setJob(null);
    setSave({ status: 'idle' });
    setPhase('uploading');
    try {
      const jobId = await uploadVideo(file);
      setPhase('processing');
      timer.current = setInterval(async () => {
        try {
          const j = await getJob(jobId);
          setJob(j);
          if (j.status === 'done' && j.result) {
            if (timer.current) clearInterval(timer.current);
            setResult(j.result);
            setPhase('done');
            autoSave(title, j.result);
          } else if (j.status === 'error') {
            fail('처리 중 오류: ' + (j.error ?? '알 수 없는 오류'));
          }
        } catch (err) {
          fail((err as Error).message);
        }
      }, 1500);
    } catch (err) {
      fail((err as Error).message);
    }
  }

  const busy = phase === 'uploading' || phase === 'processing';
  const stage = phase === 'done' ? 5 : job?.stage ?? 1;
  const percent = phase === 'done' ? 100 : Math.round(job?.percent ?? 0);
  const statusText =
    phase === 'uploading' ? '영상 업로드 중…'
    : phase === 'done' ? '완료!'
    : job ? `${job.stage_label}${job.message ? ' · ' + job.message : ''}` : '대기 중…';

  return (
    <main className="desk">
      <header className="masthead">
        <h1 className="logo">
          <Image src="/videodigest-logo.png" alt="VideoDigest" width={90} height={90} priority />
        </h1>
        <p>영상을 통째로 LLM에 넣지 않고, 핵심 장면의 텍스트만으로 요약해 토큰을 아낍니다.</p>
      </header>

      {/* 1. 업로드 / 보관함 탭 */}
      <section className="win">
        <div className="win-title tabs" role="tablist" aria-label="메뉴">
          <button type="button" role="tab" id="tab-upload" aria-controls="panel-upload" aria-selected={tab === 'upload'}
            className={'tab' + (tab === 'upload' ? ' on' : '')} onClick={() => setTab('upload')}>
            📼 동영상 업로드{busy && tab !== 'upload' ? ' ⏳' : ''}
          </button>
          <button type="button" role="tab" id="tab-archive" aria-controls="panel-archive" aria-selected={tab === 'archive'}
            className={'tab' + (tab === 'archive' ? ' on' : '')} onClick={() => setTab('archive')}>
            🗂 보관함
          </button>
        </div>
        {tab === 'archive' && (
          <div role="tabpanel" id="panel-archive" aria-labelledby="tab-archive">
            <Archive refreshKey={archiveVersion} />
          </div>
        )}
        <form className="win-body" onSubmit={start} role="tabpanel" id="panel-upload" aria-labelledby="tab-upload"
          hidden={tab !== 'upload'}>
          <label
            className={'drop' + (dragOver ? ' over' : '')}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); pick(e.dataTransfer.files[0]); }}
          >
            <input ref={inputRef} type="file" accept="video/mp4,.mp4" hidden onChange={(e) => pick(e.target.files?.[0])} />
            <strong>MP4 파일을 여기에 끌어다 놓거나 클릭하세요</strong>
            <small>최대 10분 · 200MB · 처리 후 서버에서 삭제됩니다</small>
            {file && <em>{file.name} ({(file.size / 1024 / 1024).toFixed(1)}MB)</em>}
          </label>
          {health?.model && <p className="hint">캡션·요약 모델: <b>{health.model}</b></p>}
          {healthError && <p className="hint">⚠ 백엔드 상태를 확인하지 못했어요: {healthError}</p>}
          {health && health.openai_key === false && <p className="hint">⚠ 서버에 OpenAI 키가 설정되지 않았어요 (Colab Secrets 확인).</p>}
          {health && health.models_ready === false && <p className="hint">⏳ 서버가 DINOv2 모델을 불러오는 중이에요. 잠시 후 시작하세요.</p>}
          <div className="actions">
            <button type="submit" className="btn" disabled={!file || busy}>{busy ? '처리 중…' : '요약 시작 ▶'}</button>
          </div>
          {error && <p className="alert" role="alert">⚠ {error}</p>}
        </form>
      </section>

      {/* 2. 진행 상태 (업로드 탭에서만 표시, 탭을 바꿔도 처리는 계속됨) */}
      {tab === 'upload' && phase !== 'idle' && !(phase === 'error' && !job) && (
        <section className="win" aria-live="polite">
          <div className="win-title">⏳ 처리 진행 상황</div>
          <div className="win-body">
            <ol className="steps">
              {STEPS.map((label, i) => {
                const n = i + 1;
                const state = n < stage ? 'done' : n === stage && busy ? 'active' : '';
                return (
                  <li key={label} className={'step ' + state}>
                    <span className="mark">{state === 'done' ? '✔' : state === 'active' ? <i className="spinner" aria-hidden /> : n}</span>
                    {label}
                  </li>
                );
              })}
            </ol>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
              <div className="progress-fill" style={{ width: `${percent}%` }} />
            </div>
            <div className="progress-meta"><span>{statusText}</span><span>{percent}%</span></div>
          </div>
        </section>
      )}

      {tab === 'upload' && result && (
        <>
          <p className={'save-status ' + save.status} role="status">
            {save.status === 'saving' && '🗂 보관함에 저장 중…'}
            {save.status === 'saved' && <>🗂 보관함에 저장했어요. <button type="button" className="link" onClick={() => setTab('archive')}>보관함 열기 →</button></>}
            {save.status === 'error' && `⚠ 보관함 저장 실패: ${save.message}`}
          </p>
          <Results r={result} />
        </>
      )}
    </main>
  );
}

function Results({ r }: { r: JobResult }) {
  const m = r.metrics;
  const f = r.funnel;
  const ratio = m.baseline_tokens ? Math.min(100, (m.actual_tokens / m.baseline_tokens) * 100) : 0;
  return (
    <>
      {/* 3. 토큰 절감 대시보드 */}
      <section className="win">
        <div className="win-title">📊 토큰 절감 대시보드</div>
        <div className="win-body">
          <div className="hero"><b>{m.saved_percent}%</b><span>토큰 절약</span></div>
          <div className="kpis">
            <div className="kpi"><small>실제 사용 토큰</small><b>{nf.format(m.actual_tokens)}</b>
              <span>입력 {nf.format(m.actual_input_tokens)} · 출력 {nf.format(m.actual_output_tokens)}
                {m.reasoning_tokens > 0 && ` (추론 ${nf.format(m.reasoning_tokens)})`} · {m.api_calls}회 실행</span></div>
            <div className="kpi"><small>전체 영상 입력 시 (예상)</small><b>{nf.format(m.baseline_tokens)}</b>
              <span>{nf.format(m.baseline_frames)}프레임 × {nf.format(m.baseline_tokens_per_frame)}토큰</span></div>
            <div className="kpi"><small>절약한 토큰</small><b>{nf.format(m.saved_tokens)}</b><span>예상 − 실제</span></div>
            <div className="kpi"><small>예상 절감 비용</small><b>{usd(m.saved_cost_usd)}</b>
              <span>실제 {usd(m.actual_cost_usd)} / 통째로 {usd(m.baseline_cost_usd)}</span></div>
          </div>
          <div className="meter" title={`실제 ${nf.format(m.actual_tokens)} / 예상 ${nf.format(m.baseline_tokens)} 토큰`}>
            <div className="meter-legend"><span>실제 사용량 (예상 대비)</span><span>{ratio.toFixed(1)}%</span></div>
            <div className="meter-track"><div className="meter-fill" style={{ width: `${ratio}%` }} /></div>
          </div>
          <p className="funnel">
            1fps 샘플 <b>{nf.format(f.sampled)}장</b> <span>→</span> OpenCV 통과 <b>{nf.format(f.stage1_kept)}장</b>{' '}
            <span>→</span> DINO 키프레임 <b>{nf.format(f.keyframes)}장</b>
          </p>
          <p className="note">※ 캡션·요약 모델: {m.engine} · {m.assumption} · 처리 시간 {r.elapsed_sec}초</p>
        </div>
      </section>

      {/* 4. 최종 요약 */}
      <section className="win">
        <div className="win-title">📝 최종 요약</div>
        <div className="win-body"><p className="summary">{r.summary}</p></div>
      </section>

      {/* 5. 키프레임 갤러리 */}
      <section className="win">
        <div className="win-title">🖼 주요 장면 · 캡션 ({r.keyframes.length}장)</div>
        <div className="win-body gallery">
          {r.keyframes.map((k) => (
            <figure key={k.time} className="shot">
              <div className="shot-img">
                <img src={`data:image/jpeg;base64,${k.image}`} alt={`${k.time_label} 장면`} loading="lazy" />
                <span className="stamp">{k.time_label}</span>
              </div>
              <figcaption className={k.failed ? 'failed' : undefined}>{k.caption}</figcaption>
            </figure>
          ))}
        </div>
      </section>
    </>
  );
}
